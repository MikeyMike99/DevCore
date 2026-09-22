import asyncio
import importlib
import json
import os
import time
import sys
from quart import Quart, websocket, request, jsonify

import session_manager as sm
import project_manager as pm
import agent_manager as am
import security_manager as sec_m

app = Quart(__name__)

import security_headers
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
        # Preserve active WebSocket connections
        active_clients = set(agent_mgr.connected_clients)
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
    active_clients = set(agent_mgr.connected_clients)
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
TEMPLATE_FILE = os.path.join(BASE_DIR, "templates", "index.html")

@app.route('/')
async def index():
    """Dynamically serves index.html on each request so UI edits take effect instantly."""
    if not os.path.exists(TEMPLATE_FILE):
        return "Template not found: " + TEMPLATE_FILE, 404
    with open(TEMPLATE_FILE, 'r', encoding='utf-8') as f:
        content = f.read()
    return content, 200, {'Content-Type': 'text/html; charset=utf-8'}

GLOBAL_AUTH_PROC = None

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
        upload_dir = os.path.join(os.getcwd(), ".agents", "massive_prompts")
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
    import sys
    import subprocess
    cmd = ['script', '-q', '-c', '/home/michael/.local/bin/agy --print ping', '/dev/null']
    if sys.platform == 'win32':
        cmd = ['wsl.exe'] + cmd
        
    def run_check():
        global GLOBAL_AUTH_PROC
        import subprocess
        import os
        import re
        
        # Kill any existing dangling process
        if GLOBAL_AUTH_PROC:
            try: GLOBAL_AUTH_PROC.kill()
            except: pass
            
        env = os.environ.copy()
        env["PYTHONUNBUFFERED"] = "1"
        env["WSLENV"] = "PYTHONUNBUFFERED/u"
        try:
            proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, env=env)
            
            # Read line by line synchronously
            for _ in range(5): # Don't read forever
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
            # If we get here, no URL or pong found
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
    login_file = os.path.join(BASE_DIR, "templates", "login.html")
    if not os.path.exists(login_file):
        return "Login template not found", 404
    with open(login_file, 'r', encoding='utf-8') as f:
        return f.read(), 200, {'Content-Type': 'text/html; charset=utf-8'}

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
                    await agent_mgr.submit_auth_token(token)
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
@app.before_serving
async def start_red_team_daemon():
    app.add_background_task(auto_red_team_daemon)

if __name__ == '__main__':
    print("Starting Antigravity Backend Engine on port 5000...")
    app.run(host='0.0.0.0', port=5000, use_reloader=False)
