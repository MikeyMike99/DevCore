"""Central Flask WSGI Blueprint adapter mounting the Siraugga Framework into e_profile."""
from flask import Blueprint, jsonify, request, render_template, session, redirect
import sys
import os
import time
import socket
import json
import threading
import asyncio
import shutil
import subprocess

ai_path = os.path.dirname(os.path.abspath(__file__))
if ai_path not in sys.path:
    sys.path.insert(0, ai_path)

from agents.agent_manager import AgentTaskManager
from core.project_manager import ProjectManager
from core.session_manager import SessionManager
from security.security_manager import SecurityManager
from core.local_model_service import discover_local_models

ai_bp = Blueprint("ai", __name__, template_folder="sandbox/templates", static_folder="static")

project_mgr = ProjectManager()
session_mgr = SessionManager()
agent_mgr = AgentTaskManager(project_manager=project_mgr)
security_mgr = SecurityManager()


def _get_ui_config() -> dict:
    cfg_path = os.path.join(ai_path, "core", "ui_config.json")
    ui_cfg = {}
    if os.path.exists(cfg_path):
        try:
            with open(cfg_path, "r", encoding="utf-8") as f:
                ui_cfg = json.load(f)
        except Exception:
            ui_cfg = {}
    try:
        local_entries = discover_local_models()
    except Exception:
        local_entries = []
    local_values = {e["value"] for e in local_entries}
    if "header" in ui_cfg and isinstance(ui_cfg["header"].get("models"), list):
        static_models = ui_cfg["header"]["models"]
        filtered = [m for m in static_models if m.get("value") not in local_values]
        ui_cfg["header"]["models"] = ([filtered[0]] + local_entries + filtered[1:]) if filtered else list(local_entries)
    return ui_cfg


def query_auth_daemon(payload, timeout=2.0):
    sock_path = "/tmp/agy_auth.sock"
    if not os.path.exists(sock_path):
        return None
    try:
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.settimeout(timeout)
        s.connect(sock_path)
        s.sendall(json.dumps(payload).encode("utf-8") + b"\n")
        raw = b""
        while True:
            chunk = s.recv(4096)
            if not chunk:
                break
            raw += chunk
            if b"\n" in raw:
                break
        s.close()
        if raw:
            return json.loads(raw.decode("utf-8"))
    except Exception:
        pass
    return None


def kill_auth_daemon():
    state_file = "/tmp/agy_auth_state.json"
    if os.path.exists(state_file):
        try:
            with open(state_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                pid = data.get("pid")
                if pid:
                    try:
                        os.kill(pid, 15)
                    except Exception:
                        pass
        except Exception:
            pass
        try:
            os.unlink(state_file)
        except Exception:
            pass
    sock_path = "/tmp/agy_auth.sock"
    if os.path.exists(sock_path):
        try:
            os.unlink(sock_path)
        except Exception:
            pass


def spawn_auth_daemon():
    kill_auth_daemon()
    py_bin = shutil.which("python3") or "/usr/bin/python3" or sys.executable
    daemon_script = os.path.join(ai_path, "auth_daemon.py")
    try:
        log_fp = open("/tmp/auth_daemon.log", "w", encoding="utf-8")
        subprocess.Popen(
            [py_bin, daemon_script],
            stdout=log_fp,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    except Exception as e:
        try:
            with open("/tmp/auth_daemon.log", "a", encoding="utf-8") as f:
                f.write(f"spawn_auth_daemon error: {e}\n")
        except Exception:
            pass


def wait_for_auth_daemon(timeout=5.0):
    start = time.time()
    while time.time() - start < timeout:
        info = query_auth_daemon({"action": "status"}, timeout=0.5)
        if info and info.get("url") and info.get("url") != "#":
            return info
        time.sleep(0.2)
    return query_auth_daemon({"action": "status"}, timeout=0.5)


ai_loop = asyncio.new_event_loop()


def run_ai_loop():
    asyncio.set_event_loop(ai_loop)
    ai_loop.run_forever()


threading.Thread(target=run_ai_loop, daemon=True).start()

DEMO_TOKEN_TTL_SECONDS = 7 * 24 * 3600
DEMO_DIRS = [
    os.path.join(ai_path, "demo"),
    os.path.abspath(os.path.join(ai_path, "..", "e_profile", "content", "projects", "demo")),
    os.path.abspath(os.path.join(ai_path, "..", "..", "demo")),
]
EPROFILE_ROOT = os.path.abspath(os.path.join(ai_path, "..", "e_profile"))
if not os.path.isdir(EPROFILE_ROOT):
    EPROFILE_ROOT = os.path.abspath(os.path.join(ai_path, "..", "..", ".."))


def _cleanup_expired_demo_tokens():
    now = time.time()
    for d_dir in DEMO_DIRS:
        if not os.path.exists(d_dir):
            continue
        try:
            for root, _, files in os.walk(d_dir):
                for fname in files:
                    fpath = os.path.join(root, fname)
                    try:
                        if now - os.path.getmtime(fpath) > DEMO_TOKEN_TTL_SECONDS:
                            os.unlink(fpath)
                    except Exception:
                        pass
        except Exception:
            pass


def _resolve_token_scope() -> str:
    demo_arg = request.args.get("demo")
    mode_arg = request.args.get("mode")
    is_admin = bool(session.get("is_admin") or session.get("admin"))

    if demo_arg == "1" or mode_arg == "demo":
        session["agent_token_scope"] = "demo"
    elif demo_arg == "0" or mode_arg in ("root", "admin"):
        if is_admin:
            session["agent_token_scope"] = "root"

    if not is_admin:
        return "demo"

    return "demo" if session.get("agent_token_scope") == "demo" else "root"


def _sync_demo_oauth_token():
    for d_dir in DEMO_DIRS:
        visible_token = os.path.join(d_dir, "antigravity-oauth-token")
        cli_token = os.path.join(d_dir, ".gemini", "antigravity-cli", "antigravity-oauth-token")
        try:
            if os.path.exists(visible_token) and not os.path.exists(cli_token):
                os.makedirs(os.path.dirname(cli_token), exist_ok=True)
                shutil.copy2(visible_token, cli_token)
            elif os.path.exists(cli_token) and not os.path.exists(visible_token):
                os.makedirs(d_dir, exist_ok=True)
                shutil.copy2(cli_token, visible_token)
        except Exception:
            pass


def _has_local_cli_credentials(scope: str = None) -> bool:
    _cleanup_expired_demo_tokens()
    active_scope = scope or _resolve_token_scope()

    if active_scope == "demo":
        _sync_demo_oauth_token()
        for d_dir in DEMO_DIRS:
            demo_candidates = [
                os.path.join(d_dir, ".gemini", "antigravity-cli", "antigravity-oauth-token"),
                os.path.join(d_dir, "antigravity-oauth-token"),
                os.path.join(d_dir, ".devcore_client_key.txt"),
                os.path.join(d_dir, "gemini_api_key.txt"),
            ]
            for p in demo_candidates:
                try:
                    if os.path.exists(p) and os.path.getsize(p) > 8:
                        return True
                except Exception:
                    pass
        return False

    if os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY"):
        return True
    credential_candidates = [
        os.path.expanduser("~/.devcore_client_key.txt"),
        os.path.expanduser("~/.gemini/antigravity-cli/antigravity-oauth-token"),
        os.path.join(EPROFILE_ROOT, ".devcore_client_key.txt"),
        os.path.join(EPROFILE_ROOT, ".gemini", "antigravity-cli", "antigravity-oauth-token"),
        os.path.expanduser("~/.gemini/antigravity/credentials.json"),
        os.path.expanduser("~/.config/antigravity/credentials.json"),
        os.path.expanduser("~/.gemini/credentials.json"),
        os.path.expanduser("~/.config/gcloud/application_default_credentials.json"),
    ]
    for p in credential_candidates:
        try:
            if os.path.exists(p) and os.path.getsize(p) > 8:
                return True
        except Exception:
            pass
    return False


def _save_api_key_for_scope(api_key: str, scope: str):
    if scope == "demo":
        for d_dir in DEMO_DIRS[:1]:
            os.makedirs(d_dir, exist_ok=True)
            for fname in (".devcore_client_key.txt", "gemini_api_key.txt"):
                with open(os.path.join(d_dir, fname), "w", encoding="utf-8") as f:
                    f.write(api_key)
    else:
        os.environ["GEMINI_API_KEY"] = api_key
        root_paths = [
            os.path.expanduser("~/.devcore_client_key.txt"),
            os.path.join(EPROFILE_ROOT, ".devcore_client_key.txt"),
        ]
        for p in root_paths:
            try:
                os.makedirs(os.path.dirname(p), exist_ok=True)
                with open(p, "w", encoding="utf-8") as f:
                    f.write(api_key)
            except Exception:
                pass


def _resolve_active_user() -> dict:
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header.split(" ", 1)[1].strip()
        user = security_mgr.get_user_from_token(token)
        if user:
            return user
    is_admin = bool(session.get("is_admin") or session.get("admin"))
    scope = _resolve_token_scope()
    if is_admin and scope != "demo":
        return {"username": session.get("username", "admin"), "role": "admin", "name": "System Administrator", "allowed_projects": ["*"]}
    return {"username": session.get("username", "dev"), "role": "gamedev", "name": "Developer", "allowed_projects": ["*"]}


@ai_bp.route("/")
def ai_home():
    scope = _resolve_token_scope()
    target_project = request.args.get("project", "").strip()
    if target_project and hasattr(project_mgr, "set_active_project"):
        try:
            if target_project.lower() in ("root", "antigravity_agent", "system_core"):
                project_mgr.set_active_project("")
            elif target_project in project_mgr.list_projects():
                project_mgr.set_active_project(target_project)
        except Exception:
            pass

    if scope == "demo":
        if not session.get("agent_authenticated"):
            return redirect("/ai_agent/login?demo=1")
    else:
        if not session.get("agent_authenticated") and not session.get("is_admin") and not session.get("admin"):
            return redirect("/ai_agent/login")
        session["agent_token_scope"] = "root"
        session["agent_authenticated"] = True
    return render_template("index.html", ui=_get_ui_config())


@ai_bp.route("/demo")
def ai_demo_entry():
    session["agent_token_scope"] = "demo"
    session.pop("agent_authenticated", None)
    return redirect("/ai_agent/login?demo=1")


@ai_bp.route("/login")
def login_page():
    scope = _resolve_token_scope()
    if scope == "demo":
        session.pop("agent_authenticated", None)
    return render_template("login.html")


@ai_bp.route("/api/ui-config", methods=["GET"])
def get_ui_config_route():
    return jsonify(_get_ui_config())


@ai_bp.route("/api/auth_check", methods=["GET"])
def auth_check():
    force = request.args.get("force") == "1"
    scope = _resolve_token_scope()
    has_creds = _has_local_cli_credentials(scope)
    is_authenticated = bool(session.get("agent_authenticated")) if scope == "demo" else has_creds

    agy_bin = shutil.which("agy")
    if not agy_bin:
        fallback = os.path.expanduser("~/.local/bin/agy")
        agy_bin = fallback if os.path.exists(fallback) else None

    if not agy_bin:
        return jsonify({
            "authenticated": is_authenticated,
            "scope": scope,
            "url": "#",
            "error": "agy CLI binary not found",
        })

    daemon_info = query_auth_daemon({"action": "status"})
    if force or not daemon_info or not daemon_info.get("active") or daemon_info.get("remaining", 0) < 5:
        spawn_auth_daemon()
        daemon_info = wait_for_auth_daemon(timeout=5.0)

    if daemon_info:
        return jsonify({
            "authenticated": is_authenticated,
            "scope": scope,
            "url": daemon_info.get("url", "#"),
            "remaining": daemon_info.get("remaining", 60),
            "has_existing": has_creds,
        })

    err_log = ""
    if os.path.exists("/tmp/auth_daemon.log"):
        try:
            with open("/tmp/auth_daemon.log", "r", encoding="utf-8") as f:
                err_log = f.read().strip()
        except Exception:
            pass

    return jsonify({
        "authenticated": is_authenticated,
        "scope": scope,
        "url": "#",
        "has_existing": has_creds,
        "error": f"Failed to start authentication session: {err_log}" if err_log else "Failed to start authentication session.",
    })


@ai_bp.route("/api/auth_demo", methods=["GET", "POST"])
def auth_demo():
    _cleanup_expired_demo_tokens()
    session["agent_token_scope"] = "demo"
    session["agent_authenticated"] = True
    res = security_mgr.authenticate("dev", "dev")
    if not res:
        res = {
            "token": "sec-demo-" + os.urandom(8).hex(),
            "user": {
                "username": session.get("username", "demo_visitor"),
                "role": "gamedev",
                "name": "Demo Visitor",
                "allowed_projects": ["demo", "playground"],
            },
        }
    return jsonify({
        "success": True,
        "authenticated": _has_local_cli_credentials("demo"),
        "scope": "demo",
        "token": res.get("token"),
        "user": res.get("user"),
        "message": "Demo mode active (tokens stored in projects/demo and deleted after 7 days)",
    })


@ai_bp.route("/api/set_api_key", methods=["POST"])
def set_api_key():
    data = request.get_json(silent=True) or {}
    is_admin = bool(session.get("is_admin") or session.get("admin"))
    scope = data.get("scope") or _resolve_token_scope()
    if not is_admin:
        scope = "demo"

    if data.get("demo") is True or data.get("api_key") == "demo":
        session["agent_token_scope"] = "demo"
        session["agent_authenticated"] = True
        res = security_mgr.authenticate("dev", "dev")
        return jsonify({
            "success": True,
            "demo": True,
            "scope": "demo",
            "token": res.get("token") if res else None,
            "user": res.get("user") if res else None,
        })

    api_key = data.get("api_key", "").strip()
    if not api_key:
        return jsonify({"success": False, "error": "No API key provided"}), 400

    try:
        _save_api_key_for_scope(api_key, scope)
        session["agent_token_scope"] = scope
        session["agent_authenticated"] = True
        return jsonify({"success": True, "scope": scope})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@ai_bp.route("/api/auth_submit", methods=["POST"])
def auth_submit():
    data = request.get_json(silent=True) or {}
    token = data.get("token", "").strip()
    api_key = data.get("api_key", "").strip()
    is_admin = bool(session.get("is_admin") or session.get("admin"))
    scope = data.get("scope") or _resolve_token_scope()
    if not is_admin:
        scope = "demo"

    if api_key:
        try:
            _save_api_key_for_scope(api_key, scope)
            session["agent_token_scope"] = scope
            session["agent_authenticated"] = True
            return jsonify({"success": True, "scope": scope})
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 500

    if not token:
        return jsonify({"success": False, "error": "No authorization token provided"}), 400

    resp = query_auth_daemon({"action": "submit", "token": token, "scope": scope}, timeout=15.0)
    if not resp:
        return jsonify({
            "success": False,
            "error": "Authentication session expired or unavailable. Please click 'Refresh Link' to restart the authorization flow.",
        }), 400

    if resp.get("success"):
        session["agent_token_scope"] = scope
        session["agent_authenticated"] = True
        return jsonify({
            "success": True,
            "scope": scope,
            "message": resp.get("message", "Google OAuth authorization successful!"),
        })
    return jsonify({"success": False, "error": resp.get("error", "Token rejected.")}), 400


@ai_bp.route("/api/chat", methods=["POST"])
def start_chat():
    data = request.get_json(silent=True) or {}
    prompt = data.get("prompt", "").strip()
    msg_type = data.get("type", "prompt")
    model = data.get("model", "Gemini 3.8 Flash (High)")
    conversation_id = data.get("conversation_id")
    admin_override = bool(data.get("admin_override", False))
    token = data.get("token")

    is_admin = bool(session.get("is_admin", False) or session.get("admin", False))
    scope = _resolve_token_scope()
    is_admin_exec = False if scope == "demo" else is_admin

    user = {
        "role": "admin" if is_admin_exec else "modder",
        "username": session.get("username", "guest"),
        "token_scope": scope,
    }

    if token and not is_admin_exec and scope != "demo":
        user_from_token = security_mgr.get_user_from_token(token)
        if user_from_token and user_from_token.get("role") == "admin":
            is_admin_exec = True
            user = dict(user_from_token)
            user["token_scope"] = "root"

    if msg_type == "cli_input":
        text_input = data.get("text", prompt)
        asyncio.run_coroutine_threadsafe(agent_mgr.send_input(text_input), ai_loop)
        return jsonify({"success": True, "message": "CLI input dispatched"})

    if agent_mgr.is_running() and not prompt.startswith("[STEER_NOW]") and not prompt.startswith("[QUEUE_NEXT]"):
        prompt = f"[STEER_NOW]\n{prompt}"

    asyncio.run_coroutine_threadsafe(
        agent_mgr.start_task(
            prompt,
            model=model,
            conversation_id=conversation_id,
            user=user,
            admin_override=(admin_override and is_admin_exec),
        ),
        ai_loop,
    )
    return jsonify({"success": True, "message": "Task started", "scope": scope})


@ai_bp.route("/api/stream", methods=["GET"])
def get_stream():
    messages = []
    while agent_mgr.message_queue:
        messages.append(agent_mgr.message_queue.pop(0)["msg"])
    return jsonify({"messages": messages})


@ai_bp.route("/api/kill", methods=["POST"])
def kill_chat():
    asyncio.run_coroutine_threadsafe(agent_mgr.cancel_task(), ai_loop)
    return jsonify({"success": True})


@ai_bp.route("/api/auth/login", methods=["POST"])
def auth_login():
    data = request.get_json(silent=True) or {}
    if data.get("demo") is True or data.get("username") == "demo" or data.get("access_key") == "demo":
        session["agent_token_scope"] = "demo"
        session["agent_authenticated"] = True
        res = security_mgr.authenticate("dev", "dev")
        return jsonify(res)
    username = data.get("username")
    password = data.get("password")
    res = security_mgr.authenticate(username, password)
    if res:
        if res.get("user", {}).get("role") == "admin":
            session["is_admin"] = True
            session["agent_token_scope"] = "root"
        session["agent_authenticated"] = True
        return jsonify(res)
    return jsonify({"error": "Invalid username or password"}), 401


@ai_bp.route("/api/auth/logout", methods=["POST"])
def auth_logout():
    token = request.headers.get("Authorization", "").replace("Bearer ", "").strip()
    if token:
        security_mgr.logout(token)
    session.pop("agent_authenticated", None)
    return jsonify({"success": True})


@ai_bp.route("/api/auth/me", methods=["GET"])
def auth_me():
    token = request.headers.get("Authorization", "").replace("Bearer ", "").strip()
    user = security_mgr.get_user_from_token(token)
    if user:
        return jsonify({"user": user})
    active_user = _resolve_active_user()
    if active_user:
        return jsonify({"user": active_user})
    return jsonify({"error": "Unauthorized"}), 401


@ai_bp.route("/api/auth/system-status", methods=["GET"])
def auth_system_status():
    scope = _resolve_token_scope()
    return jsonify({
        "cli_installed": bool(shutil.which("agy") or os.path.exists(os.path.expanduser("~/.local/bin/agy"))),
        "has_api_key": _has_local_cli_credentials(scope),
        "scope": scope,
    })


@ai_bp.route("/api/projects", methods=["GET", "POST"])
def handle_projects():
    if request.method == "POST":
        data = request.get_json(silent=True) or {}
        name = data.get("name", "").strip()
        if name and hasattr(project_mgr, "create_project"):
            try:
                project_mgr.create_project(name)
                return jsonify({"success": True, "active": project_mgr.active_project})
            except Exception as e:
                return jsonify({"error": str(e)}), 400
    projects = project_mgr.list_projects() if hasattr(project_mgr, "list_projects") else []
    active = project_mgr.active_project if hasattr(project_mgr, "active_project") else ""
    return jsonify({"projects": projects, "active": active})


@ai_bp.route("/api/projects/active", methods=["POST"])
def set_active_project():
    data = request.get_json(silent=True) or {}
    name = data.get("name", "")
    if hasattr(project_mgr, "set_active_project"):
        project_mgr.set_active_project(name)
    return jsonify({"success": True, "active": getattr(project_mgr, "active_project", name)})


@ai_bp.route("/api/conversations", methods=["GET"])
def get_conversations():
    user = _resolve_active_user()
    convs = (
        session_mgr.list_conversations(project_name=getattr(project_mgr, "active_project", None), user=user)
        if hasattr(session_mgr, "list_conversations")
        else []
    )
    return jsonify({"conversations": convs})


@ai_bp.route("/api/conversations/<conv_id>", methods=["GET", "DELETE"])
def handle_conversation_details(conv_id):
    user = _resolve_active_user()
    if request.method == "DELETE":
        if hasattr(session_mgr, "delete_conversation"):
            session_mgr.delete_conversation(conv_id, user=user)
        return jsonify({"success": True})
    transcript = session_mgr.get_conversation_transcript(conv_id, user=user) if hasattr(session_mgr, "get_conversation_transcript") else []
    return jsonify({"items": transcript, "transcript": transcript})


@ai_bp.route("/api/conversations/<conv_id>/rename", methods=["POST"])
def rename_conversation(conv_id):
    data = request.get_json(silent=True) or {}
    title = data.get("title", "").strip()
    if title and hasattr(session_mgr, "set_custom_title"):
        session_mgr.set_custom_title(conv_id, title)
    return jsonify({"success": True, "title": title})


@ai_bp.route("/api/projects/active/conversations", methods=["DELETE"])
def delete_active_conversations():
    user = _resolve_active_user()
    if hasattr(session_mgr, "delete_project_sessions"):
        session_mgr.delete_project_sessions(getattr(project_mgr, "active_project", None), user)
    return jsonify({"success": True})


@ai_bp.route("/api/artifacts", methods=["GET"])
def get_artifact():
    user = _resolve_active_user()
    if user.get("role") != "admin":
        return jsonify({"error": "Admin clearance required to view raw artifacts"}), 403
    fpath = request.args.get("path", "").strip()
    if not fpath or not os.path.isfile(fpath):
        return jsonify({"error": "Artifact not found"}), 404
    try:
        with open(fpath, "r", encoding="utf-8", errors="replace") as f:
            return jsonify({"content": f.read(), "path": fpath})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@ai_bp.route("/api/artifacts/save", methods=["POST"])
def save_artifact():
    user = _resolve_active_user()
    if user.get("role") != "admin":
        return jsonify({"error": "Admin clearance required to save artifacts"}), 403
    data = request.get_json(silent=True) or {}
    fpath = data.get("path", "").strip()
    content = data.get("content", "")
    if not fpath:
        return jsonify({"error": "Missing path"}), 400
    try:
        os.makedirs(os.path.dirname(fpath), exist_ok=True)
        with open(fpath, "w", encoding="utf-8") as f:
            f.write(content)
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
