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

PROTECTED_FIREWALL_BASENAMES = {
    "raugus_hook.py",
    "hooks.json",
    "local_brain_broker.py",
    "raugus_resolver.py",
    "raugus_map.json",
    "generate_raugusmap.py",
    "tool_security_auditor.py",
}


async def execute_hot_patch_sequence(app_obj=None, manual_trigger=False, fast_countdown=False):
    """Safe zero-downtime hot-patching sequence with syntax validation (py_compile), backup, and automated rollback."""
    global sm, pm, am, sec_m
    import shutil
    import py_compile
    import traceback

    target_app = app_obj
    if target_app is None:
        try:
            target_app = current_app._get_current_object()
        except Exception:
            import sys
            main_mod = sys.modules.get("__main__") or sys.modules.get("core.server")
            target_app = getattr(main_mod, "app", None) if main_mod else None

    if target_app is None or not hasattr(target_app, "agent_mgr"):
        return {"success": False, "error": "Target app or agent_mgr unavailable"}

    agent_mgr = target_app.agent_mgr
    core_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    repo_root = os.path.dirname(core_dir)
    patch_dir = os.path.join(core_dir, "patches")
    backup_dir = os.path.join(core_dir, "backups")
    os.makedirs(patch_dir, exist_ok=True)
    os.makedirs(backup_dir, exist_ok=True)

    patches_found = [f for f in os.listdir(patch_dir) if f.endswith(".py")]

    if not patches_found and not manual_trigger:
        return {"success": True, "message": "No staged patches found.", "patches_applied": 0}

    def _resolve_target_path(filename: str) -> str:
        candidates = [
            os.path.join(core_dir, filename),
            os.path.join(core_dir, "routes", filename),
            os.path.join(repo_root, "agents", filename),
            os.path.join(repo_root, "agents", "mixins", filename),
            os.path.join(repo_root, "security", filename),
        ]
        for c in candidates:
            if os.path.exists(c):
                return c
        return os.path.join(core_dir, filename)

    if patches_found:
        for patch in patches_found:
            if patch in PROTECTED_FIREWALL_BASENAMES:
                try:
                    os.remove(os.path.join(patch_dir, patch))
                except Exception:
                    pass
                await agent_mgr.broadcast({
                    "type": "system",
                    "level": "error",
                    "message": f"❌ PATCH BLOCKED: '{patch}' is a locked Raugus Firewall guard file and cannot be hot-patched."
                })
                return {"success": False, "error": f"Patch target '{patch}' is locked by Raugus Self-Protection."}

        await agent_mgr.broadcast({
            "type": "system",
            "level": "warning",
            "message": f"🚨 EXPLOIT / PATCH DETECTED: Initiating safe zero-downtime hot-patching sequence for {', '.join(patches_found)}..."
        })

        # 1. Syntax Validation: Ensure no staged patch has syntax errors before applying
        for patch in patches_found:
            try:
                py_compile.compile(os.path.join(patch_dir, patch), doraise=True)
            except py_compile.PyCompileError as ce:
                await agent_mgr.broadcast({
                    "type": "system",
                    "level": "error",
                    "message": f"❌ PATCH ABORTED: Syntax error detected in {patch}. Server protection engaged."
                })
                return {"success": False, "error": f"Syntax error in {patch}: {ce}"}

        if fast_countdown:
            await agent_mgr.broadcast({
                "type": "system",
                "level": "info",
                "message": "Validating and applying staged hot-patch..."
            })
            await asyncio.sleep(0.15)
        else:
            for i in range(3, 0, -1):
                await agent_mgr.broadcast({
                    "type": "system",
                    "level": "info",
                    "message": f"Validating and applying hot-patch in {i}s..."
                })
                await asyncio.sleep(1)

        # 2. Backup and Apply Phase
        applied_targets = []
        for patch in patches_found:
            target_file = _resolve_target_path(patch)
            backup_file = os.path.join(backup_dir, patch)
            if os.path.exists(target_file):
                shutil.copy2(target_file, backup_file)
            shutil.copy2(os.path.join(patch_dir, patch), target_file)
            applied_targets.append((patch, target_file, backup_file))
    else:
        # Manual verification trigger when no staged external patches are waiting in core/patches/
        await agent_mgr.broadcast({
            "type": "system",
            "level": "warning",
            "message": "🛡️ AUTO-PATCH ENGINE: Manual hot-patch sequence initiated (0 external files in core/patches/). Validating core engine modules..."
        })
        core_targets = [
            ("server.py", os.path.join(core_dir, "server.py")),
            ("session_manager.py", os.path.join(core_dir, "session_manager.py")),
            ("project_manager.py", os.path.join(core_dir, "project_manager.py")),
            ("agent_manager.py", os.path.join(repo_root, "agents", "agent_manager.py")),
            ("security_manager.py", os.path.join(repo_root, "security", "security_manager.py")),
        ]
        for label, fpath in core_targets:
            if os.path.exists(fpath):
                try:
                    py_compile.compile(fpath, doraise=True)
                    shutil.copy2(fpath, os.path.join(backup_dir, label))
                except py_compile.PyCompileError as ce:
                    await agent_mgr.broadcast({
                        "type": "system",
                        "level": "error",
                        "message": f"❌ VALIDATION ABORTED: Syntax error detected in {label}. Server protection engaged."
                    })
                    return {"success": False, "error": f"Syntax error in {label}: {ce}"}
        await asyncio.sleep(0.2 if fast_countdown else 0.6)
        applied_targets = []

    await agent_mgr.broadcast({
        "type": "system",
        "level": "info",
        "message": "Syntax verified & backups snapshotted. Re-compiling backend modules in-memory..."
    })

    # 3. Reload & Automated Rollback Phase
    active_clients = dict(agent_mgr.connected_clients)
    is_busy = agent_mgr.is_running()
    old_proc = getattr(agent_mgr, "active_proc", None)
    old_task = getattr(agent_mgr, "active_task", None)
    old_start = getattr(agent_mgr, "task_start_time", getattr(agent_mgr, "start_time", None))
    old_actions = getattr(agent_mgr, "actions", [])
    old_active_proj = getattr(getattr(target_app, "project_mgr", None), "active_project", None)

    try:
        importlib.reload(sm)
        importlib.reload(pm)
        importlib.reload(am)
        importlib.reload(sec_m)

        if hasattr(sm, "_sync_live_blueprint_routes"):
            sm._sync_live_blueprint_routes()

        target_app.project_mgr = pm.ProjectManager()
        target_app.project_mgr.active_project = old_active_proj
        target_app.project_mgr.reinit()
        target_app.session_mgr = sm.SessionManager()
        target_app.security_mgr = sec_m.SecurityManager()

        target_app.agent_mgr = am.AgentTaskManager(project_manager=target_app.project_mgr)
        target_app.agent_mgr.connected_clients = active_clients
        if is_busy:
            target_app.agent_mgr.active_proc = old_proc
            target_app.agent_mgr.active_task = old_task
            target_app.agent_mgr.task_start_time = old_start
            target_app.agent_mgr.actions = old_actions

        # Sync main module globals if present
        import sys
        main_mod = sys.modules.get("__main__") or sys.modules.get("core.server")
        if main_mod:
            main_mod.project_mgr = target_app.project_mgr
            main_mod.session_mgr = target_app.session_mgr
            main_mod.security_mgr = target_app.security_mgr
            main_mod.agent_mgr = target_app.agent_mgr

        # Clean up staged patch files only after successful reload
        for patch, _, _ in applied_targets:
            staged_path = os.path.join(patch_dir, patch)
            if os.path.exists(staged_path):
                try:
                    os.remove(staged_path)
                except Exception:
                    pass

        msg = (
            f"✅ Server successfully hot-patched ({len(applied_targets)} patch(es) applied) and secured with zero downtime."
            if applied_targets
            else "✅ Auto-Patch verification complete: Syntax validated (py_compile), backups saved (core/backups/), and engine hot-swapped in memory."
        )
        await target_app.agent_mgr.broadcast({
            "type": "system",
            "level": "success",
            "message": msg
        })
        return {"success": True, "message": msg, "patches_applied": len(applied_targets)}
    except Exception as e:
        await agent_mgr.broadcast({
            "type": "system",
            "level": "error",
            "message": f"⚠️ CRITICAL: Patch crashed the server engine ({e})! Initiating emergency rollback..."
        })
        for patch, target_file, backup_file in applied_targets:
            if os.path.exists(backup_file):
                shutil.copy2(backup_file, target_file)

        importlib.reload(sm)
        importlib.reload(pm)
        importlib.reload(am)
        importlib.reload(sec_m)
        target_app.project_mgr = pm.ProjectManager()
        target_app.project_mgr.active_project = old_active_proj
        target_app.project_mgr.reinit()
        target_app.session_mgr = sm.SessionManager()
        target_app.security_mgr = sec_m.SecurityManager()
        if not is_busy:
            target_app.agent_mgr = am.AgentTaskManager(project_manager=target_app.project_mgr)
            target_app.agent_mgr.connected_clients = active_clients

        await target_app.agent_mgr.broadcast({
            "type": "system",
            "level": "warning",
            "message": "🔄 Rollback complete. Previous stable state restored from core/backups/."
        })
        return {"success": False, "error": f"Patch failed and rolled back: {e}"}


@system_bp.route('/api/reload', methods=['POST'])
async def reload_system():
    # Unified with execute_hot_patch_sequence so /api/reload always validates syntax (py_compile),
    # applies any staged files in core/patches/, snapshots core/backups/, and rolls back on failure.
    try:
        app_obj = current_app._get_current_object()
        res = await execute_hot_patch_sequence(app_obj=app_obj, manual_trigger=True, fast_countdown=True)
        if isinstance(res, dict) and not res.get("success", True):
            return jsonify(res), 500
        return jsonify({
            "success": True,
            "message": "Backend hot-patched and reloaded!",
            "details": res.get("message") if isinstance(res, dict) else "OK",
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@system_bp.route('/api/simulate-patch', methods=['POST'])
async def trigger_hot_patch():
    app_obj = current_app._get_current_object()
    # Run the sequence in the background so we can return the HTTP response immediately
    asyncio.create_task(execute_hot_patch_sequence(app_obj=app_obj, manual_trigger=True, fast_countdown=False))
    return jsonify({"success": True, "message": "Hot-patch verification & reload sequence initiated."})


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
