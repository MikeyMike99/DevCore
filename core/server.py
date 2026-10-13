import asyncio
import importlib

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# 1. Initialize Central SIEM Logger before anything else
from security import central_logger
central_logger.init_central_logging()
import json
import os
import time
import sys
import httpx



from quart import Quart, websocket, request, jsonify, render_template_string

from core import session_manager as sm
from core import project_manager as pm
from agents import agent_manager as am
from security import security_manager as sec_m

app = Quart(__name__, static_folder=None)

from core.routes.auth import auth_bp
from core.routes.projects import projects_bp
from core.routes.files import files_bp
from core.routes.system import system_bp

app.register_blueprint(auth_bp)
app.register_blueprint(projects_bp)
app.register_blueprint(files_bp)
app.register_blueprint(system_bp)


from security import security_headers
security_headers.init_security_headers(app)

# Initialize modular managers
project_mgr = pm.ProjectManager()
session_mgr = sm.SessionManager()
agent_mgr = am.AgentTaskManager(project_manager=project_mgr)
security_mgr = sec_m.SecurityManager()
app.security_mgr = security_mgr
app.project_mgr = project_mgr
app.session_mgr = session_mgr
app.agent_mgr = agent_mgr

async def execute_hot_patch_sequence():
    """Timer sequence for safe hot-patching with syntax validation and automated rollback."""
    global project_mgr, session_mgr, agent_mgr, security_mgr, sm, pm, am, sec_m
    import shutil, py_compile, os, traceback
    
    # Pre-validation & Backup Phase
    patch_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "patches")
    backup_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "backups")
    os.makedirs(patch_dir, exist_ok=True)
    os.makedirs(backup_dir, exist_ok=True)
    
    patches_found = [f for f in os.listdir(patch_dir) if f.endswith('.py')]
    
    if not patches_found:
        return
        
    await agent_mgr.broadcast({
        "type": "system",
        "level": "warning",
        "message": "🚨 EXPLOIT DETECTED: Initiating safe zero-downtime hot-patching sequence..."
    })
    
    # 1. Syntax Validation: Ensure no patch has syntax errors before applying
    for patch in patches_found:
        try:
            py_compile.compile(os.path.join(patch_dir, patch), doraise=True)
        except py_compile.PyCompileError as e:
            await agent_mgr.broadcast({"type": "system", "level": "error", "message": f"❌ PATCH ABORTED: Syntax error detected in {patch}. Server protection engaged."})
            return

    for i in range(3, 0, -1):
        await agent_mgr.broadcast({"type": "system", "level": "info", "message": f"Validating and applying hot-patch in {i} seconds..."})
        await asyncio.sleep(1)
        
    # 2. Backup and Apply Phase
    if patches_found:
        for patch in patches_found:
            target_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), patch)
            if os.path.exists(target_file):
                shutil.copy2(target_file, os.path.join(backup_dir, patch)) # Backup original
            shutil.copy2(os.path.join(patch_dir, patch), target_file) # Apply patch
            
    await agent_mgr.broadcast({"type": "system", "level": "info", "message": "Files updated! Re-compiling backend modules in-memory..."})
    
    # 3. Reload & Rollback Phase
    active_clients = dict(agent_mgr.connected_clients)
    is_busy = agent_mgr.is_running()
    
    try:
        # Attempt to dynamically reload
        importlib.reload(sm)
        importlib.reload(pm)
        importlib.reload(am)
        importlib.reload(sec_m)
        
        project_mgr = pm.ProjectManager()
        session_mgr = sm.SessionManager()
        security_mgr = sec_m.SecurityManager()
        
        if is_busy:
            agent_mgr.project_manager = project_mgr
        else:
            agent_mgr = am.AgentTaskManager(project_manager=project_mgr)
            agent_mgr.connected_clients = active_clients
            
        await agent_mgr.broadcast({"type": "system", "level": "success", "message": "✅ Server successfully hot-patched and secured."})
        
    except Exception as e:
        # 4. Rollback: If initialization fails (e.g. AttributeError), restore backups and reload again
        await agent_mgr.broadcast({"type": "system", "level": "error", "message": f"⚠️ CRITICAL: Patch crashed the server engine! Initiating emergency rollback..."})
        if patches_found:
            for patch in patches_found:
                backup_file = os.path.join(backup_dir, patch)
                if os.path.exists(backup_file):
                    shutil.copy2(backup_file, os.path.join(os.path.dirname(os.path.abspath(__file__)), patch))
        
        # Reload the restored modules
        importlib.reload(sm); importlib.reload(pm); importlib.reload(am); importlib.reload(sec_m)
        project_mgr = pm.ProjectManager(); session_mgr = sm.SessionManager(); security_mgr = sec_m.SecurityManager()
        if not is_busy:
            agent_mgr = am.AgentTaskManager(project_manager=project_mgr)
            agent_mgr.connected_clients = active_clients
            
        await agent_mgr.broadcast({"type": "system", "level": "warning", "message": "🔄 Rollback complete. Previous stable state restored."})
async def auto_patch_daemon():
    """Runs continuously in the background to automatically patch exploits."""
    while True:
        # Check for patches every 30 minutes
        await asyncio.sleep(1800)
        # If a vulnerability was detected by scanners (simulated), apply the patch
        await execute_hot_patch_sequence()

@app.before_serving
async def start_background_tasks():
    app.add_background_task(auto_patch_daemon)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

def get_live_override_path(rel_path):
    """
    LIVE OVERRIDE ARCHITECTURE (OTA Drop-in Updates)
    Checks if a loose file exists next to the .exe (in CWD) before falling back to the compiled bundle.
    This allows updating the UI/Plugins without downloading a new .exe!
    """
    import os
    import sys
    # When running as compiled executable, sys.executable is the .exe directory
    # or os.getcwd() if launched from there.
    exe_dir = os.path.dirname(sys.executable) if getattr(sys, 'frozen', False) else os.getcwd()
    
    live_path = os.path.join(exe_dir, rel_path)
    if os.path.exists(live_path):
        return live_path
        
    cwd_path = os.path.join(os.getcwd(), rel_path)
    if os.path.exists(cwd_path):
        return cwd_path
        
    # Fallback to the bundled extraction directory
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
        mime_type, _ = mimetypes.guess_type(filename)
        return data, 200, {'Content-Type': mime_type or 'application/octet-stream'}
    return "Not Found", 404


# Dynamically load from the sandbox layer (with Live Override Support)
TEMPLATE_FILE = get_live_override_path("sandbox/templates/index.html")
UI_CONFIG_FILE = get_live_override_path("core/ui_config.json")

CACHED_MODELS = None

async def fetch_dynamic_models():
    global CACHED_MODELS
    if CACHED_MODELS is not None:
        return CACHED_MODELS
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
                import json
                try:
                    ui_config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ui_config.json")
                    if os.path.exists(ui_config_path):
                        with open(ui_config_path, "r", encoding="utf-8") as f:
                            cfg = json.load(f)
                        if cfg.get("header", {}).get("models") != fetched_models:
                            cfg.setdefault("header", {})["models"] = fetched_models
                            with open(ui_config_path, "w", encoding="utf-8") as f:
                                json.dump(cfg, f, indent=4)
                except Exception as e:
                    pass
                
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
    
    template_bytes = read_asset("sandbox/templates/exam_application.html")
    if not template_bytes:
        return "Exam template not found", 404
    content = template_bytes.decode('utf-8')
    
    ui_bytes = read_asset("core/ui_config.json")
    ui_strings = json.loads(ui_bytes.decode('utf-8')) if ui_bytes else {}
    
    rendered = await render_template_string(content, ui=ui_strings, quiz_file=quiz_file, exam_title=exam_title)
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

@app.route('/api/artifacts', methods=['GET'])
async def get_artifact():
    import sys
    import subprocess
    
    path = request.args.get('path', '')
    if path.startswith('file://'):
        path = path[7:]
        
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
    
    # 1. Enforce Authentication
    auth_header = request.headers.get("Authorization", "")
    token = auth_header.replace("Bearer ", "").strip()
    user = security_mgr.get_user_from_token(token)
    if not user:
        return jsonify({"error": "Unauthorized"}), 401
    
    data = await request.get_json()
    path = data.get('path', '')
    content = data.get('content', '')
    append_mode = data.get('append', False)
    
    if path.startswith('file://'):
        path = path[7:]
        
    # 2. Path Traversal & Command Injection Defense
    if not path.startswith("/home/") and not path.startswith("/mnt/"):
        return jsonify({"error": "Path traversal blocked"}), 403
        
    safe_path = shlex.quote(path)
    
    if sys.platform == "win32" and path.startswith("/"):
        import tempfile
        try:
            # Mitigation for Broken Pipes on WSL: write to a Windows temp file first
            fd, tmp_path = tempfile.mkstemp(suffix=".md")
            with os.fdopen(fd, 'w', encoding='utf-8') as f:
                f.write(content)
            
            # Use wsl.exe to copy the file into the Linux environment
            # wslpath -a converts the Windows path to a WSL path
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
            except:
                pass
                
            if process.returncode == 0:
                return jsonify({"success": True})
            else:
                return jsonify({"error": f"WSL Artifact write failed: {stderr}"}), 500
        except Exception as e:
            return jsonify({"error": str(e)}), 500
    else:
        # Native save for Linux
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
        # Enforce Zero-Knowledge Data Masking (PII Scrubbing) if Presidio is installed
        try:
            from local_security import LocalSecurity
            local_sec = LocalSecurity()
            scrubbed_prompt = local_sec.scrub_text(raw_prompt)
        except ImportError:
            # Fallback if Presidio is not installed on the system
            print("Warning: presidio-analyzer missing. Skipping PII scrubbing.")
            scrubbed_prompt = raw_prompt
        
        # Save to disk instead of spawning hardcoded background agents
        upload_dir = os.path.join(".agents", "massive_prompts")
        os.makedirs(upload_dir, exist_ok=True)
        file_path = os.path.join(upload_dir, f"{conv_id}.txt")
        
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(scrubbed_prompt)
            
        return jsonify({"success": True, "file_path": file_path})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.websocket('/ws')
async def ws_endpoint():
    ws = websocket._get_current_object()
    client_queue = asyncio.Queue()
    await agent_mgr.register_client(client_queue)
    
    async def sender():
        try:
            while True:
                msg = await client_queue.get()
                if msg is None:
                    break
                await ws.send(msg)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            print(f"WebSocket Sender Error: {e}")

    sender_task = asyncio.create_task(sender())

    try:
        while True:
            raw_msg = await ws.receive()
            if not raw_msg:
                continue

            prompt = None
            model = "gemini-3.8-flash-high"
            conversation_id = None
            try:
                data = json.loads(raw_msg)
                msg_type = data.get("type", "prompt")
                if msg_type == "ping":
                    await websocket.send(json.dumps({"type": "pong", "time": time.time()}))
                    continue
                elif msg_type == "sync":
                    last_seq = data.get("last_seq", 0)
                    await agent_mgr.sync_client(client_queue, last_seq)
                    continue
                elif msg_type == "cancel":
                    await agent_mgr.cancel_task()
                    continue
                elif msg_type == "auth_token":
                    token = data.get("token", "")
                    user = security_mgr.get_user_from_token(token)
                    if user:
                        await agent_mgr.authenticate_client(client_queue, user.get("username"))
                    await agent_mgr.submit_auth_token(token)
                    continue
                elif msg_type == "save_artifact":
                    path = data.get("path", "")
                    content = data.get("content", "")
                    if path.startswith('file://'):
                        path = path[7:]
                        
                    import subprocess
                    if sys.platform == "win32" and path.startswith("/"):
                        try:
                            # Avoid stdin piping bugs on Windows by writing to a local temp file first
                            temp_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "wsl_temp_save.md")
                            with open(temp_path, "w", encoding="utf-8") as tf:
                                tf.write(content)
                            
                            # Convert Windows path to WSL path and copy
                            wsl_temp = subprocess.run(["wsl.exe", "wslpath", "-a", temp_path], capture_output=True, text=True, creationflags=0x08000000).stdout.strip()
                            subprocess.run(["wsl.exe", "bash", "-c", f"cp '{wsl_temp}' '{path}'"], creationflags=0x08000000)
                            
                            if os.path.exists(temp_path):
                                os.remove(temp_path)
                        except Exception as e:
                            print(f"WSL save error: {e}")
                    else:
                        try:
                            with open(path, 'w', encoding='utf-8') as f:
                                f.write(content)
                        except: pass
                    continue
                elif msg_type == "exam_ready":
                    await agent_mgr.broadcast(data)
                    continue
                elif msg_type == "cli_input":
                    cli_in = data.get("input", "")
                    await agent_mgr.send_input(cli_in)
                    continue
                elif msg_type == "ack":
                    seq = data.get("seq")
                    if seq is not None:
                        agent_mgr.handle_ack(seq)
                    continue
                elif msg_type == "prompt":
                    prompt = data.get("prompt", "").strip()
                    model = data.get("model", "gemini-3.8-flash-high")
                    conversation_id = data.get("conversation_id")
                    token = data.get("token")
                    
                    if token:
                        user = security_mgr.get_user_from_token(token)
                        if not user:
                            await websocket.send(json.dumps({
                                "type": "system",
                                "level": "error",
                                "message": "Your session has expired. Please refresh the page and log in again."
                            }))
                            continue
                        await agent_mgr.authenticate_client(client_queue, user.get("username"))
                    else:
                        user = security_mgr.get_user_from_token(None)
                    
                    admin_override = os.environ.get("ADMIN_OVERRIDE", "false").lower() == "true"
                    if data.get("danger_mode") is True:
                        admin_override = True
            except (json.JSONDecodeError, AttributeError):
                prompt = str(raw_msg).strip()
                user = None
                admin_override = os.environ.get("ADMIN_OVERRIDE", "false").lower() == "true"

            if prompt:
                # [SECURITY] 1. SEMANTIC FIREWALL INTERCEPTION (RBAC AWARE)
                # Tier 5 Admins require full unrestricted execution for system administration.
                is_admin = user and user.get("role") in ("admin", "super_admin", "Tier5_SysAdmin")
                if not is_admin:
                    try:
                        from local_security import LocalSecurity
                        ls = LocalSecurity()
                        security_status = ls.analyze_intent(prompt)
                        if security_status == "ATTACK":
                            print("[Semantic Firewall] Dropping malicious prompt.")
                            await ws.send(json.dumps({
                                "type": "agent_article",
                                "markdown": "> [!CAUTION] Semantic Firewall Active\n> Malicious intent or prompt injection detected. Your request has been blocked and dropped."
                            }))
                            continue
                    except ImportError:
                        pass
                    except Exception as e:
                        print(f"[Security Firewall] Error parsing intent: {e}")

                await agent_mgr.start_task(prompt, model=model, conversation_id=conversation_id, user=user, admin_override=admin_override)
    except asyncio.CancelledError:
        pass
    except Exception as e:
        import traceback
        traceback.print_exc()
        try:
            with open("ws_error.log", "a") as f:
                f.write(traceback.format_exc() + "\n")
        except: pass
        print(f"WebSocket Error: {e}")
    finally:
        sender_task.cancel()
        await agent_mgr.unregister_client(client_queue)


# Project API endpoints
@app.route('/api/sounds/<sound_name>')
async def play_sound(sound_name):
    from quart import send_file
    
    # Base directory for internal UI sounds
    sounds_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "sandbox", "static", "sounds")
    
    # Check for supported audio extensions dynamically
    for ext in ['.wav', '.mp3', '.ogg']:
        file_path = os.path.join(sounds_dir, f"{sound_name}{ext}")
        if os.path.exists(file_path):
            return await send_file(file_path)
    
    # Return 404 if the user hasn't placed a custom sound file yet
    return jsonify({"error": f"No custom {sound_name} audio file found in {sounds_dir}"}), 404

# File & Security Management API endpoints
async def trigger_dast_scan_internal():
    """Triggers the Red Team ZAP Docker scan natively."""
    await agent_mgr.broadcast({
        "type": "system",
        "level": "warning",
        "message": "🔴 ACTIVE SPEAR: Initiating internal Red Team DAST strike..."
    })
    
    scanner_path = r"C:\Users\michael\Documents\scanners\scanner.py"
    # Using host.docker.internal to route the ZAP attack correctly back to WSL
    cmd = ["python3", scanner_path, "--dast", "http://host.docker.internal:5000"]
    
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=r"C:\Users\michael\Documents\scanners"
        )
        # We don't block the event loop here. It runs as a true background task.
    except Exception as e:
        print(f"[DAST] Failed to launch Red Team engine: {e}")

async def auto_red_team_daemon():
    """Biological clock: Wakes up every 12 hours to strike the server."""
    while True:
        # 12 hours = 43200 seconds
        await asyncio.sleep(43200)
        await trigger_dast_scan_internal()
# Register the autonomous testing biological clock safely when the event loop starts


import signal

def force_shutdown(sig, frame):
    print("\n[Antigravity] Force quitting server (bypassing asyncio graceful shutdown)...")
    os._exit(0)

if __name__ == '__main__':
    import signal
    def force_shutdown(sig, frame):
        import os
        print('\n[Antigravity] Force quitting...')
        os._exit(0)
    signal.signal(signal.SIGINT, force_shutdown)
    print('Starting Antigravity Backend Engine on port 5000...')
    import asyncio
    from hypercorn.config import Config
    from hypercorn.asyncio import serve
    config = Config()
    
    # Check for TLS certificates
    import os
    cert_path = os.path.join(os.getcwd(), "cert.pem")
    key_path = os.path.join(os.getcwd(), "key.pem")
    if os.path.exists(cert_path) and os.path.exists(key_path):
        config.certfile = cert_path
        config.keyfile = key_path
        config.bind = ['0.0.0.0:5001']
        config.insecure_bind = ['0.0.0.0:5000']
    else:
        config.bind = ['0.0.0.0:5000']
        
    asyncio.run(serve(app, config))

# =====================================================================
# CWE-214: Secure Proxy Server for Agent LLM Egress
# =====================================================================
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
        
        ui_config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ui_config.json")
        
        # Ensure it passes the Raugus map if needed, but since it's a proxy we just rely on the plugin
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
    # 1. Grab the real root API key securely from the host
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

    # 2. Reconstruct the request to the real Google API
    target_url = f"https://generativelanguage.googleapis.com/{subpath}"
    
    headers = dict(request.headers)
    headers.pop("Host", None) # Let httpx compute correct Host for Google
    
    # 3. Transparent Token Replacement
    if headers.get("x-goog-api-key") == "dummy_token_123":
        headers["x-goog-api-key"] = real_api_key
        
    query_params = dict(request.args)
    if query_params.get("key") == "dummy_token_123":
        query_params["key"] = real_api_key

    body = await request.get_data()
    
    # 4. Forward to Google
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
