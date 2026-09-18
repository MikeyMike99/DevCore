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
    
    await agent_mgr.broadcast({
        "type": "system",
        "level": "warning",
        "message": "🚨 EXPLOIT DETECTED: Initiating safe zero-downtime hot-patching sequence..."
    })
    
    # Pre-validation & Backup Phase
    patch_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "patches")
    backup_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "backups")
    os.makedirs(patch_dir, exist_ok=True)
    os.makedirs(backup_dir, exist_ok=True)
    
    patches_found = [f for f in os.listdir(patch_dir) if f.endswith('.py')]
    
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

@app.websocket('/ws')
async def ws():
    await agent_mgr.register_client(websocket)
    try:
        while True:
            raw_msg = await websocket.receive()
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
                    await agent_mgr.sync_client(websocket, last_seq)
                    continue
                elif msg_type == "cancel":
                    await agent_mgr.cancel_task()
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
        await agent_mgr.unregister_client(websocket)

# Project API endpoints
@app.route('/api/projects', methods=['GET'])
async def list_projects():
    projects = project_mgr.list_projects()
    active = project_mgr.active_project
    return jsonify({"projects": projects, "active": active})

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
    # Threaded to prevent connection blocking
    convos = await asyncio.to_thread(session_mgr.list_conversations, project_mgr.active_project, get_current_user())
    return jsonify({"conversations": convos})

@app.route('/api/conversations/<conv_id>', methods=['GET'])
async def get_conversation(conv_id):
    # Threaded to prevent connection blocking
    items = await asyncio.to_thread(session_mgr.get_conversation_transcript, conv_id)
    return jsonify({"items": items})

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

if __name__ == '__main__':
    print("Starting Antigravity Backend Engine on port 5000...")
    app.run(host='0.0.0.0', port=5000, use_reloader=False)
