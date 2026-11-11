import asyncio
import importlib

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from security import central_logger
central_logger.init_central_logging()
import json
import os
import time
import sys
import html as _html
import re
import httpx

from quart import Quart, websocket, request, jsonify, render_template_string

from core.roles import is_admin_role
from core import session_manager as sm
from core import project_manager as pm
from agents import agent_manager as am
from agents import browser_key_relay
from security import security_manager as sec_m

app = Quart(__name__, static_folder=None)

from core.routes.auth import auth_bp
from core.routes.projects import projects_bp
from core.routes.files import files_bp
from core.routes.system import system_bp
from core.routes.ai import ai_bp as ai_routes_bp
from core.routes.access import access_bp
from core.routes.device_keys import device_keys_bp

app.register_blueprint(auth_bp)
app.register_blueprint(projects_bp)
app.register_blueprint(files_bp)
app.register_blueprint(system_bp)
app.register_blueprint(ai_routes_bp)
app.register_blueprint(access_bp)
app.register_blueprint(device_keys_bp)

from security import security_headers
security_headers.init_security_headers(app)


def _cookie_secure() -> bool:
    """Mark cookies Secure only on https (directly, or via Cloudflare/a proxy). Browsers drop a
    Secure cookie sent over plain http on any address but the literal name 'localhost', which
    left visitors on http://127.0.0.1 or the LAN/WSL address stuck on the terms screen."""
    try:
        if request.scheme == "https":
            return True
        if (request.headers.get("X-Forwarded-Proto") or "").split(",")[0].strip().lower() == "https":
            return True
        return '"scheme":"https"' in (request.headers.get("CF-Visitor") or "").replace(" ", "")
    except Exception:
        return True


def _cookie_samesite() -> str:
    """'None' on https so the guest/terms cookies also travel with calls from the E-Profile front
    end (another site, see PORTAL_ORIGINS); 'Lax' on plain http, where browsers reject 'None'."""
    return "None" if _cookie_secure() else "Lax"


# Front ends on other sites that call this server's API directly (E-Profile is only a front end
# for the agent). Exact origins only; extra ones via DEVCORE_PORTAL_ORIGINS (comma-separated).
PORTAL_ORIGINS = {o.strip().rstrip("/") for o in (
    ["https://mikeymike.pythonanywhere.com", "https://eprofile-eou.pages.dev"]
    + os.environ.get("DEVCORE_PORTAL_ORIGINS", "").split(","))
    if o.strip()}


@app.after_request
async def _portal_cors(response):
    """Let the E-Profile front end call /api/* with the visitor's mikeytech.dev cookies."""
    try:
        origin = (request.headers.get("Origin") or "").rstrip("/")
        if origin in PORTAL_ORIGINS and request.path.startswith("/api/"):
            response.headers["Access-Control-Allow-Origin"] = origin
            response.headers["Access-Control-Allow-Credentials"] = "true"
            response.headers["Access-Control-Allow-Headers"] = "Authorization, Content-Type, X-Client-ID"
            response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
            response.headers["Access-Control-Max-Age"] = "600"
            response.headers.add("Vary", "Origin")
    except Exception:
        pass
    return response


@app.after_request
async def _ensure_guest_session_cookie(response):
    """Give every browser a random guest session cookie on its first visit; guests are identified
    by it (hashed), never by IP address. See security/guest_session.py."""
    try:
        from quart import g
        from security import guest_session
        existing = guest_session.session_from_headers(request.headers)
        if not existing:
            sid = getattr(g, "devcore_guest_sid", "") or guest_session.new_session_id()
            response.set_cookie(guest_session.COOKIE_NAME, sid, max_age=guest_session.COOKIE_MAX_AGE, path="/",
                                httponly=True, secure=_cookie_secure(), samesite=_cookie_samesite())
        elif request.path == "/" and _cookie_secure():
            # Re-issue cookies set before the E-Profile front end existed (SameSite=Lax) as
            # SameSite=None, once per page load, so they travel with E-Profile's calls too.
            response.set_cookie(guest_session.COOKIE_NAME, existing, max_age=guest_session.COOKIE_MAX_AGE, path="/",
                                httponly=True, secure=True, samesite="None")
            if guest_session.terms_accepted(request.headers):
                response.set_cookie(guest_session.TERMS_COOKIE, guest_session.TERMS_VERSION, max_age=365 * 86400,
                                    path="/", httponly=True, secure=True, samesite="None")
    except Exception:
        pass
    return response

project_mgr = pm.ProjectManager()
session_mgr = sm.SessionManager()
agent_mgr = am.AgentTaskManager(project_manager=project_mgr)
security_mgr = sec_m.SecurityManager()
app.security_mgr = security_mgr
app.project_mgr = project_mgr
app.session_mgr = session_mgr
app.agent_mgr = agent_mgr

async def execute_hot_patch_sequence(manual_trigger=False):
    """Timer sequence for safe hot-patching with syntax validation and automated rollback."""
    from core.routes.system import execute_hot_patch_sequence as _run_hot_patch
    await _run_hot_patch(app_obj=app, manual_trigger=manual_trigger)

async def auto_patch_daemon():
    """Runs continuously in the background to automatically patch exploits."""
    while True:
        await asyncio.sleep(1800)
        await execute_hot_patch_sequence()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

async def raugus_map_watcher_daemon():
    """
    Background watcher that monitors workspace directories (playground, docs)
    and updates raugus_map.json incrementally if modified out-of-band.
    """
    import os
    import time
    devcore_root = os.path.dirname(BASE_DIR)
    watched_dirs = [
        os.path.join(devcore_root, 'playground'),
        os.path.join(devcore_root, 'docs'),
    ]
    seen_mtimes = {}
    # Folders that are never project source: version control, environments, caches, sandboxes.
    skip_dirs = {'.git', 'node_modules', '__pycache__', 'venv', '.venv', '.virtualenvs', '.local', '.cache',
                 '.dev_sandboxes', 'site-packages', 'backups', '.ipython', '.ssh', '.gemini'}

    def _scan_once():
        """One pass over the watched folders. Runs in a worker thread: on /mnt/c every stat is slow,
        and walking the playground on the event loop (it now holds e_profile, with its .git and
        virtualenvs) froze the whole server for ~20 s every few seconds."""
        for wdir in watched_dirs:
            if not os.path.exists(wdir):
                continue
            for root, dirs, files in os.walk(wdir):
                dirs[:] = [d for d in dirs if d not in skip_dirs and not d.startswith('.')]
                for fname in files:
                    if fname.startswith('.') or fname.endswith(('.pyc', '.tmp', '.log')):
                        continue
                    fpath = os.path.join(root, fname)
                    try:
                        mtime = os.stat(fpath).st_mtime
                        if fpath not in seen_mtimes:
                            seen_mtimes[fpath] = mtime
                        elif seen_mtimes[fpath] != mtime:
                            seen_mtimes[fpath] = mtime
                            try:
                                from security.raugus_sync import sync_path
                                sync_path(fpath, root_dir=devcore_root)
                            except Exception:
                                pass
                    except Exception:
                        continue

    while True:
        try:
            await asyncio.sleep(4)
            await asyncio.to_thread(_scan_once)
        except asyncio.CancelledError:
            break
        except Exception:
            await asyncio.sleep(4)

@app.before_serving
async def start_background_tasks():
    app.add_background_task(auto_patch_daemon)
    app.add_background_task(raugus_map_watcher_daemon)

def get_live_override_path(rel_path):
    """
    LIVE OVERRIDE ARCHITECTURE (OTA Drop-in Updates)
    Checks if a loose file exists next to the .exe (in CWD) before falling back to the compiled bundle.
    This allows updating the UI/Plugins without downloading a new .exe!
    """
    import os
    import sys
    exe_dir = os.path.dirname(sys.executable) if getattr(sys, 'frozen', False) else os.getcwd()
    
    live_path = os.path.join(exe_dir, rel_path)
    if os.path.exists(live_path):
        return live_path
        
    cwd_path = os.path.join(os.getcwd(), rel_path)
    if os.path.exists(cwd_path):
        return cwd_path
        
    return os.path.join(os.path.dirname(BASE_DIR), rel_path)

def read_asset(rel_path):
    from security.vfs import vfs
    vfs.load()
    live_path = get_live_override_path(rel_path)
    if os.path.exists(live_path):
        return open(live_path, 'rb').read()
    data = vfs.read(rel_path)
    if data:
        return data
    return None

@app.route('/static/<path:filename>')
async def custom_static(filename):
    import mimetypes
    data = read_asset(f"sandbox/static/{filename}")
    if data:
        # Windows' mimetypes table lacks these; module scripts and WebAssembly
        # refuse to load with the wrong Content-Type (on-device dictation needs them).
        ext = os.path.splitext(filename)[1].lower()
        mime_type = {
            '.js': 'text/javascript', '.mjs': 'text/javascript',
            '.wasm': 'application/wasm', '.onnx': 'application/octet-stream',
        }.get(ext) or mimetypes.guess_type(filename)[0]
        headers = {'Content-Type': mime_type or 'application/octet-stream'}
        if filename.startswith('speech/vendor/') or filename.startswith('speech/models/'):
            headers['Cache-Control'] = 'public, max-age=604800'  # large, rarely-changing files
        elif filename in ('speech/speech-worker.js', 'speech/dictation.js', 'device-keys.js', 'device-keys-ui.js'):
            # A worker runs under the CSP of its own response; if Cloudflare caches it,
            # header changes (e.g. 'wasm-unsafe-eval') never reach the browser.
            headers['Cache-Control'] = 'no-cache'
        return data, 200, headers
    return "Not Found", 404

TEMPLATE_FILE = get_live_override_path("sandbox/templates/index.html")
UI_CONFIG_FILE = get_live_override_path("core/ui_config.json")

CACHED_MODELS = None

async def fetch_dynamic_models(force_cli: bool = False):
    global CACHED_MODELS
    if CACHED_MODELS is not None and not force_cli:
        return CACHED_MODELS

    try:
        from core.local_model_service import discover_local_models
        local_entries = discover_local_models()
    except Exception:
        local_entries = [{"value": "Local Qwen 2.5 (Offline)", "text": "Local Qwen 2.5 (Offline)"}]
    local_values = {e["value"] for e in local_entries}

    if not force_cli:
        try:
            ui_config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ui_config.json")
            if os.path.exists(ui_config_path):
                with open(ui_config_path, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
                static_models = cfg.get("header", {}).get("models")
                if isinstance(static_models, list) and static_models:
                    filtered = [m for m in static_models if m.get("value") not in local_values]
                    models_list = ([filtered[0]] + local_entries + filtered[1:]) if filtered else list(local_entries)
                    CACHED_MODELS = models_list
                    return CACHED_MODELS
        except Exception:
            pass

    local_agy = os.path.expanduser("~/.local/bin/agy")
    if not os.path.exists(local_agy):
        return None
        
    try:
        import sys
        if sys.platform == "win32":
            cmd = ["wsl.exe", "-e", "bash", "-c", "~/.local/bin/agy --model invalid --print 'test'"]
        else:
            cmd = [local_agy, "--model", "invalid", "--print", "test"]
        proc = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT
        )
        stdout, _ = await proc.communicate()
        out_str = stdout.decode("utf-8", errors="ignore")
        if "Available models:" in out_str:
            models_section = out_str.split("Available models:")[1]
            lines = models_section.strip().split("\n")
            fetched_models = []
            for line in lines:
                val = line.strip()
                if val and not val.startswith("Set-PSReadLineOption") and not val.startswith("At C:") and not val.startswith("+") and not val.startswith("CategoryInfo") and not val.startswith("FullyQualifiedErrorId") and not val.startswith("~"):
                    fetched_models.append({"value": val, "text": val})
            if fetched_models:
                filtered = [m for m in fetched_models if m.get("value") not in local_values]
                fetched_models = ([filtered[0]] + local_entries + filtered[1:]) if filtered else list(local_entries)
                CACHED_MODELS = fetched_models
                return fetched_models
    except Exception:
        pass
    return None

@app.route('/')
async def index():
    """Dynamically serves and renders the template using Jinja2 variables."""
    import json
    template_bytes = read_asset("sandbox/templates/index.html")
    if not template_bytes:
        return "Template not found: sandbox/templates/index.html", 404
    content = template_bytes.decode('utf-8')
    
    ui_bytes = read_asset("core/ui_config.json")
    ui_strings = json.loads(ui_bytes.decode('utf-8')) if ui_bytes else {}
    
    dyn_models = await fetch_dynamic_models()
    if dyn_models:
        if "header" not in ui_strings:
            ui_strings["header"] = {}
        ui_strings["header"]["models"] = dyn_models
    
    rendered_content = await render_template_string(content, ui=ui_strings)
    return rendered_content, 200, {'Content-Type': 'text/html; charset=utf-8'}

@app.route('/ai_agent/')
@app.route('/ai_agent')
async def ai_agent_index():
    return await index()

GLOBAL_AUTH_PROC = None

@app.route('/plugin/media')
async def plugin_media():
    """Dynamically renders the video application plugin."""
    import json
    video_id = request.args.get('v', 'jNQXAC9IVRw')
    video_title = request.args.get('title', 'Accessible Video Player')
    
    template_bytes = read_asset("sandbox/templates/video_application.html")
    if not template_bytes:
        return "Media template not found", 404
    content = template_bytes.decode('utf-8')
    
    ui_bytes = read_asset("core/ui_config.json")
    ui_strings = json.loads(ui_bytes.decode('utf-8')) if ui_bytes else {}
    
    rendered = await render_template_string(content, ui=ui_strings, video_id=video_id, video_title=video_title)
    return rendered, 200, {'Content-Type': 'text/html; charset=utf-8'}

@app.route('/plugin/security')
async def plugin_security():
    """Dynamically renders the security dashboard plugin."""
    import json
    template_bytes = read_asset("sandbox/templates/security_dashboard.html")
    if not template_bytes:
        return "Security template not found", 404
    content = template_bytes.decode('utf-8')
    
    ui_bytes = read_asset("core/ui_config.json")
    ui_strings = json.loads(ui_bytes.decode('utf-8')) if ui_bytes else {}
    
    rendered = await render_template_string(content, ui=ui_strings)
    return rendered, 200, {'Content-Type': 'text/html; charset=utf-8'}

@app.route('/plugin/exam')
async def plugin_exam():
    """Dynamically renders the exam generator plugin."""
    import json
    quiz_file = request.args.get('quiz', 'quiz_temp.json')
    exam_title = request.args.get('title', 'Siraugga Exam')
    # Ticket gate questionnaires are private: served only to the visitor they were made for
    intake = request.args.get('intake', '')
    if intake and re.fullmatch(r"I-[A-Za-z0-9_-]{8,40}", intake):
        quiz_url = f"/api/tickets/intake/{intake}/exam"
    else:
        quiz_url = f"/static/{quiz_file}"

    template_bytes = read_asset("sandbox/templates/exam_application.html")
    if not template_bytes:
        return "Exam template not found", 404
    content = template_bytes.decode('utf-8')

    ui_bytes = read_asset("core/ui_config.json")
    ui_strings = json.loads(ui_bytes.decode('utf-8')) if ui_bytes else {}

    rendered = await render_template_string(content, ui=ui_strings, quiz_file=quiz_file, quiz_url=quiz_url, exam_title=exam_title)
    return rendered, 200, {'Content-Type': 'text/html; charset=utf-8'}

@app.route('/plugin/exam_builder')
async def plugin_exam_builder():
    """Serves the visual Exam Builder Dashboard."""
    template_bytes = read_asset("sandbox/templates/exam_builder.html")
    if not template_bytes:
        return "Exam builder template not found", 404
    content = template_bytes.decode('utf-8')
    rendered = await render_template_string(content)
    return rendered, 200, {'Content-Type': 'text/html; charset=utf-8'}

@app.route('/plugin/audits')
async def plugin_audits():
    """Serves the System Audits Review Hub."""
    template_bytes = read_asset("sandbox/templates/audits.html")
    if not template_bytes:
        template_bytes = read_asset("templates/audits.html")
    if not template_bytes:
        return "Audits template not found", 404
    content = template_bytes.decode('utf-8')
    rendered = await render_template_string(content)
    return rendered, 200, {'Content-Type': 'text/html; charset=utf-8'}

@app.route('/api/exam/content', methods=['GET', 'POST'])
async def api_exam_content():
    content_dir = os.path.join(os.getcwd(), 'plugins', 'exam_application', 'content')
    os.makedirs(content_dir, exist_ok=True)
    if request.method == 'GET':
        try:
            files = os.listdir(content_dir)
            files = [f for f in files if os.path.isfile(os.path.join(content_dir, f))]
            return jsonify({"files": files})
        except Exception as e:
            return jsonify({"error": str(e)}), 500
    
    if request.method == 'POST':
        files = await request.files
        uploaded = []
        for name, file in files.items():
            path = os.path.join(content_dir, file.filename)
            await file.save(path)
            uploaded.append(file.filename)
        return jsonify({"message": "Files uploaded successfully", "files": uploaded})

_ARTIFACT_SECRET_NAMES = {
    ".devcore_master.key", "subscriptions.json", "subscriptions.json.tmp", "sessions.json",
    "antigravity-oauth-token", "gemini_api_key.txt", ".devcore_client_key.txt",
    "webauthn_credentials.json", ".env", "key.pem", "cert.pem", "id_rsa", "id_ed25519",
    "demo_gemini.key", "demo_gemini.key.tmp",
}


def _artifact_admin_user(token=None):
    """Direct file access is a super-admin feature: resolve the caller and return them only if they are an admin."""
    try:
        user = security_mgr.get_user_from_token(token or None, remote_addr=request.remote_addr, headers=request.headers)
    except Exception:
        user = None
    # The Super Admin (owner) only: these endpoints read/write any file on the machine, and an
    # admin is bound to their project and may not see code.
    return user if security_mgr.is_super_admin(user) else None


def _artifact_path_blocked(path: str) -> bool:
    """True for secrets that must never be read or written through the browser, even by an admin."""
    if not path or "\x00" in path:
        return True
    real = os.path.realpath(path).replace("\\", "/")
    if os.path.basename(real) in _ARTIFACT_SECRET_NAMES or "/.ssh/" in real + "/" or "/.gnupg/" in real + "/":
        return True
    try:
        from security.raugus_resolver import resolver
        if resolver.is_sensitive_path(path) or resolver.is_sensitive_path(real):
            return True
    except Exception:
        pass
    return False


@app.route('/api/artifacts', methods=['GET'])
async def get_artifact():
    import sys
    import subprocess
    
    token = request.headers.get("Authorization", "").replace("Bearer ", "").strip()
    if not _artifact_admin_user(token):
        return jsonify({"error": "Admin authorization required"}), 403

    path = request.args.get('path', '')
    if path.startswith('file://'):
        path = path[7:]

    if _artifact_path_blocked(path):
        return jsonify({"error": "Raugus Sensitive Vault: Direct HTTP read of sensitive files is blocked."}), 403

    if sys.platform == "win32" and path.startswith("/"):
        try:
            result = subprocess.run(["wsl.exe", "-e", "cat", path], capture_output=True, text=True)
            if result.returncode == 0:
                return jsonify({"content": result.stdout})
            else:
                return jsonify({"error": f"WSL Artifact not found: {result.stderr}"}), 404
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    if not os.path.exists(path):
        return jsonify({"error": "Artifact not found"}), 404
        
    try:
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()
        return jsonify({"content": content})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
        

@app.route('/api/artifacts/save', methods=['POST'])
async def save_artifacts():
    import sys
    import subprocess
    import shlex
    
    auth_header = request.headers.get("Authorization", "")
    token = auth_header.replace("Bearer ", "").strip()
    if not token:
        return jsonify({"error": "Unauthorized"}), 401
    if not _artifact_admin_user(token):
        return jsonify({"error": "Admin authorization required"}), 403

    data = await request.get_json() or {}
    path = str(data.get('path', '') or '')
    content = str(data.get('content', '') or '')
    append_mode = bool(data.get('append', False))

    if path.startswith('file://'):
        path = path[7:]

    if _artifact_path_blocked(path):
        return jsonify({"error": "Raugus Sensitive Vault: Direct HTTP write to sensitive files is blocked."}), 403

    real_path = os.path.realpath(path).replace("\\", "/") if sys.platform != "win32" else path
    if not (real_path.startswith("/home/") or real_path.startswith("/mnt/")) or "/../" in path.replace("\\", "/") + "/":
        return jsonify({"error": "Path traversal blocked"}), 403
    if sys.platform != "win32":
        path = real_path
        
    safe_path = shlex.quote(path)
    
    if sys.platform == "win32" and path.startswith("/"):
        import tempfile
        try:
            fd, tmp_path = tempfile.mkstemp(suffix=".md")
            with os.fdopen(fd, 'w', encoding='utf-8') as f:
                f.write(content)
            
            if append_mode:
                cmd = f"cat $(wslpath -a '{tmp_path}') >> {safe_path}"
            else:
                cmd = f"cp $(wslpath -a '{tmp_path}') {safe_path}"
                
            process = subprocess.Popen(
                ["wsl.exe", "-e", "bash", "-c", cmd],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
            )
            stdout, stderr = process.communicate()
            
            try:
                os.remove(tmp_path)
            except Exception:
                pass
                
            if process.returncode == 0:
                return jsonify({"success": True})
            else:
                return jsonify({"error": f"WSL Artifact write failed: {stderr}"}), 500
        except Exception as e:
            return jsonify({"error": str(e)}), 500
    else:
        try:
            mode = "a" if append_mode else "w"
            with open(path, mode, encoding="utf-8") as f:
                f.write(content)
            return jsonify({"success": True})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

@app.route('/api/prompt/massive', methods=['POST'])
async def handle_massive_prompt():
    auth_hdr = request.headers.get('Authorization', '')
    token = auth_hdr.replace('Bearer ', '').strip()
    user = security_mgr.get_user_from_token(token)
    if not user:
        return jsonify({"error": "Unauthorized"}), 401

    data = await request.get_json()
    raw_prompt = data.get("prompt", "")
    conv_id = data.get("conv_id", "")
    
    if not raw_prompt or not conv_id:
        return jsonify({"error": "Missing prompt or conv_id"}), 400
        
    try:
        import os
        try:
            from local_security import LocalSecurity
            local_sec = LocalSecurity()
            scrubbed_prompt = local_sec.scrub_text(raw_prompt)
        except ImportError:
            print("Warning: presidio-analyzer missing. Skipping PII scrubbing.")
            scrubbed_prompt = raw_prompt
        
        upload_dir = os.path.join(".agents", "massive_prompts")
        os.makedirs(upload_dir, exist_ok=True)
        file_path = os.path.join(upload_dir, f"{conv_id}.txt")
        
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(scrubbed_prompt)
            
        return jsonify({"success": True, "file_path": file_path})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.websocket('/ws')
@app.websocket("/ws")
@app.websocket("/ai_agent/ws")
async def ws_endpoint():
    ws = websocket._get_current_object()
    client_queue = asyncio.Queue()
    await agent_mgr.register_client(client_queue)
    _ws_addr = getattr(websocket, "remote_addr", None)
    _ws_hdrs = getattr(websocket, "headers", None)
    _ws_args = getattr(websocket, "args", {}) or {}
    init_token = (_ws_args.get("token") or (_ws_hdrs.get("Authorization", "") if _ws_hdrs else "").replace("Bearer ", "")).strip()
    init_cid = (_ws_args.get("client_id") or "").strip()
    from security import guest_session
    _ws_guest_name = guest_session.guest_username(_ws_hdrs)
    _ws_net_key = (guest_session.network_key(guest_session.connection_address(_ws_hdrs, _ws_addr))
                   if guest_session.terms_accepted(_ws_hdrs) else "")

    def _resolve_ws_user_and_slot(tok=None, cid=None):
        use_tok = tok if tok is not None else init_token
        use_cid = cid if cid is not None else init_cid
        u = None
        if use_tok:
            u = security_mgr.get_user_from_token(use_tok, remote_addr=_ws_addr, headers=_ws_hdrs)
        if not u:
            u = security_mgr.get_user_from_token(None, remote_addr=_ws_addr, headers=_ws_hdrs)
        if not u:
            # Guests are identified by their session cookie, never by IP address
            u = {"username": _ws_guest_name, "name": "Guest", "role": "guest", "token_scope": "user"}
        base_u = u.get("username") or u.get("name") or "guest"
        s_key = f"{base_u}::{use_cid}" if use_cid else base_u
        u = dict(u)
        u["username"] = base_u
        u["_slot_key"] = s_key
        u["_client_id"] = use_cid
        u["_device_id"] = use_cid
        try:
            from agents import unlock_links
            u["_unlimited"] = unlock_links.is_unlimited(_ws_hdrs)
        except Exception:
            u["_unlimited"] = False
        if _ws_net_key:
            u["_net_key"] = _ws_net_key  # abuse guard explained in the terms; in memory, rotates daily
        return u, s_key

    curr_user, curr_slot_key = _resolve_ws_user_and_slot()
    await agent_mgr.authenticate_client(client_queue, curr_slot_key)

    async def _safe_send(payload):
        try:
            if isinstance(payload, dict):
                payload = json.dumps(payload)
            await client_queue.put(payload)
        except Exception as e:
            print(f"WebSocket Queue Error: {e}")

    async def sender():
        try:
            while True:
                msg = await client_queue.get()
                if msg is None:
                    break
                if isinstance(msg, dict):
                    msg = json.dumps(msg)
                await ws.send(msg)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            print(f"WebSocket Sender Error: {e}")

    sender_task = asyncio.create_task(sender())

    try:
        while True:
            if sender_task.done():
                break
            raw_msg = await ws.receive()
            if raw_msg is None:
                break
            if not raw_msg:
                continue

            prompt = None
            model = "gemini-3.8-flash-high"
            conversation_id = None
            try:
                data = json.loads(raw_msg)
                if browser_key_relay.is_relay_frame(data):
                    browser_key_relay.deliver_from_browser(curr_slot_key, data)
                    continue
                msg_type = data.get("type", "prompt")
                if data.get("client_id"):
                    init_cid = str(data.get("client_id")).strip()
                elif data.get("device_id"):
                    init_cid = str(data.get("device_id")).strip()
                if data.get("token") is not None:
                    init_token = str(data.get("token") or "").strip()
                curr_user, curr_slot_key = _resolve_ws_user_and_slot(init_token, init_cid)
                await agent_mgr.authenticate_client(client_queue, curr_slot_key)
                if hasattr(agent_mgr, "set_task_context"):
                    agent_mgr.set_task_context(curr_slot_key)

                if msg_type == "ping":
                    await _safe_send({"type": "pong", "time": time.time()})
                    continue
                elif msg_type == "sync":
                    last_seq = data.get("last_seq", 0)
                    await agent_mgr.sync_client(client_queue, last_seq)
                    continue
                elif msg_type == "cancel":
                    await agent_mgr.cancel_task(user=curr_user)
                    continue
                elif msg_type == "auth_token":
                    token = data.get("token", "")
                    init_token = str(token).strip()
                    curr_user, curr_slot_key = _resolve_ws_user_and_slot(init_token, init_cid)
                    await agent_mgr.authenticate_client(client_queue, curr_slot_key)
                    await agent_mgr.submit_auth_token(token)
                    continue
                elif msg_type == "save_artifact":
                    if not (curr_user and is_admin_role(curr_user.get("role"))):
                        print(f"[Security] Blocked save_artifact from non-admin {curr_slot_key}")
                        await _safe_send({"type": "system", "level": "error", "message": "Saving files directly requires admin rights."})
                        continue
                    path = str(data.get("path", "") or "")
                    content = str(data.get("content", "") or "")
                    if path.startswith('file://'):
                        path = path[7:]
                    norm = path.replace("\\", "/")
                    real = os.path.realpath(path).replace("\\", "/") if sys.platform != "win32" else norm
                    if _artifact_path_blocked(path) or "/../" in norm + "/" or not (real.startswith("/home/") or real.startswith("/mnt/")):
                        await _safe_send({"type": "system", "level": "error", "message": "That file path is not allowed."})
                        continue

                    import subprocess
                    if sys.platform == "win32" and path.startswith("/"):
                        try:
                            temp_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "wsl_temp_save.md")
                            with open(temp_path, "w", encoding="utf-8") as tf:
                                tf.write(content)

                            wsl_temp = subprocess.run(["wsl.exe", "wslpath", "-a", temp_path], capture_output=True, text=True, creationflags=0x08000000).stdout.strip()
                            subprocess.run(["wsl.exe", "-e", "cp", "--", wsl_temp, path], creationflags=0x08000000)

                            if os.path.exists(temp_path):
                                os.remove(temp_path)
                        except Exception as e:
                            print(f"WSL save error: {e}")
                    else:
                        try:
                            with open(real, 'w', encoding='utf-8') as f:
                                f.write(content)
                        except Exception:
                            pass
                    continue
                elif msg_type == "exam_ready":
                    await agent_mgr.broadcast(data)
                    continue
                elif msg_type == "cli_input":
                    cli_in = data.get("input", "")
                    await agent_mgr.send_input(cli_in)
                    continue
                elif msg_type == "clear_queue":
                    if hasattr(agent_mgr, "clear_queue"):
                        await agent_mgr.clear_queue()
                    continue
                elif msg_type == "promote_queue":
                    if hasattr(agent_mgr, "promote_queued_to_steer"):
                        await agent_mgr.promote_queued_to_steer()
                    continue
                elif msg_type == "ack":
                    seq = data.get("seq")
                    if seq is not None:
                        agent_mgr.handle_ack(seq)
                    continue
                elif msg_type in ("prompt", "steer", "queue_prompt"):
                    prompt = (data.get("prompt") or data.get("text") or "").strip()
                    model = data.get("model") or "gemini-3.8-flash-high"
                    conversation_id = data.get("conversation_id")
                    token = data.get("token")
                    req_mode = data.get("mode") or (
                        "steer" if msg_type == "steer" else ("queue" if msg_type == "queue_prompt" else "normal")
                    )
                    if token is not None:
                        init_token = str(token or "").strip()
                    curr_user, curr_slot_key = _resolve_ws_user_and_slot(init_token, init_cid)
                    user = curr_user
                    # Everyone except admins must accept the Terms & Privacy first (server-side check)
                    if not is_admin_role((curr_user or {}).get("role")) and not guest_session.terms_accepted(_ws_hdrs):
                        await _safe_send({"type": "system", "level": "error", "terms_required": True,
                                          "message": "Please accept the Terms & Privacy before using Siraugga (reload the page to see them)."})
                        continue
                    await agent_mgr.authenticate_client(client_queue, curr_slot_key)
                    if hasattr(agent_mgr, "set_task_context"):
                        agent_mgr.set_task_context(curr_slot_key)

                    if data.get("browser_key"):
                        accepted_ver = str(data.get("byok_terms_version") or "")
                        if accepted_ver != browser_key_relay.TERMS_VERSION:
                            await _safe_send({
                                "type": "byok_terms_required",
                                "terms_version": browser_key_relay.TERMS_VERSION,
                                "message": "Please review and accept the Bring Your Own Key terms before using your own API key."
                            })
                            continue
                        user = dict(user)
                        user["_browser_key"] = True
                        user["_byok_terms_version"] = accepted_ver
                        curr_user = user
                        if not getattr(ws, "_byok_terms_logged", False):
                            try:
                                ws._byok_terms_logged = True
                            except Exception:
                                pass
                            print(f"[BYOK] Terms v{accepted_ver} accepted by {curr_slot_key} at {time.strftime('%Y-%m-%dT%H:%M:%S')}")

                    is_role_admin = bool(user and is_admin_role(user.get("role")))
                    admin_override = is_role_admin or (os.environ.get("ADMIN_OVERRIDE", "false").lower() == "true")
            except (json.JSONDecodeError, AttributeError):
                prompt = str(raw_msg).strip()
                curr_user, curr_slot_key = _resolve_ws_user_and_slot(init_token, init_cid)
                user = curr_user
                if hasattr(agent_mgr, "set_task_context"):
                    agent_mgr.set_task_context(curr_slot_key)
                req_mode = "normal"
                admin_override = os.environ.get("ADMIN_OVERRIDE", "false").lower() == "true"

            if prompt:
                is_admin = bool(user and is_admin_role(user.get("role"))) or (os.environ.get("ADMIN_OVERRIDE", "false").lower() == "true")
                if not is_admin:
                    try:
                        from local_security import LocalSecurity
                        ls = LocalSecurity()
                        security_status = ls.analyze_intent(prompt)
                        if security_status == "ATTACK":
                            print("[Semantic Firewall] Dropping malicious prompt.")
                            await _safe_send({
                                "type": "agent_article",
                                "markdown": "> [!CAUTION] Semantic Firewall Active\n> Malicious intent or prompt injection detected. Your request has been blocked and dropped."
                            })
                            continue
                    except ImportError:
                        pass
                    except Exception as e:
                        print(f"[Security Firewall] Error parsing intent: {e}")

                is_running = agent_mgr.is_running(curr_slot_key) if hasattr(agent_mgr, "is_running") else False
                if is_running and locals().get("req_mode") != "queue":
                    if not prompt.startswith("[STEER_NOW]\n"):
                        prompt = f"[STEER_NOW]\n{prompt}"
                    req_mode = "steer"

                if locals().get("req_mode") == "queue" and hasattr(agent_mgr, "queue_prompt"):
                    clean_q = prompt[len("[QUEUE_NEXT]\n"):].strip() if prompt.startswith("[QUEUE_NEXT]\n") else prompt
                    await agent_mgr.queue_prompt(clean_q, model=model, conversation_id=conversation_id, user=user, admin_override=admin_override)
                elif locals().get("req_mode") == "steer" and hasattr(agent_mgr, "steer_task"):
                    clean_s = prompt[len("[STEER_NOW]\n"):].strip() if prompt.startswith("[STEER_NOW]\n") else prompt
                    await agent_mgr.steer_task(clean_s, model=model, conversation_id=conversation_id, user=user, admin_override=admin_override)
                else:
                    await agent_mgr.start_task(prompt, model=model, conversation_id=conversation_id, user=user, admin_override=admin_override)
    except asyncio.CancelledError:
        pass
    except Exception as e:
        import traceback
        traceback.print_exc()
        try:
            with open("ws_error.log", "a") as f:
                f.write(traceback.format_exc() + "\n")
        except Exception:
            pass
        print(f"WebSocket Error: {e}")
    finally:
        sender_task.cancel()
        await agent_mgr.unregister_client(client_queue)

_EXTRACT_RATE = {}
_EXTRACT_MAX_BYTES = 5 * 1024 * 1024
_EXTRACT_MAX_CHARS = 150_000


def _extract_document_text(name: str, data: bytes) -> str:
    import io
    ext = os.path.splitext(name.lower())[1]
    if ext == ".pdf":
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(data))
        return "\n\n".join((page.extract_text() or "") for page in reader.pages[:300])
    if ext == ".docx":
        import docx
        document = docx.Document(io.BytesIO(data))
        return "\n".join(p.text for p in document.paragraphs)
    if ext in (".txt", ".md", ".csv"):
        return data.decode("utf-8", "replace")
    raise ValueError("Unsupported file type. Use PDF, Word (.docx), text, Markdown or CSV.")


@app.route('/api/extract-text', methods=['POST'])
async def extract_document_text():
    """Any tier: turn an uploaded document into text for the user's own prompt. Nothing is stored."""
    who = _http_user_id()  # logged-in user or session-cookie guest, never the IP
    now = time.time()
    recent = [t for t in _EXTRACT_RATE.get(who, []) if now - t < 60]
    if len(recent) >= 10:
        return jsonify({"success": False, "error": "Too many uploads. Wait a minute and try again."}), 429
    _EXTRACT_RATE[who] = recent + [now]

    if (request.content_length or 0) > _EXTRACT_MAX_BYTES + 64 * 1024:
        return jsonify({"success": False, "error": "File too large (limit 5 MB)."}), 413
    files = await request.files
    upload = files.get("file")
    if not upload or not upload.filename:
        return jsonify({"success": False, "error": "No file received."}), 400
    data = upload.read(_EXTRACT_MAX_BYTES + 1)
    if len(data) > _EXTRACT_MAX_BYTES:
        return jsonify({"success": False, "error": "File too large (limit 5 MB)."}), 413
    name = os.path.basename(upload.filename)[:120]
    try:
        text = await asyncio.wait_for(asyncio.to_thread(_extract_document_text, name, data), timeout=30)
    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 415
    except asyncio.TimeoutError:
        return jsonify({"success": False, "error": "Reading the file took too long."}), 408
    except Exception:
        return jsonify({"success": False, "error": "Could not read this file."}), 422
    text = (text or "").strip()
    if not text:
        return jsonify({"success": False, "error": "No readable text found in this file (scanned images are not supported)."}), 422
    truncated = len(text) > _EXTRACT_MAX_CHARS
    return jsonify({"success": True, "name": name, "text": text[:_EXTRACT_MAX_CHARS], "truncated": truncated, "chars": min(len(text), _EXTRACT_MAX_CHARS)})


@app.route('/api/usage', methods=['GET'])
async def api_usage():
    """Public usage overview for the /usage chat command: shared model quotas plus the viewer's own daily prompts."""
    from agents import model_router, tier_limits
    # Both CLIs' own /usage readings, shared with the router (refreshed every 5 minutes)
    snap = await asyncio.get_event_loop().run_in_executor(None, lambda: model_router.usage_snapshot(wait=True))
    c = snap.get("claude") or {}
    claude = dict(c, available=bool(c))
    google = [{"group": g["group"], "period": g["period"], "remaining_pct": g["remaining_pct"],
               "resets": time.strftime("%a %d %b, %H:%M", time.localtime(g["reset_ts"]))}
              for g in snap.get("google", [])]
    out_now = model_router.status()
    models = []
    for name in model_router.configured_models():
        fam = model_router.family(name)
        entry = out_now.get(fam)
        back_at = (time.time() + entry["available_in_s"]) if entry else None
        models.append({"name": name, "status": "out" if entry else "available",
                       "back_at": time.strftime("%a %d %b, %H:%M", time.localtime(back_at)) if back_at else None})
    # The viewer's own allowance, identified the same way the chat counts it
    token = request.headers.get("Authorization", "").replace("Bearer ", "").strip()
    try:
        u = security_mgr.get_user_from_token(token or None, remote_addr=request.remote_addr, headers=request.headers)
    except Exception:
        u = None
    cid = (request.args.get("client_id") or "").strip()[:80]
    if not u:
        from security import guest_session
        u = {"username": guest_session.guest_username(request.headers), "name": "Guest", "role": "guest", "token_scope": "user"}
    u = dict(u)
    from agents import unlock_links
    u.update(_client_id=cid, _device_id=cid,
             _slot_key=f"{u.get('username')}::{cid}" if cid else u.get("username"),
             _unlimited=unlock_links.is_unlimited(request.headers))
    _ok, used, limit, tier = tier_limits.check_prompt(u)
    you = {"tier": tier, "tier_name": "Super Admin" if tier >= 5 else tier_limits.TIER_NAMES.get(tier, f"Tier {tier}"),
           "used": used, "limit": limit, "unlimited": tier >= 5 or limit is None, "unlocked_by_link": bool(u["_unlimited"])}
    # Daily limit of every tier (admin-configurable), for the Help menu's "Tiers" guide
    limits = tier_limits.load_limits()
    tiers = [{"tier": t, "name": tier_limits.TIER_NAMES[t], "limit": limits.get(t)} for t in sorted(tier_limits.TIER_NAMES)]
    return jsonify({"claude": claude, "google": google, "models": models, "you": you, "tiers": tiers, "exams_unlimited": True})


def _http_user_id() -> str:
    """Same identity the WebSocket uses: the logged-in username, else the guest session cookie (never the IP)."""
    token = request.headers.get("Authorization", "").replace("Bearer ", "").strip()
    try:
        user = security_mgr.get_user_from_token(token or None, remote_addr=request.remote_addr, headers=request.headers)
    except Exception:
        user = None
    if user:
        return user.get("username") or user.get("name") or "guest"
    from security import guest_session
    return guest_session.guest_username(request.headers)


@app.route('/api/exam-content', methods=['GET', 'POST'])
async def exam_content_folder():
    """Any tier: list or add files in the caller's own exam content folder."""
    from agents import exam_content
    user_id = _http_user_id()
    if request.method == "GET":
        return jsonify({"success": True, "files": exam_content.list_files(user_id), "max_files": exam_content.MAX_FILES})

    if (request.content_length or 0) > _EXTRACT_MAX_BYTES + 64 * 1024:
        return jsonify({"success": False, "error": "File too large (limit 5 MB)."}), 413
    files = await request.files
    upload = files.get("file")
    if not upload or not upload.filename:
        return jsonify({"success": False, "error": "No file received."}), 400
    data = upload.read(_EXTRACT_MAX_BYTES + 1)
    if len(data) > _EXTRACT_MAX_BYTES:
        return jsonify({"success": False, "error": "File too large (limit 5 MB)."}), 413
    name = os.path.basename(upload.filename)[:120]
    try:
        text = await asyncio.wait_for(asyncio.to_thread(_extract_document_text, name, data), timeout=30)
    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 415
    except Exception:
        return jsonify({"success": False, "error": "Could not read this file."}), 422
    if not (text or "").strip():
        return jsonify({"success": False, "error": "No readable text found in this file."}), 422
    try:
        item = await asyncio.to_thread(exam_content.add_file, user_id, name, text.strip())
    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 409
    return jsonify({"success": True, "file": item, "files": exam_content.list_files(user_id)})


@app.route('/api/exam-content/<file_id>', methods=['DELETE'])
async def exam_content_delete(file_id):
    from agents import exam_content
    user_id = _http_user_id()
    ok = await asyncio.to_thread(exam_content.delete_file, user_id, file_id)
    return jsonify({"success": ok, "files": exam_content.list_files(user_id)}), (200 if ok else 404)


# ---- Change-request tickets -------------------------------------------------------------
_TICKET_JOBS = set()


def _start_ticket_review(ticket_id: str) -> None:
    from agents import ticket_mail
    task = asyncio.create_task(asyncio.to_thread(ticket_mail.review_and_notify, ticket_id))
    _TICKET_JOBS.add(task)
    task.add_done_callback(_TICKET_JOBS.discard)


def _ticket_notify_submitter(t: dict) -> None:
    from agents import ticket_mail
    task = asyncio.create_task(asyncio.to_thread(ticket_mail.notify_submitter, t))
    _TICKET_JOBS.add(task)
    task.add_done_callback(_TICKET_JOBS.discard)


def _ticket_after_decision(t: dict) -> None:
    """Approved: DevCore's agent implements it (and tells everyone). Otherwise: tell the submitter."""
    from agents import ticket_mail
    if t.get("status") == "approved":
        task = asyncio.create_task(asyncio.to_thread(ticket_mail.implement_and_notify, t["id"]))
        _TICKET_JOBS.add(task)
        task.add_done_callback(_TICKET_JOBS.discard)
    else:
        _ticket_notify_submitter(t)


@app.route('/terms', methods=['GET'])
async def terms_page():
    """Terms & Privacy (every visitor accepts these before using DevCore)."""
    from security import guest_session
    page = read_asset("sandbox/templates/terms.html")
    if not page:
        return "Terms not found", 404
    rendered = await render_template_string(page.decode("utf-8"), version=guest_session.TERMS_VERSION)
    return rendered, 200, {"Content-Type": "text/html; charset=utf-8"}


@app.route('/api/terms', methods=['GET', 'POST'])
async def terms_accept():
    """GET: has this browser accepted the current terms? POST: accept them (sets an HttpOnly cookie)."""
    from security import guest_session
    if request.method == "GET":
        return jsonify({"accepted": guest_session.terms_accepted(request.headers), "version": guest_session.TERMS_VERSION})
    data = await request.get_json(silent=True) or {}
    if str(data.get("version") or "") != guest_session.TERMS_VERSION or data.get("agree") is not True:
        return jsonify({"success": False, "error": "Please tick the box to agree to the current terms."}), 400
    resp = jsonify({"success": True, "accepted": True, "version": guest_session.TERMS_VERSION})
    resp.set_cookie(guest_session.TERMS_COOKIE, guest_session.TERMS_VERSION, max_age=365 * 86400, path="/",
                    httponly=True, secure=_cookie_secure(), samesite=_cookie_samesite())
    return resp


@app.route('/api/tickets', methods=['GET', 'POST'])
async def tickets_mine():
    """Any tier: send a ticket, or list your own tickets with their status."""
    from agents import tickets, tier_limits
    from security import guest_session
    owner = _http_user_id()
    if request.method == "GET":
        return jsonify({"success": True, "tickets": tickets.list_for_owner(owner), "categories": tickets.CATEGORIES})
    data = await request.get_json(silent=True) or {}
    token = request.headers.get("Authorization", "").replace("Bearer ", "").strip()
    try:
        user = security_mgr.get_user_from_token(token or None, remote_addr=request.remote_addr, headers=request.headers)
    except Exception:
        user = None
    tier = tier_limits.get_tier_for_user(user or {"role": "guest"})
    if tier < 5 and not guest_session.terms_accepted(request.headers):
        return jsonify({"success": False, "terms_required": True,
                        "error": "Please accept the Terms & Privacy before sending a ticket."}), 403
    from agents import ticket_gate
    try:
        session_id = request.cookies.get(ticket_gate.SESSION_COOKIE, "")
        if tier <= 1 and not data.get("intake_id"):
            # Tier 1, step 1: a few questions about the visitor's goal before anything is created.
            # The questions are tied to this browser session (HttpOnly cookie; only its hash is kept).
            if not re.fullmatch(r"[A-Za-z0-9_-]{24,64}", session_id or ""):
                session_id = ticket_gate.new_session_id()
            intake = await asyncio.to_thread(ticket_gate.start, owner, tier, data.get("title"), data.get("description"),
                                             data.get("category"), data.get("email"), session_id)
            resp = jsonify({"success": True, "needs_answers": True, **intake})
            resp.set_cookie(ticket_gate.SESSION_COOKIE, session_id, max_age=ticket_gate.INTAKE_TTL, path="/",
                            httponly=True, secure=_cookie_secure(), samesite="Strict")
            return resp
        if tier <= 1:
            # Tier 1, step 2: the gate AI reads the ticket with the answers and accepts or refuses it
            t = await asyncio.to_thread(ticket_gate.finish, owner, data.get("intake_id"), data.get("answers"), session_id)
        else:
            t = await asyncio.to_thread(tickets.create, owner, tier, data.get("title"), data.get("description"),
                                        data.get("category"), data.get("email"))
    except ticket_gate.Refused as e:
        return jsonify({"success": False, "refused": True, "error": str(e)}), 422
    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    _start_ticket_review(t["id"])
    return jsonify({"success": True, "ticket": tickets.public_view(t), "tickets": tickets.list_for_owner(owner)})


@app.route('/api/tickets/intake/<intake_id>/exam', methods=['GET'])
async def tickets_intake_exam(intake_id):
    """The gate questionnaire (exam JSON) for the exam player; only for the browser session that sent the ticket."""
    from agents import ticket_gate
    exam = ticket_gate.get_exam(intake_id, request.cookies.get(ticket_gate.SESSION_COOKIE, ""))
    if not exam:
        return jsonify({"error": "Not found"}), 404
    return jsonify(exam), 200, {"Cache-Control": "no-store", "X-Robots-Tag": "noindex"}


# ---- Direct mode (Tier 5 Super Admin only): one live Claude Code session in a chat page -----
def _direct_client_ip(headers, addr):
    from security import guest_session
    return guest_session.connection_address(headers, addr)


def _direct_same_origin(headers) -> bool:
    """The websocket must be opened by our own page: blocks other websites from using the
    owner's trusted-device cookie to reach Direct mode (cross-site websocket hijacking)."""
    from urllib.parse import urlparse
    origin = (headers.get("Origin") or "").strip()
    if not origin:
        return False
    o_host = (urlparse(origin).netloc or "").lower()
    hosts = {(headers.get("Host") or "").lower(), (headers.get("X-Forwarded-Host") or "").lower()}
    return bool(o_host) and o_host in hosts


@app.route('/direct')
async def direct_mode_page():
    """The Direct mode chat page. The page itself holds no data; it only works after
    /api/direct/status and the /ws/direct websocket confirm the caller is the Super Admin."""
    template_bytes = read_asset("sandbox/templates/direct.html")
    if not template_bytes:
        return "Not found", 404
    return template_bytes.decode("utf-8"), 200, {"Content-Type": "text/html; charset=utf-8",
                                                 "Cache-Control": "no-store", "X-Robots-Tag": "noindex, nofollow"}


@app.route('/api/direct/status', methods=['GET'])
async def direct_mode_status():
    """Tier 5 only: may this caller use Direct mode?"""
    token = request.headers.get("Authorization", "").replace("Bearer ", "").strip()
    if not _artifact_admin_user(token):
        from agents import direct_session
        direct_session.audit("page_refused", ip=_direct_client_ip(request.headers, request.remote_addr))
        return jsonify({"allowed": False, "error": "Direct mode is only for the Super Admin."}), 403
    return jsonify({"allowed": True}), 200, {"Cache-Control": "no-store"}


@app.websocket("/ws/direct")
async def ws_direct():
    """Tier 5 only. First frame: {"type": "auth", "token": ...}. Then {"type": "send", "text"},
    {"type": "stop"} or {"type": "new"}. The Super Admin check is repeated on every frame and
    every minute while connected; failing it closes the socket."""
    import logging
    from agents import direct_session
    ws = websocket._get_current_object()
    addr = getattr(websocket, "remote_addr", None)
    hdrs = websocket.headers
    ip = _direct_client_ip(hdrs, addr)

    async def deny(reason):
        direct_session.audit("refused", ip=ip, detail=reason)
        try:
            await ws.send(json.dumps({"type": "denied", "text": "Direct mode is only for the Super Admin."}))
            await ws.close(1008)
        except Exception:
            pass

    if not _direct_same_origin(hdrs):
        return await deny("origin")
    try:
        first = json.loads(await asyncio.wait_for(ws.receive(), 20))
    except Exception:
        return await deny("no auth frame")
    token = str((first or {}).get("token") or "").strip() if isinstance(first, dict) else ""

    def owner():
        try:
            u = security_mgr.get_user_from_token(token or None, remote_addr=addr, headers=hdrs)
        except Exception:
            u = None
        return u if security_mgr.is_super_admin(u) else None

    user = owner()
    if not user or (first or {}).get("type") != "auth":
        return await deny("not super admin")
    who = str(user.get("username") or user.get("name") or "owner")
    sess = direct_session.get("owner")
    q = sess.subscribe()
    direct_session.audit("connected", who, ip)
    await ws.send(json.dumps(sess.snapshot()))
    revoked = asyncio.Event()

    async def sender():
        while True:
            try:
                ev = await asyncio.wait_for(q.get(), 60)
            except asyncio.TimeoutError:
                if not owner():
                    revoked.set()
                    return
                ev = {"type": "ping"}
            await ws.send(json.dumps(ev))

    sender_task = asyncio.create_task(sender())
    try:
        while not revoked.is_set():
            recv = asyncio.create_task(ws.receive())
            done, _ = await asyncio.wait({recv, sender_task}, return_when=asyncio.FIRST_COMPLETED)
            if recv not in done:
                recv.cancel()
                break
            raw = recv.result()
            if not owner():
                revoked.set()
                break
            try:
                data = json.loads(raw)
            except Exception:
                continue
            kind = data.get("type")
            if kind == "send":
                text = str(data.get("text") or "").strip()
                if not text:
                    continue
                direct_session.audit("message", who, ip, text[:4000])
                try:
                    await sess.send(text)
                except Exception as e:
                    logging.error(f"[DirectMode] send failed: {e}")
                    await ws.send(json.dumps({"type": "notice", "text": "Could not start Claude Code: " + str(e)[:300]}))
            elif kind == "stop":
                direct_session.audit("stop", who, ip)
                asyncio.create_task(sess.stop())
            elif kind == "new":
                direct_session.audit("new_session", who, ip)
                await sess.new_session()
    except asyncio.CancelledError:
        raise
    except Exception as e:
        logging.info(f"[DirectMode] socket closed: {e}")
    finally:
        sess.unsubscribe(q)
        sender_task.cancel()
        direct_session.audit("disconnected", who, ip)
    if revoked.is_set():
        await deny("access lost during session")


@app.route('/api/tickets/admin', methods=['GET'])
async def tickets_admin_list():
    """Tier 5 only: every ticket, with the review agent's assessment."""
    from agents import tickets
    token = request.headers.get("Authorization", "").replace("Bearer ", "").strip()
    if not _artifact_admin_user(token):
        return jsonify({"error": "Admin authorization required"}), 403
    from agents import ticket_impl
    all_tickets = tickets.list_all()
    # Re-run reviews that were cut off (e.g. by a server restart)
    for t in all_tickets:
        if t["status"] == "submitted" and time.time() - t["created"] > 600:
            _start_ticket_review(t["id"])
        # An implementation cut off by a restart: put it back to approved so it can be done by hand
        if t["status"] == "implementing" and ticket_impl.RUNNING["id"] != t["id"] and time.time() - t["updated"] > 60:
            await asyncio.to_thread(tickets.set_status, t["id"], "approved",
                                    "The automatic implementation was interrupted (server restart). Nothing went live.")
            all_tickets = tickets.list_all()
    from agents import ticket_gate
    return jsonify({"success": True, "tickets": all_tickets, "refused": ticket_gate.recent_refusals(20)})


@app.route('/api/tickets/admin/<ticket_id>', methods=['POST'])
async def tickets_admin_decide(ticket_id):
    """Tier 5 only: approve, decline, or mark an approved ticket implemented."""
    from agents import tickets
    token = request.headers.get("Authorization", "").replace("Bearer ", "").strip()
    admin = _artifact_admin_user(token)
    if not admin:
        return jsonify({"error": "Admin authorization required"}), 403
    data = await request.get_json(silent=True) or {}
    action = str(data.get("action") or "")
    try:
        if action == "undo":
            from agents import ticket_impl
            await asyncio.to_thread(ticket_impl.undo, ticket_id)
            t = tickets.get(ticket_id)
        else:
            t = await asyncio.to_thread(tickets.decide, ticket_id, action,
                                        admin.get("username") or "admin", "app", data.get("note"))
    except LookupError as e:
        return jsonify({"success": False, "error": str(e)}), 404
    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 409
    _ticket_after_decision(t)
    return jsonify({"success": True, "ticket": tickets.admin_view(t)})


def _ticket_page(title: str, body_html: str, status: int = 200):
    page = f"""<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta name="robots" content="noindex"><title>{_html.escape(title)}</title>
<style>body{{margin:0;background:#0a0a0b;color:#e2e8f0;font-family:-apple-system,'Segoe UI',Roboto,Arial,sans-serif;}}
main{{max-width:620px;margin:40px auto;padding:24px 16px;}}.card{{background:#10141d;border:1px solid rgba(45,212,191,.3);border-radius:10px;padding:24px;}}
h1{{color:#fff;font-size:22px;margin:0 0 12px}}.kicker{{font:12px monospace;color:#2dd4bf;text-transform:uppercase;letter-spacing:1px}}
.desc{{white-space:pre-wrap;background:rgba(255,255,255,.03);border:1px solid rgba(255,255,255,.1);border-radius:6px;padding:12px;margin:12px 0}}
label{{display:block;font-size:14px;margin:14px 0 6px}}textarea{{width:100%;box-sizing:border-box;min-height:70px;background:#0b0f16;color:#e2e8f0;border:1px solid #334155;border-radius:6px;padding:8px;font:inherit}}
button{{margin-top:16px;padding:12px 26px;font-size:16px;font-weight:bold;color:#fff;border:0;border-radius:6px;cursor:pointer}}
.approve{{background:#16a34a}}.decline{{background:#dc2626}}button:focus{{outline:3px solid #2dd4bf;outline-offset:2px}}a{{color:#2dd4bf}}</style></head>
<body><main><div class="card">{body_html}</div></main></body></html>"""
    return page, status, {"Content-Type": "text/html; charset=utf-8", "Cache-Control": "no-store", "X-Robots-Tag": "noindex"}


@app.route('/tickets/decide', methods=['GET', 'POST'])
async def tickets_email_decide():
    """One-click link from the admin email. GET shows the ticket and a confirm button (so link
    scanners that open email links can't decide by accident); POST records the decision."""
    from agents import tickets
    src = (await request.form) if request.method == "POST" else request.args
    tid, action, exp, sig = src.get("id", ""), src.get("a", ""), src.get("exp", ""), src.get("sig", "")
    if not tickets.verify_link(tid, action, exp, sig):
        return _ticket_page("Link not valid", "<h1>This link isn't valid</h1><p>It may have expired (links last 14 days) or been changed. "
                            "Tier-5 users can still decide in Settings &amp; Sessions → Ticket queue.</p>", 403)
    t = tickets.get(tid)
    if not t:
        return _ticket_page("Ticket not found", "<h1>Ticket not found</h1>", 404)
    if action == "undo":
        return await _ticket_undo_page(t, tid, exp, sig)
    verb = "Approve" if action == "approve" else "Decline"
    if request.method == "GET":
        if t["status"] != "awaiting_approval":
            label = tickets.STATUS_TEXT.get(t["status"], (t["status"],))[0]
            return _ticket_page("Already decided", f"<p class='kicker'>{_html.escape(t['id'])}</p><h1>{_html.escape(t['title'])}</h1>"
                                f"<p>This ticket is already <strong>{_html.escape(label)}</strong>. Nothing more to do.</p>")
        review = t.get("review") or {}
        body = (f"<p class='kicker'>{_html.escape(t['id'])} · {verb} this ticket?</p><h1>{_html.escape(t['title'])}</h1>"
                f"<div class='desc'>{_html.escape(t['description'])}</div>"
                f"<p><strong>Review agent:</strong> {_html.escape(review.get('risk', '?'))} risk, recommends "
                f"{_html.escape(review.get('recommendation', '?'))}. {_html.escape(review.get('reason', ''))}</p>"
                f"<form method='post' action='/tickets/decide'>"
                + "".join(f"<input type='hidden' name='{k}' value='{_html.escape(str(v))}'>" for k, v in
                          (("id", tid), ("a", action), ("exp", exp), ("sig", sig)))
                + f"<label for='note'>Note for the person who sent it (optional)</label><textarea id='note' name='note' maxlength='500'></textarea>"
                f"<button type='submit' class='{action}'>{'✅' if action == 'approve' else '❌'} Confirm: {verb}</button></form>")
        return _ticket_page(f"{verb} ticket {t['id']}", body)
    try:
        t = await asyncio.to_thread(tickets.decide, tid, action, "admin (email link)", "email", src.get("note", ""))
    except ValueError as e:
        return _ticket_page("Already decided", f"<h1>Nothing changed</h1><p>{_html.escape(str(e))}</p>", 409)
    _ticket_after_decision(t)
    done = ("Approved. Siraugga's agent is making the change now and it goes live as soon as it's done. "
            "You'll get an email showing exactly what changed, with a one-click Undo button."
            if action == "approve" else "Declined. The person who sent it has been told.")
    return _ticket_page(f"Ticket {verb.lower()}d", f"<p class='kicker'>{_html.escape(t['id'])}</p><h1>{_html.escape(t['title'])}</h1><p>{done}</p>"
                        f"<p><a href='/'>Open Siraugga</a></p>")


async def _ticket_undo_page(t: dict, tid: str, exp: str, sig: str):
    """Undo link from the 'Live now' email: GET confirms, POST restores the previous files."""
    from agents import tickets, ticket_impl
    impl = t.get("implementation") or {}
    head = f"<p class='kicker'>{_html.escape(t['id'])} · Undo</p><h1>{_html.escape(t['title'])}</h1>"
    if request.method == "GET":
        if t["status"] != "implemented" or not impl.get("files"):
            label = tickets.STATUS_TEXT.get(t["status"], (t["status"],))[0]
            return _ticket_page("Nothing to undo", head + f"<p>This ticket is <strong>{_html.escape(label)}</strong>, so there's nothing to undo.</p>")
        files = "".join(f"<li><code>{_html.escape(f)}</code></li>" for f in impl["files"])
        body = (head + f"<p>This puts these files back the way they were before the agent's change:</p><ul>{files}</ul>"
                f"<div class='desc'>{_html.escape(impl.get('summary', ''))}</div>"
                "<form method='post' action='/tickets/decide'>"
                + "".join(f"<input type='hidden' name='{k}' value='{_html.escape(str(v))}'>" for k, v in
                          (("id", tid), ("a", "undo"), ("exp", exp), ("sig", sig)))
                + "<button type='submit' class='decline'>↩️ Confirm: Undo the change</button></form>")
        return _ticket_page(f"Undo ticket {t['id']}", body)
    try:
        res = await asyncio.to_thread(ticket_impl.undo, tid)
    except ValueError as e:
        return _ticket_page("Nothing to undo", head + f"<p>{_html.escape(str(e))}</p>", 409)
    _ticket_notify_submitter(tickets.get(tid))
    msg = f"<p>Done. {len(res['restored'])} file(s) are back to how they were. The change is no longer live.</p>"
    if res["skipped"]:
        msg += ("<p>These files were changed again after the agent's change, so they were left alone: "
                + ", ".join(f"<code>{_html.escape(f)}</code>" for f in res["skipped"]) + "</p>")
    return _ticket_page("Change undone", head + msg + "<p><a href='/'>Open Siraugga</a></p>")


# ---- Reusable "no limit" links -----------------------------------------------------------
_UNLOCK_REASONS = {"full": "This link has reached its limit of browsers.", "expired": "This link has expired.",
                   "revoked": "This link was turned off by the admin.", "invalid": "This link isn't valid."}


@app.route('/unlock/<code>', methods=['GET'])
async def unlock_link(code):
    """Opens the normal site; the page shows a one-time popup for the link (see /api/unlock)."""
    from urllib.parse import quote
    return "", 302, {"Location": "/?unlock=" + quote(code[:64], safe=""), "Cache-Control": "no-store", "X-Robots-Tag": "noindex"}


@app.route('/api/unlock', methods=['GET', 'POST'])
async def unlock_api():
    """GET ?code=: what the popup should say. POST {code}: use the link and set the no-limit cookie.
    Using it needs the popup's button press, so link previews and scanners can't use it up."""
    from agents import unlock_links
    if unlock_links.is_unlimited(request.headers):
        return jsonify({"state": "already_unlimited"})
    if request.method == "GET":
        st = unlock_links.status(request.args.get("code", ""))
        return jsonify({"state": st, "message": _UNLOCK_REASONS.get(st, "")})
    data = await request.get_json(silent=True) or {}
    token = unlock_links.claim(str(data.get("code") or ""))
    if not token:
        st = unlock_links.status(str(data.get("code") or ""))
        return jsonify({"state": st, "message": _UNLOCK_REASONS.get(st, "This link can't be used.")}), 410
    print("[Unlock] A no-limit link was used.")
    resp = jsonify({"state": "unlocked"})
    resp.headers["Set-Cookie"] = f"{unlock_links.COOKIE_NAME}={token}; Max-Age={unlock_links.COOKIE_MAX_AGE}; Path=/; HttpOnly; Secure; SameSite=Lax"
    return resp


@app.route('/api/admin/unlock-links', methods=['GET', 'POST'])
async def admin_unlock_links():
    """Tier 5 only: create a reusable no-limit link, or list them."""
    from agents import unlock_links
    token = request.headers.get("Authorization", "").replace("Bearer ", "").strip()
    if not _artifact_admin_user(token):
        return jsonify({"error": "Admin authorization required"}), 403
    if request.method == "POST":
        data = await request.get_json(silent=True) or {}
        link = unlock_links.create(data.get("label", ""), int(data.get("days") or unlock_links.DEFAULT_TTL_DAYS))
        return jsonify({"success": True, "url": link["url"], "links": unlock_links.list_links()})
    return jsonify({"success": True, "links": unlock_links.list_links()})


@app.route('/api/admin/unlock-links/<link_id>', methods=['DELETE'])
async def admin_unlock_link_revoke(link_id):
    """Tier 5 only: turn a link off (also ends unlimited access for every browser that used it)."""
    from agents import unlock_links
    token = request.headers.get("Authorization", "").replace("Bearer ", "").strip()
    if not _artifact_admin_user(token):
        return jsonify({"error": "Admin authorization required"}), 403
    ok = unlock_links.revoke(link_id)
    return jsonify({"success": ok, "links": unlock_links.list_links()}), (200 if ok else 404)


@app.route('/api/admin/tier-limits', methods=['GET', 'POST'])
async def admin_tier_limits():
    """Super-admin only: daily prompt limits per tier for users running on the host subscription."""
    from agents import tier_limits
    token = request.headers.get("Authorization", "").replace("Bearer ", "").strip()
    if not _artifact_admin_user(token):
        return jsonify({"error": "Admin authorization required"}), 403
    if request.method == "POST":
        data = await request.get_json(silent=True) or {}
        raw = data.get("limits")
        if not isinstance(raw, dict):
            return jsonify({"success": False, "error": "Send {\"limits\": {\"1\": 10, \"2\": 30, ...}} (null = no limit)."}), 400
        try:
            saved = tier_limits.save_limits(raw)
        except Exception as e:
            return jsonify({"success": False, "error": f"Could not save the limits: {e}"}), 400
        print(f"[TierLimits] Updated by admin: {saved}")
    limits = tier_limits.load_limits()
    return jsonify({
        "success": True,
        "tiers": [{"tier": t, "name": tier_limits.TIER_NAMES[t], "limit": limits.get(t)} for t in sorted(tier_limits.TIER_NAMES)],
        "today": tier_limits.usage_summary(),
    })


@app.route('/api/admin/demo-key', methods=['GET', 'POST', 'DELETE'])
async def admin_demo_key():
    """Owner-only: set, check or remove the shared demo Gemini key from the Settings panel."""
    token = request.headers.get("Authorization", "").replace("Bearer ", "").strip()
    if not _artifact_admin_user(token):
        return jsonify({"error": "Admin authorization required"}), 403
    key_file = browser_key_relay.DEMO_KEY_FILE

    if request.method == "GET":
        usage = browser_key_relay._DEMO_USAGE
        today = time.strftime("%Y-%m-%d")
        return jsonify({
            "configured": bool(browser_key_relay.demo_server_key()),
            "used_today": usage["count"] if usage["day"] == today else 0,
            "daily_limit": browser_key_relay.demo_daily_limit(),
        })

    if request.method == "DELETE":
        try:
            if os.path.exists(key_file):
                os.remove(key_file)
        except Exception as e:
            return jsonify({"success": False, "error": f"Could not remove the key: {e}"}), 500
        return jsonify({"success": True})

    data = await request.get_json(silent=True) or {}
    key = str(data.get("key") or "").strip()
    if not key or len(key) > 200 or any(c.isspace() for c in key):
        return jsonify({"success": False, "error": "Paste a Gemini API key (it usually starts with AIza)."}), 400
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            check = await client.get("https://generativelanguage.googleapis.com/v1beta/models",
                                     params={"pageSize": 1}, headers={"x-goog-api-key": key})
        if check.status_code != 200:
            msg = "Google rejected this key."
            try:
                msg = check.json().get("error", {}).get("message") or msg
            except Exception:
                pass
            return jsonify({"success": False, "error": msg}), 400
    except Exception as e:
        return jsonify({"success": False, "error": f"Could not reach Google to check the key: {type(e).__name__}"}), 502
    try:
        os.makedirs(os.path.dirname(key_file), mode=0o700, exist_ok=True)
        tmp = key_file + ".tmp"
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(key)
        os.replace(tmp, key_file)
    except Exception as e:
        return jsonify({"success": False, "error": f"Could not save the key: {e}"}), 500
    print(f"[DemoKey] Shared demo key updated at {time.strftime('%Y-%m-%dT%H:%M:%S')}")
    return jsonify({"success": True})


@app.route('/internal/llm-relay/<token>/v1beta/models/<path:model_method>', methods=['POST'])
async def browser_key_llm_relay(token, model_method):
    """Loopback-only endpoint that `agy` calls instead of Google when a guest's key lives in their browser."""
    from quart import Response

    def _gerr(code, status, message):
        return jsonify({"error": {"code": code, "status": status, "message": message}}), code

    remote = (request.remote_addr or "").strip()
    proxied = any(request.headers.get(h) for h in ("CF-Connecting-IP", "CF-Ray", "X-Forwarded-For", "X-Real-IP"))
    if remote not in ("127.0.0.1", "::1", "localhost") or proxied:
        return _gerr(403, "PERMISSION_DENIED", "Forbidden")
    if not browser_key_relay.session_slot(token):
        return _gerr(404, "NOT_FOUND", "Unknown relay session")
    parsed = browser_key_relay.split_model_method(model_method)
    if not parsed:
        return _gerr(400, "INVALID_ARGUMENT", "Unsupported model or method")
    model_name, method_name = parsed

    body_text = (await request.get_data()).decode("utf-8", "replace")

    server_key = browser_key_relay.session_server_key(token)
    if server_key:
        # Shared demo key: the server attaches it and calls Google itself, so the agent never holds it.
        if not browser_key_relay.take_demo_request():
            return _gerr(429, "RESOURCE_EXHAUSTED", "The shared demo has reached its daily limit. Add your own Gemini key in Settings & Sessions to keep going.")
        upstream_url = f"{browser_key_relay.GOOGLE_API_BASE}/{model_name}:{method_name}"
        q = browser_key_relay.safe_query(request.args)
        client = httpx.AsyncClient(timeout=httpx.Timeout(connect=15.0, read=browser_key_relay.IDLE_TIMEOUT, write=60.0, pool=15.0))
        try:
            upstream_req = client.build_request(
                "POST", upstream_url, params=q, content=body_text.encode("utf-8"),
                headers={"Content-Type": "application/json", "x-goog-api-key": server_key},
            )
            upstream = await client.send(upstream_req, stream=True)
        except Exception as e:
            await client.aclose()
            return _gerr(502, "UNAVAILABLE", f"Could not reach Google: {type(e).__name__}")

        async def _upstream_stream():
            try:
                async for chunk in upstream.aiter_raw():
                    yield chunk
            finally:
                await upstream.aclose()
                await client.aclose()

        resp = Response(_upstream_stream(), status=upstream.status_code,
                        content_type=upstream.headers.get("content-type", "application/json"))
        resp.timeout = None
        return resp

    try:
        rid, queue = await browser_key_relay.open_request(
            agent_mgr, token, model_name, method_name, browser_key_relay.safe_query(request.args), body_text
        )
    except LookupError as e:
        return _gerr(503, "UNAVAILABLE", str(e))

    try:
        first = await asyncio.wait_for(queue.get(), browser_key_relay.FIRST_BYTE_TIMEOUT)
    except asyncio.TimeoutError:
        browser_key_relay.close_request(rid)
        return _gerr(504, "DEADLINE_EXCEEDED", "Your browser did not answer the model request in time.")
    if first.get("kind") != "start":
        browser_key_relay.close_request(rid)
        return _gerr(502, "UNAVAILABLE", str(first.get("error") or "Browser relay failed"))

    async def _stream():
        try:
            while True:
                item = await asyncio.wait_for(queue.get(), browser_key_relay.IDLE_TIMEOUT)
                if item.get("kind") == "chunk":
                    yield item["data"].encode("utf-8")
                elif item.get("kind") == "end":
                    break
        except asyncio.TimeoutError:
            pass
        finally:
            browser_key_relay.close_request(rid)

    resp = Response(_stream(), status=first["status"], content_type=first["content_type"])
    resp.timeout = None
    return resp

@app.route('/api/sounds/<sound_name>')
async def play_sound(sound_name):
    from quart import send_file
    
    sounds_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "sandbox", "static", "sounds")
    
    for ext in ['.wav', '.mp3', '.ogg']:
        file_path = os.path.join(sounds_dir, f"{sound_name}{ext}")
        if os.path.exists(file_path):
            return await send_file(file_path)
    
    return jsonify({"error": f"No custom {sound_name} audio file found in {sounds_dir}"}), 404

async def trigger_dast_scan_internal():
    """Triggers the Red Team ZAP Docker scan natively."""
    await agent_mgr.broadcast({
        "type": "system",
        "level": "warning",
        "message": "🔴 ACTIVE SPEAR: Initiating internal Red Team DAST strike..."
    })
    
    scanner_path = r"C:\Users\michael\Documents\scanners\scanner.py"
    cmd = ["python3", scanner_path, "--dast", "http://host.docker.internal:5000"]
    
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=r"C:\Users\michael\Documents\scanners"
        )
    except Exception as e:
        print(f"[DAST] Failed to launch Red Team engine: {e}")

async def auto_red_team_daemon():
    """Biological clock: Wakes up every 12 hours to strike the server."""
    while True:
        await asyncio.sleep(43200)
        await trigger_dast_scan_internal()

import signal

def force_shutdown(sig, frame):
    print("\n[Antigravity] Force quitting server (bypassing asyncio graceful shutdown)...")
    os._exit(0)

@app.route('/api/plugin/tts', methods=['POST'])
async def plugin_tts():
    try:
        data = await request.get_json()
        text = data.get("text", "")
        if not text:
            return jsonify({"error": "No text provided"}), 400
            
        import sys
        import os
        sys.path.append(os.path.abspath("plugins"))
        import tts_proxy
        from quart import Response
        
        ui_config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ui_config.json")
        
        audio_content, status_code = tts_proxy.generate_audio(text, ui_config_path)
        
        if status_code == 200:
            return Response(audio_content, mimetype="audio/mpeg")
        else:
            return jsonify(audio_content), status_code
            
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/proxy/<path:subpath>', methods=['GET', 'POST', 'PUT', 'DELETE', 'PATCH'])
async def proxy_gemini(subpath):
    """
    Intercepts the Agent's API calls, replaces the dummy token with the true root 
    vault key, and forwards it to Google. The Agent never sees the real key.
    """
    real_api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not real_api_key:
        client_key_path = os.path.expanduser("~/.devcore_client_key.txt")
        if os.path.exists(client_key_path):
            try:
                with open(client_key_path, "r", encoding="utf-8") as f:
                    real_api_key = f.read().strip()
            except Exception:
                pass
                
    if not real_api_key:
        return jsonify({"error": "No root billing key configured on server."}), 500

    target_url = f"https://generativelanguage.googleapis.com/{subpath}"
    
    headers = dict(request.headers)
    headers.pop("Host", None)
    
    if headers.get("x-goog-api-key") == "dummy_token_123":
        headers["x-goog-api-key"] = real_api_key
        
    query_params = dict(request.args)
    if query_params.get("key") == "dummy_token_123":
        query_params["key"] = real_api_key

    body = await request.get_data()
    
    async with httpx.AsyncClient() as client:
        resp = await client.request(
            method=request.method,
            url=target_url,
            headers=headers,
            params=query_params,
            content=body,
            timeout=180.0
        )
        
    from quart import Response
    return Response(resp.content, status=resp.status_code, headers=dict(resp.headers))

if __name__ == '__main__':
    import signal
    def force_shutdown(sig, frame):
        import os
        print('\n[Antigravity] Force quitting...')
        os._exit(0)
    signal.signal(signal.SIGINT, force_shutdown)
    try:
        from core.bootstrap_gateway import run_preflight_checks
        run_preflight_checks(spawn_agent=False, exit_on_failure=True)
    except Exception as preflight_err:
        print(f"[Bootstrap] Pre-flight check warning: {preflight_err}")
    print('Starting Antigravity Backend Engine on port 5000...')
    import asyncio
    from hypercorn.config import Config
    from hypercorn.asyncio import serve
    config = Config()
    
    import os
    devcore_root = os.path.dirname(BASE_DIR)
    cert_path = os.path.join(devcore_root, "cert.pem")
    key_path = os.path.join(devcore_root, "key.pem")
    if not (os.path.exists(cert_path) and os.path.exists(key_path)):
        cert_path = os.path.join(os.getcwd(), "cert.pem")
        key_path = os.path.join(os.getcwd(), "key.pem")
    if os.path.exists(cert_path) and os.path.exists(key_path):
        config.certfile = cert_path
        config.keyfile = key_path
        config.bind = ['0.0.0.0:5001', '[::1]:5001']
        config.insecure_bind = ['0.0.0.0:5000', '[::1]:5000']
    else:
        config.bind = ['0.0.0.0:5000', '[::1]:5000']
        
    # CyberBrief newsletter backend (moved from e-profile) is mounted on its own paths;
    # if it fails to load, DevCore still starts without it.
    asgi_entry = app
    try:
        from services.cyberbrief.app import mount as _mount_cyberbrief
        asgi_entry = _mount_cyberbrief(app)
        print('[CyberBrief] Newsletter backend mounted.')
    except Exception as cyberbrief_err:
        print(f'[CyberBrief] Not mounted: {cyberbrief_err}')
    # e-profile backend (login, admin, projects) runs as its own local process; requests
    # from the e-profile Pages proxy (secret header) are streamed to it.
    try:
        from services import eprofile_bridge
        from services.cyberbrief.app import owns as _cyberbrief_owns
        if eprofile_bridge.SECRET:
            asgi_entry = eprofile_bridge.mount(asgi_entry, owns_path=_cyberbrief_owns)
            print(f'[e-profile] Bridge to 127.0.0.1:{eprofile_bridge.PORT} mounted.')
        else:
            print('[e-profile] Bridge not mounted: no PROXY_SECRET in services/eprofile_bridge/.env')
    except Exception as bridge_err:
        print(f'[e-profile] Bridge not mounted: {bridge_err}')
    asyncio.run(serve(asgi_entry, config))
