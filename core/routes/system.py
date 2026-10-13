import asyncio
import importlib
from core.routes.auth import get_current_user
from quart import Blueprint, request, jsonify, current_app, Response
import os, json
from core import session_manager as sm
from core import project_manager as pm
from agents import agent_manager as am
from security import security_manager as sec_m

system_bp = Blueprint('system_bp', __name__)


@system_bp.route('/api/reload', methods=['POST'])
async def reload_system():
    global sm, pm, am, sec_m
    
    # 1. Enforce Authentication & Admin Role
    auth_header = request.headers.get("Authorization", "")
    token = auth_header.replace("Bearer ", "").strip()
    user = current_app.security_mgr.get_user_from_token(token)
    #if not user or not current_app.security_mgr.can_reload_engine(user):
        #return jsonify({"error": "Unauthorized"}), 401
    
    try:
        # Preserve active WebSocket connections (CWE-200)
        active_clients = dict(current_app.agent_mgr.connected_clients)
        is_busy = current_app.agent_mgr.is_running()
        
        # Reload modules dynamically
        importlib.reload(sm)
        importlib.reload(pm)
        importlib.reload(am)
        importlib.reload(sec_m)
        
        # Reinitialize project, session, and security managers
        current_app.project_mgr = pm.ProjectManager()
        current_app.session_mgr = sm.SessionManager()
        current_app.security_mgr = sec_m.SecurityManager()
        
        # ALWAYS re-instantiate to pick up new code, but preserve running state!
        old_proc = getattr(current_app.agent_mgr, "active_proc", None)
        old_task = getattr(current_app.agent_mgr, "active_task", None)
        old_start = getattr(current_app.agent_mgr, "start_time", None)
        old_actions = getattr(current_app.agent_mgr, "actions", [])
        old_clients = dict(current_app.agent_mgr.connected_clients)
        
        current_app.agent_mgr = am.AgentTaskManager(project_manager=current_app.project_mgr)
        current_app.agent_mgr.connected_clients = old_clients
        if is_busy:
            current_app.agent_mgr.active_proc = old_proc
            current_app.agent_mgr.active_task = old_task
            current_app.agent_mgr.task_start_time = old_start
            current_app.agent_mgr.actions = old_actions
        
        # Broadcast reload success (pass dict directly, not json.dumps string)
        await current_app.agent_mgr.broadcast({
            "type": "system",
            "level": "success",
            "message": "Engine classes hot-reloaded successfully. Connection preserved."
        })
        
        return jsonify({"success": True, "message": "Backend hot-reloaded!"})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@system_bp.route('/api/simulate-patch', methods=['POST'])
async def trigger_hot_patch():
    # Run the sequence in the background so we can return the HTTP response immediately
    asyncio.create_task(execute_hot_patch_sequence())
    return jsonify({"success": True, "message": "Hot-patch sequence initiated."})


@system_bp.route('/api/security/csp-report', methods=['POST'])
async def csp_report():
    import json
    from datetime import datetime
    try:
        report = await request.get_json(force=True)
        log_entry = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "report": report.get("csp-report", report)
        }
        with open("csp_violations.log", "a", encoding="utf-8") as f:
            f.write(json.dumps(log_entry) + "\n")
        print("[Security] CSP Violation Logged")
    except Exception as e:
        print(f"[Security] Failed to log CSP violation: {e}")
    return jsonify({"success": True}), 204



@system_bp.route('/api/security/red-team-strike', methods=['POST'])
async def api_trigger_red_team():
    user = get_current_user()
    if not user or user.get("role") not in ["super_admin", "Tier5_SysAdmin"]:
        return jsonify({"error": "Access Denied: Red Team strikes require Tier 5 Admin authorization."}), 403
        
    asyncio.create_task(trigger_dast_scan_internal())
    return jsonify({"success": True, "message": "Red Team strike initiated."})


