import asyncio
import importlib
import json
import os
import time
import sys

# Dynamically add the DevCore root to the Python path so absolute imports work regardless of execution context
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from quart import Quart, websocket, request, jsonify, render_template_string

from core import session_manager as sm
from core import project_manager as pm
from agents import agent_manager as am
from security import security_manager as sec_m

app = Quart(__name__, static_folder=os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "sandbox", "static"))

from security import security_headers
security_headers.init_security_headers(app)

# Initialize modular managers
project_mgr = pm.ProjectManager()
session_mgr = sm.SessionManager()
agent_mgr = am.AgentTaskManager(project_manager=project_mgr)
security_mgr = sec_m.SecurityManager()

@app.route('/api/reload', methods=['POST'])
async def reload_system():
    global project_mgr, session_mgr, agent_mgr, security_mgr, sm, pm, am, sec_m
    
    try:
        # Preserve active WebSocket connections (CWE-200)
        active_clients = dict(agent_mgr.connected_clients)
        is_busy = agent_mgr.is_running()
        
        # Reload modules dynamically
        importlib.reload(sm)
        importlib.reload(pm)
        importlib.reload(am)
        importlib.reload(sec_m)
        
        # Reinitialize project, session, and security managers
        project_mgr = pm.ProjectManager()
        session_mgr = sm.SessionManager()
        security_mgr = sec_m.SecurityManager()
        
        if is_busy:
            # If a task is active, update reference without killing the running subprocess
            agent_mgr.project_manager = project_mgr
        else:
            # If idle, cleanly re-instantiate and restore connected clients
            agent_mgr = am.AgentTaskManager(project_manager=project_mgr)
            agent_mgr.connected_clients = active_clients
        
        # Broadcast reload success (pass dict directly, not json.dumps string)
        await agent_mgr.broadcast({
            "type": "system",
            "level": "success",
            "message": "Engine classes hot-reloaded successfully. Connection preserved."
        })
        
        return jsonify({"success": True, "message": "Backend hot-reloaded!"})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

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
@app.route('/api/simulate-patch', methods=['POST'])
async def trigger_hot_patch():
    # Run the sequence in the background so we can return the HTTP response immediately
    asyncio.create_task(execute_hot_patch_sequence())
    return jsonify({"success": True, "message": "Hot-patch sequence initiated."})

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

# Dynamically load from the sandbox layer (with Live Override Support)
TEMPLATE_FILE = get_live_override_path("sandbox/templates/index.html")
UI_CONFIG_FILE = get_live_override_path("core/ui_config.json")

@app.route('/')
async def index():
    """Dynamically serves and renders the template using Jinja2 variables."""
    if not os.path.exists(TEMPLATE_FILE):
        return "Template not found: " + TEMPLATE_FILE, 404
        
    with open(TEMPLATE_FILE, 'r', encoding='utf-8') as f:
        content = f.read()
        
    # Load dynamic strings
    import json
    with open(UI_CONFIG_FILE, 'r') as f:
        ui_strings = json.load(f)
        
    # Render variables into the HTML
    rendered_content = await render_template_string(content, ui=ui_strings)
    return rendered_content, 200, {'Content-Type': 'text/html; charset=utf-8'}

GLOBAL_AUTH_PROC = None

@app.route('/plugin/media')
async def plugin_media():
    """Dynamically renders the video application plugin."""
    video_id = request.args.get('v', 'jNQXAC9IVRw')
    video_title = request.args.get('title', 'Accessible Video Player')
    
    template = get_live_override_path("sandbox/templates/video_application.html")
    if not os.path.exists(template):
        return "Media template not found", 404
        
    with open(template, 'r', encoding='utf-8') as f:
        content = f.read()
        
    import json
    with open(UI_CONFIG_FILE, 'r') as f:
        ui_strings = json.load(f)
        
    rendered = await render_template_string(content, ui=ui_strings, video_id=video_id, video_title=video_title)
    return rendered, 200, {'Content-Type': 'text/html; charset=utf-8'}

@app.route('/plugin/security')
async def plugin_security():
    """Dynamically renders the security dashboard plugin."""
    template = get_live_override_path("sandbox/templates/security_dashboard.html")
    if not os.path.exists(template):
        return "Security template not found", 404
        
    with open(template, 'r', encoding='utf-8') as f:
        content = f.read()
        
    import json
    with open(UI_CONFIG_FILE, 'r') as f:
        ui_strings = json.load(f)
        
    rendered = await render_template_string(content, ui=ui_strings)
    return rendered, 200, {'Content-Type': 'text/html; charset=utf-8'}

@app.route('/plugin/exam')
async def plugin_exam():
    """Dynamically renders the exam generator plugin."""
    quiz_file = request.args.get('quiz', 'quiz_temp.json')
    exam_title = request.args.get('title', 'Siraugga Exam')
    
    template = get_live_override_path("sandbox/templates/exam_application.html")
    if not os.path.exists(template):
        return "Exam template not found", 404
        
    with open(template, 'r', encoding='utf-8') as f:
        content = f.read()
        
    import json
    with open(UI_CONFIG_FILE, 'r') as f:
        ui_strings = json.load(f)
        
    rendered = await render_template_string(content, ui=ui_strings, quiz_file=quiz_file, exam_title=exam_title)
    return rendered, 200, {'Content-Type': 'text/html; charset=utf-8'}

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
    
    data = await request.get_json()
    path = data.get('path', '')
    content = data.get('content', '')
    if path.startswith('file://'):
        path = path[7:]
        
    if sys.platform == "win32" and path.startswith("/"):
        try:
            process = subprocess.Popen(
                ["wsl.exe", "-e", "bash", "-c", f"cat > '{path}'"],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
            )
            stdout, stderr = process.communicate(input=content)
            if process.returncode == 0:
                return jsonify({"success": True})
            else:
                return jsonify({"error": f"WSL Artifact write failed: {stderr}"}), 500
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    try:
        with open(path, 'w', encoding='utf-8') as f:
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

@app.route('/api/auth_check')
async def auth_check():
    """Proactively tests if the CLI needs authentication by running a dummy command."""
    def run_check():
        global GLOBAL_AUTH_PROC
        import subprocess
        import os
        import re
        import shutil
        import sys
        
        # Resolve agy executable
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        bundled_exe = os.path.join(base_dir, "agy.exe")
        bundled_linux = os.path.join(base_dir, "agy")
        
        real_agy = None
        cand = shutil.which("agy")
        if cand and os.path.exists(cand) and os.path.getsize(cand) > 1024:
            real_agy = cand
        elif os.path.exists(bundled_exe) and os.path.getsize(bundled_exe) > 1024:
            real_agy = bundled_exe
        elif os.path.exists(bundled_linux) and os.path.getsize(bundled_linux) > 1024:
            real_agy = bundled_linux
        elif sys.platform != "win32":
            local_agy = os.path.expanduser("~/.local/bin/agy")
            if os.path.exists(local_agy) and os.path.getsize(local_agy) > 1024:
                real_agy = local_agy
        elif sys.platform == "win32":
            try:
                wsl_agy = subprocess.check_output(["wsl.exe", "-e", "bash", "-lc", "which agy"], text=True, stderr=subprocess.DEVNULL).strip()
                if wsl_agy and wsl_agy.startswith("/"):
                    real_agy = wsl_agy
            except Exception:
                pass
                
        if not real_agy:
            return {"authenticated": True} # Fallback to native gemini if no CLI found

        # Kill any existing dangling process
        if GLOBAL_AUTH_PROC:
            try: GLOBAL_AUTH_PROC.kill()
            except: pass
            
        env = os.environ.copy()
        env["PYTHONUNBUFFERED"] = "1"
        env["WSLENV"] = "PYTHONUNBUFFERED/u"
        
        cmd = [real_agy, '--print', 'ping']
        if sys.platform == 'win32' and not real_agy.endswith('.exe'):
            cmd = ['wsl.exe', '-e'] + cmd
            
        try:
            proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, env=env)
            
            # Read line by line synchronously
            for _ in range(15): # Don't read forever
                line = proc.stdout.readline()
                if not line:
                    break
                
                if "Authentication required" in line or "oauth2" in line or "Waiting for authentication" in line or "https://accounts.google.com" in line:
                    match = re.search(r'(https://accounts\.google\.com/[^\s]+)', line)
                    if match:
                        GLOBAL_AUTH_PROC = proc
                        return {"authenticated": False, "url": match.group(1)}
                        
                if "pong" in line.lower():
                    try: proc.kill()
                    except: pass
                    GLOBAL_AUTH_PROC = None
                    return {"authenticated": True}
                    
            try: proc.kill()
            except: pass
            GLOBAL_AUTH_PROC = None
            return {"authenticated": False, "url": "#"}
        except Exception as e:
            print(f"Auth check error in thread: {e}")
            return {"authenticated": False, "url": "#"}
            
    try:
        result = await asyncio.to_thread(run_check)
        return jsonify(result)
    except Exception as e:
        print(f"Auth check error: {e}")
        return jsonify({"authenticated": False, "url": "#"})

@app.route('/login')
async def login_page():
    login_file = get_live_override_path("sandbox/templates/login.html")
    if not os.path.exists(login_file):
        return "Login template not found", 404
    with open(login_file, 'r', encoding='utf-8') as f:
        return f.read(), 200, {'Content-Type': 'text/html; charset=utf-8'}

@app.route('/api/set_api_key', methods=['POST'])
async def set_api_key():
    data = await request.get_json() or {}
    api_key = data.get('api_key', '').strip()
    if not api_key:
        return jsonify({"success": False, "error": "No API key provided"})
    
    os.environ["GEMINI_API_KEY"] = api_key
    client_key_path = os.path.expanduser("~/.devcore_client_key.txt")
    try:
        with open(client_key_path, "w", encoding="utf-8") as f:
            f.write(api_key)
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

@app.route('/api/auth_submit', methods=['POST'])
async def auth_submit():
    print("[auth_submit] Starting request...")
    data = await request.get_json() or {}
    token = data.get('token', '').strip()
    if not token:
        print("[auth_submit] No token provided")
        return jsonify({"success": False, "error": "No token provided"})
        
    def run_submit():
        global GLOBAL_AUTH_PROC
        if not GLOBAL_AUTH_PROC:
            return {"success": False, "error": "No auth check process running"}
            
        proc = GLOBAL_AUTH_PROC
        try:
            proc.stdin.write(token + "\n")
            proc.stdin.flush()
            
            for _ in range(15): # Max 15 lines
                line = proc.stdout.readline()
                if not line:
                    break
                    
                out = line.lower()
                if "authentication failed" in out or "invalid code" in out or "error" in out or "timed out" in out or "invalid_grant" in out or "malformed" in out:
                    try: proc.kill()
                    except: pass
                    GLOBAL_AUTH_PROC = None
                    return {"success": False}
                    
                if "authentication successful" in out or "select " in out or "project" in out or "workspace" in out or "pong" in out:
                    try: proc.kill()
                    except: pass
                    GLOBAL_AUTH_PROC = None
                    return {"success": True}
                    
            try: proc.kill()
            except: pass
            GLOBAL_AUTH_PROC = None
            return {"success": True}
        except Exception as e:
            GLOBAL_AUTH_PROC = None
            return {"success": False, "error": str(e)}
            
    try:
        result = await asyncio.to_thread(run_submit)
        return jsonify(result)
    except Exception as e:
        print(f"[auth_submit] Exception: {e}")
        return jsonify({"success": False, "error": str(e)})

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
                        
                    import sys, subprocess, os
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
                    await agent_mgr.submit_cli_input(cli_in)
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
                    admin_override = data.get("admin_override", False)
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
            except (json.JSONDecodeError, AttributeError):
                prompt = str(raw_msg).strip()
                user = None
                admin_override = False

            if prompt:
                # [SECURITY] 1. SEMANTIC FIREWALL INTERCEPTION (RBAC AWARE)
                # Tier 5 Admins require full unrestricted execution for system administration.
                is_admin = user and user.get("role") == "Tier5_SysAdmin"
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
@app.route('/api/projects', methods=['GET'])
async def list_projects():
    projects = project_mgr.list_projects()
    active = project_mgr.active_project
    root_name = "Workspaces"
    return jsonify({"projects": projects, "active": active, "root_name": root_name})

@app.route('/api/projects', methods=['POST'])
async def create_project():
    data = await request.get_json() or {}
    name = data.get('name')
    try:
        project_mgr.create_project(name)
        return jsonify({"success": True, "project": name})
    except (ValueError, FileExistsError) as e:
        return jsonify({"error": str(e)}), 400

@app.route('/api/projects/active', methods=['POST'])
async def set_active_project():
    data = await request.get_json() or {}
    name = data.get('name')
    try:
        p = project_mgr.set_active_project(name)
        return jsonify({"success": True, "active": project_mgr.active_project, "path": p})
    except Exception as e:
        return jsonify({"error": str(e)}), 400

# Conversation API endpoints
@app.route('/api/conversations', methods=['GET'])
async def list_conversations():
    limit = request.args.get('limit', default=10, type=int)
    # Threaded to prevent connection blocking
    convos, has_more = await asyncio.to_thread(session_mgr.list_conversations, project_mgr.active_project, get_current_user(), limit)
    return jsonify({"conversations": convos, "has_more": has_more})

@app.route('/api/conversations/<conv_id>', methods=['GET'])
async def get_conversation(conv_id):
    # Threaded to prevent connection blocking
    items = await asyncio.to_thread(session_mgr.get_conversation_transcript, conv_id)
    return jsonify({"items": items})

@app.route('/api/conversations/<conv_id>', methods=['DELETE'])
async def delete_conversation(conv_id):
    user = get_current_user()
    if not user:
        return jsonify({"error": "Unauthorized"}), 401
    try:
        success = await asyncio.to_thread(session_mgr.delete_session, conv_id, user)
        if success:
            return jsonify({"success": True})
        else:
            return jsonify({"error": "Failed to delete"}), 403
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/projects/active/conversations', methods=['DELETE'])
async def clear_project_sessions():
    user = get_current_user()
    if not user:
        return jsonify({"error": "Unauthorized"}), 401

    active_proj = project_mgr.active_project
    if not active_proj:
        return jsonify({"error": "No active project"}), 400

    try:
        # Threaded deletion prevents connection timeouts
        await asyncio.to_thread(session_mgr.delete_project_sessions, active_proj, user)
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

def get_current_user():
    auth_hdr = request.headers.get('Authorization', '')
    token = auth_hdr.replace('Bearer ', '').strip()
    return security_mgr.get_user_from_token(token)


@app.route('/api/auth/keys', methods=['GET'])
async def list_keys():
    user = get_current_user()
    if not user or user.get("role") not in ["super_admin", "admin"]:
        return jsonify({"error": "Admin access required"}), 403
    return jsonify(security_mgr.get_all_keys())

@app.route('/api/auth/scrub', methods=['POST'])
async def scrub_auth():
    """Removes all Google OAuth and Gemini API key configuration to test fresh state."""
    import os
    import sys
    import subprocess
    
    if 'GEMINI_API_KEY' in os.environ:
        del os.environ['GEMINI_API_KEY']
        
    paths = [
        os.path.expanduser('~/.devcore_client_key.txt'),
        os.path.expanduser('~/.config/gcloud/application_default_credentials.json'),
        os.path.expanduser('~/.gemini/credentials.json'),
        os.path.expanduser('~/.gemini/antigravity/credentials.json'),
        os.path.expanduser('~/.config/antigravity/credentials.json'),
        os.path.expandvars('%APPDATA%/gcloud/application_default_credentials.json')
    ]
    for p in paths:
        if os.path.exists(p):
            try: os.remove(p)
            except: pass
            
    return jsonify({"success": True, "message": "Host Authentication scrubbed. You can now test the setup flow."})

@app.route('/api/auth/keys', methods=['POST'])
async def create_key():
    user = get_current_user()
    if not user or user.get("role") not in ["super_admin", "admin"]:
        return jsonify({"error": "Admin access required"}), 403
    data = await request.get_json() or {}
    role = data.get("role", "guest")
    name = data.get("name", "New User")
    allowed_projects = data.get("allowed_projects")
    expires_in_days = float(data.get("expires_in_days", 30))
    
    new_key = security_mgr.generate_key(role, name, allowed_projects, expires_in_days)
    return jsonify({"success": True, "key": new_key})

@app.route('/api/auth/keys/<key_id>', methods=['DELETE'])
async def delete_key(key_id):
    user = get_current_user()
    if not user or user.get("role") not in ["super_admin", "admin"]:
        return jsonify({"error": "Admin access required"}), 403
    success = security_mgr.delete_key(key_id)
    return jsonify({"success": success})


# File & Security Management API endpoints
@app.route('/api/files', methods=['GET'])
async def list_files():
    user = get_current_user()
    if not user:
        return jsonify({"error": "Unauthorized"}), 401
    workspace = project_mgr.get_active_workspace_path()
    if not security_mgr.can_access_project(user, project_mgr.active_project):
        return jsonify({"error": "Access Denied: You do not have permission for this workspace"}), 403
    files = await asyncio.to_thread(security_mgr.list_files, workspace, user=user)
    return jsonify({"workspace": workspace, "files": files, "user": user})

@app.route('/api/files/content', methods=['GET'])
async def get_file_content():
    user = get_current_user()
    if not user:
        return jsonify({"error": "Unauthorized"}), 401
    path = request.args.get('path', '')
    workspace = project_mgr.get_active_workspace_path()
    if not security_mgr.can_access_project(user, project_mgr.active_project):
        return jsonify({"error": "Access Denied: You do not have permission for this workspace"}), 403
    try:
        data = await asyncio.to_thread(security_mgr.read_file_content, workspace, path, user=user)
        return jsonify(data)
    except Exception as e:
        return jsonify({"error": str(e)}), 403

@app.route('/api/files/content', methods=['POST'])
async def save_file_content():
    user = get_current_user()
    if not user:
        return jsonify({"error": "Unauthorized"}), 401
    data = await request.get_json() or {}
    path = data.get('path')
    content = data.get('content', '')
    workspace = project_mgr.get_active_workspace_path()
    if not security_mgr.can_access_project(user, project_mgr.active_project):
        return jsonify({"error": "Access Denied: You do not have permission for this workspace"}), 403
    try:
        result = await asyncio.to_thread(security_mgr.write_file_content, workspace, path, content, user=user)
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 403

@app.route('/api/logs', methods=['GET'])
async def list_logs():
    user = get_current_user()
    if not user or not security_mgr.can_view_logs(user):
        return jsonify({"error": "Access Denied: Admin role required to view system logs"}), 403
    try:
        logs = await asyncio.to_thread(security_mgr.list_logs, user=user)
        return jsonify({"logs": logs})
    except Exception as e:
        return jsonify({"error": str(e)}), 400

@app.route('/api/logs/<log_name>', methods=['GET'])
async def get_log_content(log_name):
    user = get_current_user()
    if not user or not security_mgr.can_view_logs(user):
        return jsonify({"error": "Access Denied: Admin role required to view system logs"}), 403
    try:
        data = await asyncio.to_thread(security_mgr.read_file_content, security_mgr.base_dir, log_name, user=user)
        return jsonify(data)
    except Exception as e:
        return jsonify({"error": str(e)}), 403

# Authentication endpoints

@app.route('/api/auth/system-status', methods=['GET'])
async def auth_system_status():
    """First-Time Setup System Status Check."""
    is_super = security_mgr.check_master_signature()
    return jsonify({"super_admin": is_super})
@app.route('/api/auth/login', methods=['POST'])
async def auth_login():
    data = await request.get_json() or {}
    username = data.get('username')
    password = data.get('password')
    res = security_mgr.authenticate(username, password)
    if res:
        return jsonify(res)
    return jsonify({"error": "Invalid username or password"}), 401

@app.route('/api/auth/logout', methods=['POST'])
async def auth_logout():
    token = request.headers.get('Authorization', '').replace('Bearer ', '').strip()
    security_mgr.logout(token)
    return jsonify({"success": True})

@app.route('/api/auth/me', methods=['GET'])
async def auth_me():
    token = request.headers.get('Authorization', '').replace('Bearer ', '').strip()
    user = security_mgr.get_user_from_token(token)
    if user:
        return jsonify({"user": user})
    return jsonify({"error": "Unauthorized"}), 401

# (Removed duplicate /api/reload endpoint that caused state loss)

# --- THE PURPLE TEAM ENGINE (DAST / ZAP INTEGRATION) ---

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

@app.route('/api/security/red-team-strike', methods=['POST'])
async def api_trigger_red_team():
    user = get_current_user()
    if not user or user.get("role") not in ["super_admin", "Tier5_SysAdmin"]:
        return jsonify({"error": "Access Denied: Red Team strikes require Tier 5 Admin authorization."}), 403
        
    asyncio.create_task(trigger_dast_scan_internal())
    return jsonify({"success": True, "message": "Red Team strike initiated."})

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
    import asyncio; from hypercorn.config import Config; from hypercorn.asyncio import serve; config = Config(); config.bind = ['0.0.0.0:5000']; asyncio.run(serve(app, config))
