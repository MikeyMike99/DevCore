import asyncio
import importlib
import importlib.util
import inspect
import sys
from core.routes.auth import get_current_user
from quart import Blueprint, request, jsonify, current_app, Response
import os, json, time
from core import session_manager as sm
from core import project_manager as pm
from agents import agent_manager as am
from security import security_manager as sec_m
from core.audit_registry import get_audit_registry

system_bp = Blueprint('system_bp', __name__)

IMMUTABLE_JIT_BASENAMES = {
    ".jit_elevation_lease.json",
    ".devcore_master.key",
}

PROTECTED_FIREWALL_BASENAMES = {
    "jit_elevation.py",
    "raugus_hook.py",
    "hooks.json",
    "local_brain_broker.py",
    "raugus_resolver.py",
    "raugus_map.json",
    "generate_raugusmap.py",
    "tool_security_auditor.py",
    "agent_identity.py",
    "raugus_access.py",
    "raugus_access.json",
}

def _request_user():
    user = get_current_user()
    if user:
        return user
    try:
        from core.routes.auth import get_bearer_session_user
        return get_bearer_session_user()
    except Exception:
        return None

def _is_tier5_request() -> bool:
    sec = getattr(current_app, "security_mgr", None)
    if sec is None:
        return False
    user = _request_user()
    if user is not None:
        try:
            tier_val = int(user.get("tier", 5))
        except Exception:
            tier_val = 0
        return bool(sec.is_admin_user(user) and tier_val >= 5)
    return bool(sec.is_host_owner_request(request.remote_addr, dict(request.headers)))

def _is_super_admin_request() -> bool:
    sec = getattr(current_app, "security_mgr", None)
    if sec is None:
        return False
    user = _request_user()
    if user is not None:
        return bool(sec.is_super_admin(user))
    return bool(sec.is_host_owner_request(request.remote_addr, dict(request.headers)))

def _unwrap_view(fn):
    while fn is not None and hasattr(fn, "_raugus_unwrapped"):
        fn = getattr(fn, "_raugus_unwrapped")
    return fn

def install_server_tier_gates(live_app, main_mod=None):
    if live_app is None or not hasattr(live_app, "view_functions"):
        return

    async def _call_view(fn, *args, **kwargs):
        res = fn(*args, **kwargs)
        if inspect.isawaitable(res):
            return await res
        return res

    def _wrap_static(orig_fn):
        async def _gated_custom_static(filename):
            norm = str(filename or "").lstrip("/").replace("\\", "/")
            if norm == "security_audit.json" and not _is_tier5_request():
                return "Forbidden: Tier 5 Administrator clearance required.", 403
            if norm.startswith("courses/progress_") and not (_is_tier5_request() or _request_user() is not None):
                return "Forbidden: Authentication required.", 403
            if norm.startswith("courses/") and not _is_tier5_request():
                return "Forbidden: course files are only served through the course page.", 403
            return await _call_view(orig_fn, filename)

        _gated_custom_static._raugus_unwrapped = orig_fn
        _gated_custom_static.__name__ = getattr(orig_fn, "__name__", "custom_static")
        return _gated_custom_static

    def _wrap_tier5(orig_fn):
        async def _gated_tier5(*args, **kwargs):
            if not _is_tier5_request():
                return "Forbidden: Tier 5 Administrator clearance required.", 403
            return await _call_view(orig_fn, *args, **kwargs)

        _gated_tier5._raugus_unwrapped = orig_fn
        _gated_tier5.__name__ = getattr(orig_fn, "__name__", "tier5_view")
        return _gated_tier5

    def _wrap_super_admin_page(orig_fn):
        async def _gated_super_admin_page(*args, **kwargs):
            if not _is_super_admin_request():
                return "Forbidden: Super Admin clearance required.", 403
            return await _call_view(orig_fn, *args, **kwargs)

        _gated_super_admin_page._raugus_unwrapped = orig_fn
        _gated_super_admin_page.__name__ = getattr(orig_fn, "__name__", "super_admin_page")
        return _gated_super_admin_page

    def _wrap_super_admin_api(orig_fn):
        async def _gated_super_admin_api(*args, **kwargs):
            if not _is_super_admin_request():
                return jsonify({"success": False, "error": "Forbidden: Super Admin clearance required."}), 403
            return await _call_view(orig_fn, *args, **kwargs)

        _gated_super_admin_api._raugus_unwrapped = orig_fn
        _gated_super_admin_api.__name__ = getattr(orig_fn, "__name__", "super_admin_api")
        return _gated_super_admin_api

    wrappers = {
        "custom_static": _wrap_static,
        "plugin_security": _wrap_tier5,
        "plugin_audits": _wrap_tier5,
        "admin_mailbox_page": _wrap_tier5,
        "direct_mode_page": _wrap_super_admin_page,
        "direct_mode_status": _wrap_super_admin_api,
    }
    for ep_k in list(live_app.view_functions.keys()):
        short = ep_k.rsplit(".", 1)[-1]
        builder = wrappers.get(short)
        if builder is None:
            continue
        orig = _unwrap_view(live_app.view_functions[ep_k])
        if callable(orig):
            live_app.view_functions[ep_k] = builder(orig)

async def _run_pages_sync(force: bool = False):
    try:
        from scripts import deploy_siraugga_pages
        importlib.reload(deploy_siraugga_pages)
        return await asyncio.to_thread(deploy_siraugga_pages.sync_siraugga_pages, force)
    except Exception as e:
        print(f"[PagesSync] Sync warning: {e}")
        return {"ok": False, "deployed": False, "error": str(e)}

def _trigger_pages_sync_bg(force: bool = False):
    import threading
    def _runner():
        try:
            from scripts import deploy_siraugga_pages
            importlib.reload(deploy_siraugga_pages)
            res = deploy_siraugga_pages.sync_siraugga_pages(force=force)
            if res.get("deployed"):
                print(f"[PagesSync] Deployed updated Siraugga Pages bundle ({str(res.get('hash', ''))[:12]} @ {str(res.get('git_sha', ''))[:8]}).")
        except Exception as e:
            print(f"[PagesSync] Background sync warning: {e}")
    threading.Thread(target=_runner, name="DevCore-PagesSync-Once", daemon=True).start()

async def _pages_sync_daemon(target_app):
    from scripts import deploy_siraugga_pages
    importlib.reload(deploy_siraugga_pages)
    last_sig = None
    try:
        res = await _run_pages_sync(force=False)
        last_sig = await asyncio.to_thread(deploy_siraugga_pages.watched_inputs_signature)
        if res.get("deployed"):
            print(f"[PagesSync] Initial deploy complete ({str(res.get('hash', ''))[:12]}).")
    except Exception as e:
        print(f"[PagesSync] Startup sync warning: {e}")

    while True:
        try:
            await asyncio.sleep(10)
            sig = await asyncio.to_thread(deploy_siraugga_pages.watched_inputs_signature)
            if sig == last_sig:
                continue
            await asyncio.sleep(3)
            sig2 = await asyncio.to_thread(deploy_siraugga_pages.watched_inputs_signature)
            if sig2 != sig:
                await asyncio.sleep(2)
                sig2 = await asyncio.to_thread(deploy_siraugga_pages.watched_inputs_signature)
            res = await _run_pages_sync(force=False)
            last_sig = sig2
            if res.get("deployed"):
                print(f"[PagesSync] Auto-deployed updated Siraugga Pages bundle ({str(res.get('hash', ''))[:12]} @ {str(res.get('git_sha', ''))[:8]}).")
        except asyncio.CancelledError:
            break
        except Exception as e:
            print(f"[PagesSync] Watcher warning: {e}")

def ensure_pages_sync_started(target_app=None):
    if target_app is None or getattr(target_app, "_pages_sync_started", False):
        return
    try:
        loop = asyncio.get_running_loop()
        target_app._pages_sync_started = True
        loop.create_task(_pages_sync_daemon(target_app))
    except RuntimeError:
        try:
            target_app.add_background_task(_pages_sync_daemon, target_app)
            target_app._pages_sync_started = True
        except Exception:
            target_app._pages_sync_started = False

@system_bp.before_app_serving
async def _on_system_app_serving():
    try:
        if hasattr(sm, "_sync_live_blueprint_routes"):
            sm._sync_live_blueprint_routes()
    except Exception:
        pass
    try:
        app_obj = current_app._get_current_object()
        install_server_tier_gates(app_obj)
        ensure_pages_sync_started(app_obj)
    except Exception:
        pass

def _is_jit_active() -> bool:
    try:
        from security.jit_elevation import verify_jit_elevation
        ver = verify_jit_elevation()
        return bool(ver.get("valid") is True)
    except Exception:
        return False

def _get_devcore_vault_service():
    mod_name = "eprofile_vault_mod"
    repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    documents_dir = os.path.dirname(repo_root)
    vault_mod_path = next((p for p in (os.path.join(repo_root, "playground", "e_profile", "vault_mod.py"),
                                       os.path.join(documents_dir, "e_profile", "vault_mod.py")) if os.path.exists(p)),
                          os.path.join(repo_root, "playground", "e_profile", "vault_mod.py"))
    if not os.path.exists(vault_mod_path):
        raise RuntimeError(f"Unified Vault module not found at {vault_mod_path}")
    mtime = os.path.getmtime(vault_mod_path)
    if mod_name in sys.modules and hasattr(sys.modules[mod_name], "vault_service"):
        existing_mod = sys.modules[mod_name]
        if getattr(existing_mod, "_loaded_mtime", None) == mtime:
            return existing_mod.vault_service
    spec = importlib.util.spec_from_file_location(mod_name, vault_mod_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("Failed to create module spec for e_profile/vault_mod.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = mod
    spec.loader.exec_module(mod)
    mod._loaded_mtime = mtime
    return mod.vault_service

def _mail_no_store_headers() -> dict:
    return {
        "Cache-Control": "no-store, no-cache, must-revalidate, private",
        "Pragma": "no-cache",
        "X-Content-Type-Options": "nosniff",
    }

def _get_mail_engine():
    import services.mail.engine as mail_eng
    return mail_eng

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
            os.path.join(repo_root, ".agents", filename),
            os.path.join(repo_root, filename),
        ]
        for c in candidates:
            if os.path.exists(c):
                return c
        return os.path.join(core_dir, filename)

    jit_active = _is_jit_active()

    if patches_found:
        for patch in patches_found:
            if patch in IMMUTABLE_JIT_BASENAMES:
                try:
                    os.remove(os.path.join(patch_dir, patch))
                except Exception:
                    pass
                await agent_mgr.broadcast({
                    "type": "system",
                    "level": "error",
                    "message": f"\u274c PATCH BLOCKED: '{patch}' is an immutable Human-in-the-Loop JIT authority file."
                })
                return {"success": False, "error": f"Patch target '{patch}' is an immutable JIT authority file."}

            if patch in PROTECTED_FIREWALL_BASENAMES and not jit_active:
                try:
                    os.remove(os.path.join(patch_dir, patch))
                except Exception:
                    pass
                await agent_mgr.broadcast({
                    "type": "system",
                    "level": "error",
                    "message": f"\u274c PATCH BLOCKED: '{patch}' is a locked Raugus Firewall guard file. Elevate Super Admin JIT (5m) first."
                })
                return {"success": False, "error": f"Patch target '{patch}' is locked by Raugus Self-Protection."}

        await agent_mgr.broadcast({
            "type": "system",
            "level": "warning",
            "message": f"\ud83d\udea8 EXPLOIT / PATCH DETECTED: Initiating safe zero-downtime hot-patching sequence for {', '.join(patches_found)}..."
        })

        for patch in patches_found:
            try:
                py_compile.compile(os.path.join(patch_dir, patch), doraise=True)
            except py_compile.PyCompileError as ce:
                await agent_mgr.broadcast({
                    "type": "system",
                    "level": "error",
                    "message": f"\u274c PATCH ABORTED: Syntax error detected in {patch}. Server protection engaged."
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

        applied_targets = []
        for patch in patches_found:
            target_file = _resolve_target_path(patch)
            backup_file = os.path.join(backup_dir, patch)
            if os.path.exists(target_file):
                shutil.copy2(target_file, backup_file)
            shutil.copy2(os.path.join(patch_dir, patch), target_file)
            applied_targets.append((patch, target_file, backup_file))
    else:
        await agent_mgr.broadcast({
            "type": "system",
            "level": "warning",
            "message": "\ud83d\udee1\ufe0f AUTO-PATCH ENGINE: Manual hot-patch sequence initiated (0 external files in core/patches/). Validating core engine modules..."
        })
        try:
            from core.bootstrap_gateway import get_engine_files
            rel_list = get_engine_files(repo_root)
            core_targets = [(os.path.basename(r), os.path.join(repo_root, r)) for r in rel_list]
        except Exception:
            core_targets = [
                ("server.py", os.path.join(core_dir, "server.py")),
                ("session_manager.py", os.path.join(core_dir, "session_manager.py")),
                ("project_manager.py", os.path.join(core_dir, "project_manager.py")),
                ("bootstrap_gateway.py", os.path.join(core_dir, "bootstrap_gateway.py")),
                ("agent_manager.py", os.path.join(repo_root, "agents", "agent_manager.py")),
                ("security_manager.py", os.path.join(repo_root, "security", "security_manager.py")),
            ]
        for label, fpath in core_targets:
            if os.path.exists(fpath):
                try:
                    py_compile.compile(fpath, doraise=True)
                    if label not in PROTECTED_FIREWALL_BASENAMES:
                        shutil.copy2(fpath, os.path.join(backup_dir, label))
                except py_compile.PyCompileError as ce:
                    await agent_mgr.broadcast({
                        "type": "system",
                        "level": "error",
                        "message": f"\u274c VALIDATION ABORTED: Syntax error detected in {label}. Server protection engaged."
                    })
                    return {"success": False, "error": f"Syntax error in {label}: {ce}"}
        await asyncio.sleep(0.2 if fast_countdown else 0.6)
        applied_targets = []

    await agent_mgr.broadcast({
        "type": "system",
        "level": "info",
        "message": "Syntax verified & backups snapshotted. Re-compiling backend modules in-memory..."
    })

    active_clients = dict(agent_mgr.connected_clients)
    old_sessions = dict(getattr(agent_mgr, "sessions_by_key", {}))
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
        try:
            import core.routes.auth as auth_mod
            importlib.reload(auth_mod)
        except Exception:
            auth_mod = None
        try:
            import core.token_telemetry as tt
            importlib.reload(tt)
            tt._ENGINE_INSTANCE = None
        except Exception:
            pass
        for mail_mod_name in ("services.mail.config", "services.mail.engine"):
            if mail_mod_name in sys.modules:
                try:
                    importlib.reload(sys.modules[mail_mod_name])
                except Exception:
                    pass

        if hasattr(sm, "_sync_live_blueprint_routes"):
            sm._sync_live_blueprint_routes()

        sys_mod = sys.modules.get("core.routes.system")

        target_app.project_mgr = pm.ProjectManager()
        target_app.project_mgr.active_project = old_active_proj
        target_app.project_mgr.reinit()
        target_app.session_mgr = sm.SessionManager()
        target_app.security_mgr = sec_m.SecurityManager()

        target_app.agent_mgr = am.AgentTaskManager(project_manager=target_app.project_mgr)
        target_app.agent_mgr.connected_clients = active_clients
        if old_sessions:
            target_app.agent_mgr.sessions_by_key = old_sessions
        if is_busy:
            target_app.agent_mgr.active_proc = old_proc
            target_app.agent_mgr.active_task = old_task
            target_app.agent_mgr.task_start_time = old_start
            target_app.agent_mgr.actions = old_actions

        main_mod = sys.modules.get("__main__") or sys.modules.get("core.server")
        if main_mod:
            main_mod.project_mgr = target_app.project_mgr
            main_mod.session_mgr = target_app.session_mgr
            main_mod.security_mgr = target_app.security_mgr
            main_mod.agent_mgr = target_app.agent_mgr

        try:
            def _sys_fn(attr_n, fallback):
                return getattr(sys_mod, attr_n, fallback) if sys_mod else fallback

            dynamic_endpoints = [
                ('/api/reload', 'system_bp.reload_system', _sys_fn('reload_system', reload_system), ['POST']),
                ('/api/simulate-patch', 'system_bp.trigger_hot_patch', _sys_fn('trigger_hot_patch', trigger_hot_patch), ['POST']),
                ('/telemetry', 'system_bp.telemetry_page', _sys_fn('telemetry_page', telemetry_page), ['GET']),
                ('/plugin/telemetry', 'system_bp.telemetry_page_plugin', _sys_fn('telemetry_page', telemetry_page), ['GET']),
                ('/api/telemetry/tokens', 'system_bp.api_token_telemetry', _sys_fn('api_token_telemetry', api_token_telemetry), ['GET']),
                ('/api/telemetry/models', 'system_bp.api_model_telemetry', _sys_fn('api_model_telemetry', api_model_telemetry), ['GET']),
                ('/audits', 'system_bp.audits_page', _sys_fn('audits_page', audits_page), ['GET']),
                ('/plugin/audits', 'system_bp.audits_page_plugin', _sys_fn('audits_page', audits_page), ['GET']),
                ('/api/audits', 'system_bp.api_get_audits', _sys_fn('api_get_audits', api_get_audits), ['GET']),
                ('/api/audits/run', 'system_bp.api_run_audit', _sys_fn('api_run_audit', api_run_audit), ['POST']),
                ('/api/audits/refresh', 'system_bp.api_refresh_audits', _sys_fn('api_refresh_audits', api_refresh_audits), ['POST']),
                ('/api/bootstrap/pull-config', 'system_bp.api_bootstrap_pull_config', _sys_fn('api_bootstrap_pull_config', api_bootstrap_pull_config), ['POST']),
                ('/api/audits/results/<audit_id>', 'system_bp.api_audit_result', _sys_fn('api_audit_result', api_audit_result), ['GET']),
                ('/api/vault/<path:subpath>', 'system_bp.api_vault_gateway', _sys_fn('api_vault_gateway', api_vault_gateway), ['GET', 'POST', 'DELETE']),
                ('/admin/mailbox', 'system_bp.admin_mailbox_page', _sys_fn('admin_mailbox_page', admin_mailbox_page), ['GET']),
                ('/api/mailbox/status', 'system_bp.api_mailbox_status', _sys_fn('api_mailbox_status', api_mailbox_status), ['GET']),
                ('/api/mailbox/folders', 'system_bp.api_mailbox_folders', _sys_fn('api_mailbox_folders', api_mailbox_folders), ['GET']),
                ('/api/mailbox/inbox', 'system_bp.api_mailbox_inbox', _sys_fn('api_mailbox_inbox', api_mailbox_inbox), ['GET']),
                ('/api/mailbox/inbox/<uid>', 'system_bp.api_mailbox_inbox_detail', _sys_fn('api_mailbox_inbox_detail', api_mailbox_inbox_detail), ['GET']),
                ('/api/mailbox/inbox/<uid>/read', 'system_bp.api_mailbox_inbox_read', _sys_fn('api_mailbox_inbox_read', api_mailbox_inbox_read), ['POST']),
                ('/api/mailbox/reply', 'system_bp.api_mailbox_reply', _sys_fn('api_mailbox_reply', api_mailbox_reply), ['POST']),
                ('/api/mailbox/outbound', 'system_bp.api_mailbox_outbound', _sys_fn('api_mailbox_outbound', api_mailbox_outbound), ['GET']),
                ('/api/mailbox/outbound/<email_id>', 'system_bp.api_mailbox_outbound_detail', _sys_fn('api_mailbox_outbound_detail', api_mailbox_outbound_detail), ['GET']),
                ('/api/mailbox/send', 'system_bp.api_mailbox_send', _sys_fn('api_mailbox_send', api_mailbox_send), ['POST']),
                ('/api/mailbox/clear', 'system_bp.api_mailbox_clear', _sys_fn('api_mailbox_clear', api_mailbox_clear), ['POST']),
                ('/api/mailbox/settings', 'system_bp.api_mailbox_settings', _sys_fn('api_mailbox_settings', api_mailbox_settings), ['POST']),
                ('/api/mailbox/upload-google-json', 'system_bp.api_mailbox_upload_google_json', _sys_fn('api_mailbox_upload_google_json', api_mailbox_upload_google_json), ['POST']),
                ('/api/mailbox/test', 'system_bp.api_mailbox_test', _sys_fn('api_mailbox_test', api_mailbox_test), ['POST']),
                ('/admin/cloudflare', 'system_bp.cloudflare_admin_page', _sys_fn('cloudflare_admin_page', cloudflare_admin_page), ['GET']),
                ('/api/admin/cloudflare/overview', 'system_bp.api_cloudflare_overview', _sys_fn('api_cloudflare_overview', api_cloudflare_overview), ['GET']),
                ('/traffic', 'system_bp.public_traffic_page', _sys_fn('public_traffic_page', public_traffic_page), ['GET']),
                ('/api/public/traffic', 'system_bp.api_public_traffic', _sys_fn('api_public_traffic', api_public_traffic), ['GET']),
            ]
            if auth_mod:
                reset_auth_fn = getattr(auth_mod, 'reset_auth_session', None)
                if reset_auth_fn:
                    dynamic_endpoints.append(('/api/auth/reset', 'auth_bp.reset_auth_session', reset_auth_fn, ['POST']))
                restore_root_fn = getattr(auth_mod, 'restore_root', None)
                if restore_root_fn:
                    dynamic_endpoints.append(('/api/auth/restore-root', 'auth_bp.restore_root', restore_root_fn, ['GET', 'POST']))
                sub_set_fn = getattr(auth_mod, 'set_user_subscription_route', None)
                sub_status_fn = getattr(auth_mod, 'get_user_subscription_status', None)
                sub_del_fn = getattr(auth_mod, 'delete_user_subscription_route', None)
                if sub_set_fn:
                    dynamic_endpoints.append(('/api/user/subscription/set', 'auth_bp.set_user_subscription_route', sub_set_fn, ['POST']))
                if sub_status_fn:
                    dynamic_endpoints.append(('/api/user/subscription/status', 'auth_bp.get_user_subscription_status', sub_status_fn, ['GET']))
                if sub_del_fn:
                    dynamic_endpoints.append(('/api/user/subscription', 'auth_bp.delete_user_subscription_route', sub_del_fn, ['DELETE']))

            existing_rules = {r.rule: r.endpoint for r in target_app.url_map.iter_rules()}
            for rule, ep, view, methods in dynamic_endpoints:
                if rule not in existing_rules:
                    target_app.add_url_rule(rule, endpoint=ep, view_func=view, methods=methods)
                else:
                    matched_ep = existing_rules[rule]
                    target_app.view_functions[matched_ep] = view
                    target_app.view_functions[ep] = view
        except Exception:
            pass

        if sys_mod and hasattr(sys_mod, "install_server_tier_gates"):
            sys_mod.install_server_tier_gates(target_app, main_mod)
        else:
            install_server_tier_gates(target_app, main_mod)

        if sys_mod and hasattr(sys_mod, "ensure_pages_sync_started"):
            sys_mod.ensure_pages_sync_started(target_app)
        else:
            ensure_pages_sync_started(target_app)

        if sys_mod and hasattr(sys_mod, "_trigger_pages_sync_bg"):
            sys_mod._trigger_pages_sync_bg(force=False)
        else:
            _trigger_pages_sync_bg(force=False)

        for patch, _, _ in applied_targets:
            staged_path = os.path.join(patch_dir, patch)
            if os.path.exists(staged_path):
                try:
                    os.remove(staged_path)
                except Exception:
                    pass

        msg = (
            f"\u2705 Server successfully hot-patched ({len(applied_targets)} patch(es) applied) and secured with zero downtime."
            if applied_targets
            else "\u2705 Auto-Patch verification complete: Syntax validated (py_compile), backups saved (core/backups/), and engine hot-swapped in memory."
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
            "message": f"\u26a0\ufe0f CRITICAL: Patch crashed the server engine ({e})! Initiating emergency rollback..."
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
            if old_sessions:
                target_app.agent_mgr.sessions_by_key = old_sessions

        await target_app.agent_mgr.broadcast({
            "type": "system",
            "level": "warning",
            "message": "\ud83d\udd04 Rollback complete. Previous stable state restored from core/backups/."
        })
        return {"success": False, "error": f"Patch failed and rolled back: {e}"}

@system_bp.route('/api/reload', methods=['POST'])
@system_bp.route("/api/reload", methods=["POST"])
async def reload_system():
    if not _is_tier5_request():
        return jsonify({"success": False, "error": "Forbidden: Tier 5 Administrator clearance required."}), 403
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
    asyncio.create_task(execute_hot_patch_sequence(app_obj=app_obj, manual_trigger=True, fast_countdown=False))
    return jsonify({"success": True, "message": "Hot-patch verification & reload sequence initiated."})

@system_bp.route('/api/bootstrap/preflight', methods=['GET', 'POST'])
async def api_bootstrap_preflight():
    try:
        from core.bootstrap_gateway import run_preflight_checks
        report = run_preflight_checks(spawn_agent=False, exit_on_failure=False, quiet=True)
        status_code = 200 if report.get("success") else 500
        return jsonify(report), status_code
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@system_bp.route('/api/bootstrap/pull-config', methods=['POST'])
async def api_bootstrap_pull_config():
    """Authenticated bootstrap sync for fresh git clones/pulls on trusted hosts or owner sessions."""
    import hmac
    no_store = {"Cache-Control": "no-store, no-cache, must-revalidate, private", "X-Content-Type-Options": "nosniff"}
    sec = getattr(current_app, "security_mgr", None)
    is_owner = False
    if sec is not None:
        user = _request_user()
        if user is not None:
            is_owner = bool(sec.is_super_admin(user))
        else:
            is_owner = bool(sec.is_host_owner_request(request.remote_addr, dict(request.headers)))

    repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    ep_root = os.path.join(repo_root, "playground", "e_profile")
    if not os.path.isdir(ep_root):
        ep_root = os.path.join(os.path.dirname(repo_root), "e_profile")

    if not is_owner:
        supplied_secret = (request.headers.get("X-Sync-Secret") or "").strip()
        expected_secret = os.environ.get("SYNC_SECRET", "").strip()
        if not expected_secret and os.path.isfile(os.path.join(ep_root, ".env")):
            try:
                with open(os.path.join(ep_root, ".env"), encoding="utf-8", errors="ignore") as f:
                    for ln in f:
                        if ln.strip().startswith("SYNC_SECRET="):
                            expected_secret = ln.split("=", 1)[1].strip().strip("\"'")
                            break
            except Exception:
                pass
        if not (supplied_secret and expected_secret and hmac.compare_digest(supplied_secret, expected_secret)):
            resp = jsonify({"success": False, "error": "Forbidden: Owner or SYNC_SECRET authorization required."})
            resp.headers.update(no_store)
            return resp, 403

    data = await request.get_json(silent=True) or {}
    target_repo = str(data.get("repo") or "all").strip().lower()
    placeholders = {
        "YourSuperSecretAdminPassword",
        "YourSuperSecretEmployerPassword",
        "A_Long_Random_String_For_Flask_Sessions",
        "SECURE_ADMIN_KEY_HERE",
        "SECURE_KEY_2026_PROTOTYPE",
        "your_email@gmail.com",
        "your_app_password",
    }

    def _safe_env_map(env_path: str) -> dict:
        out = {}
        if not os.path.isfile(env_path):
            return out
        try:
            with open(env_path, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    s = line.strip()
                    if not s or s.startswith("#") or "=" not in s:
                        continue
                    k, v = s.split("=", 1)
                    k_c = k.strip()
                    v_c = v.strip().strip("\"'")
                    if v_c and v_c not in placeholders:
                        out[k_c] = v_c
        except Exception:
            pass
        return out

    bundle = {"success": True, "repo": target_repo, "files": {}, "status": {}}
    if target_repo in ("e_profile", "all") and os.path.isdir(ep_root):
        ep_env = _safe_env_map(os.path.join(ep_root, ".env"))
        if ep_env:
            bundle["files"]["e_profile/.env"] = "\n".join(f"{k}={v}" for k, v in ep_env.items()) + "\n"
        prof_path = os.path.join(ep_root, "profiles.json")
        if os.path.isfile(prof_path):
            try:
                with open(prof_path, "r", encoding="utf-8") as f:
                    bundle["files"]["e_profile/profiles.json"] = f.read()
            except Exception:
                pass
    if target_repo in ("devcore", "all"):
        wa_cfg = os.path.join(repo_root, "security", "webauthn_config.json")
        if os.path.isfile(wa_cfg):
            try:
                with open(wa_cfg, "r", encoding="utf-8") as f:
                    bundle["files"]["security/webauthn_config.json"] = f.read()
            except Exception:
                pass
        for rel_env in ("services/eprofile_bridge/.env", "services/cyberbrief/.env", "services/mail/.env"):
            env_map = _safe_env_map(os.path.join(repo_root, rel_env))
            if env_map:
                bundle["files"][rel_env] = "\n".join(f"{k}={v}" for k, v in env_map.items()) + "\n"
        dk_path = os.path.expanduser("~/.config/devcore/device_keys.json")
        bundle["status"]["device_keys_enrolled"] = os.path.isfile(dk_path)
        bundle["status"]["ai_credentials_present"] = bool(
            os.environ.get("ANTHROPIC_API_KEY")
            or os.environ.get("GEMINI_API_KEY")
            or os.path.isfile(os.path.join(repo_root, "security", "ai_credentials.json"))
        )

    resp = jsonify(bundle)
    resp.headers.update(no_store)
    return resp, 200

@system_bp.route('/api/security/csp-report', methods=['POST'])
async def csp_report():
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

@system_bp.route('/api/security/jit-status', methods=['GET'])
async def api_jit_status():
    try:
        from security.jit_elevation import get_jit_status
        return jsonify({"success": True, **get_jit_status()})
    except Exception as e:
        return jsonify({"success": False, "active": False, "error": str(e)}), 500

@system_bp.route('/api/security/jit-elevate', methods=['POST'])
async def api_jit_elevate():
    user = get_current_user()
    has_master_sig = current_app.security_mgr.check_master_signature()
    if not has_master_sig or not (user and current_app.security_mgr.is_admin_user(user)):
        return jsonify({"success": False, "error": "Access Denied: Super Admin hardware signature & authorization required."}), 403

    try:
        is_busy = False
        if hasattr(current_app, "agent_mgr") and current_app.agent_mgr:
            is_busy = current_app.agent_mgr.is_running()

        if is_busy:
            msg = "Policy Violation: JIT Elevation request ignored because an agent is currently busy executing an active task."
            solution = "Wait for the active agent to complete its execution or cancel the running task before requesting JIT Elevation."
            if hasattr(current_app, "agent_mgr"):
                await current_app.agent_mgr.broadcast({
                    "type": "system",
                    "level": "error",
                    "message": f"⚠️ {msg} Solution: {solution}"
                })
            return jsonify({
                "success": False,
                "error": msg,
                "solution": solution,
                "policy_violation": True
            }), 409

        data = await request.get_json(silent=True) or {}
        ttl_seconds = int(data.get("ttl_seconds", 300))

        bound_agent_id = (
            data.get("agent_id")
            or data.get("conversation_id")
            or getattr(getattr(current_app, "agent_mgr", None), "current_conversation_id", None)
            or "1b00c340-8c19-4a13-a7b9-d85a0799fc83"
        )

        import inspect
        from security.jit_elevation import mint_jit_token
        sig_params = inspect.signature(mint_jit_token).parameters
        mint_kwargs = {
            "ttl_seconds": ttl_seconds,
            "issued_by": "web_ui",
            "active_session_lift": True,
        }
        if "agent_id" in sig_params:
            mint_kwargs["agent_id"] = bound_agent_id
        if "conversation_id" in sig_params:
            mint_kwargs["conversation_id"] = bound_agent_id

        res = mint_jit_token(**mint_kwargs)
        res["bound_agent_id"] = bound_agent_id
        if hasattr(current_app, "agent_mgr"):
            await current_app.agent_mgr.broadcast({
                "type": "system",
                "level": "warning",
                "message": f"🔓 SUPER ADMIN JIT ELEVATION ACTIVE ({res['ttl_seconds']}s): Bound to Agent '{bound_agent_id}'. Core security guard files are temporarily unlocked for patching."
            })
        return jsonify(res)
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@system_bp.route('/api/security/jit-revoke', methods=['POST'])
async def api_jit_revoke():
    user = get_current_user()
    has_master_sig = current_app.security_mgr.check_master_signature()
    if not has_master_sig or not (user and current_app.security_mgr.is_admin_user(user)):
        return jsonify({"success": False, "error": "Access Denied: Super Admin authorization required."}), 403

    try:
        from security.jit_elevation import revoke_jit_token
        res = revoke_jit_token(revoked_by="web_ui")
        if hasattr(current_app, "agent_mgr"):
            await current_app.agent_mgr.broadcast({
                "type": "system",
                "level": "info",
                "message": "🔒 SUPER ADMIN JIT ELEVATION REVOKED: Core security guard files are now re-locked."
            })
        return jsonify(res)
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@system_bp.route('/telemetry', methods=['GET'])
@system_bp.route('/plugin/telemetry', methods=['GET'])
@system_bp.route("/telemetry", methods=["GET"])
async def telemetry_page():
    if not _is_tier5_request():
        return "Forbidden: Tier 5 Administrator clearance required.", 403
    repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    candidates = [
        os.path.join(repo_root, "sandbox", "templates", "telemetry.html"),
        os.path.join(repo_root, "templates", "telemetry.html"),
    ]
    for p in candidates:
        if os.path.exists(p):
            with open(p, "r", encoding="utf-8") as f:
                content = f.read()
            return content, 200, {"Content-Type": "text/html; charset=utf-8"}
    return "Telemetry template not found", 404

@system_bp.route('/api/telemetry/tokens', methods=['GET'])
@system_bp.route("/api/telemetry/tokens", methods=["GET"])
async def api_token_telemetry():
    if not _is_tier5_request():
        return jsonify({"success": False, "error": "Forbidden: Tier 5 Administrator clearance required."}), 403
    try:
        import core.token_telemetry as tt
        engine = tt.get_telemetry_engine()
        tf = request.args.get("timeframe", "all")
        force = request.args.get("force", "false").lower() == "true"
        data = await asyncio.to_thread(engine.get_telemetry_data, requested_timeframe=tf, force_refresh=force)
        return jsonify(data)
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@system_bp.route('/api/telemetry/models', methods=['GET'])
@system_bp.route("/api/telemetry/models", methods=["GET"])
async def api_model_telemetry():
    """Per-brain usage (Claude, Gemini/agy, Ollama, local, ...) from the SwarmFlow log."""
    if not _is_tier5_request():
        return jsonify({"success": False, "error": "Forbidden: Tier 5 Administrator clearance required."}), 403
    try:
        from security.swarm_telemetry import SwarmFlowLogger
        tf = request.args.get("timeframe", "all")
        data = await asyncio.to_thread(SwarmFlowLogger.get_model_usage, tf)
        return jsonify({"success": True, **data})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@system_bp.route('/audits', methods=['GET'])
@system_bp.route("/audits", methods=["GET"])
async def audits_page():
    if not _is_tier5_request():
        return "Forbidden: Tier 5 Administrator clearance required.", 403
    repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    candidates = [
        os.path.join(repo_root, "sandbox", "templates", "audits.html"),
        os.path.join(repo_root, "templates", "audits.html"),
    ]
    for p in candidates:
        if os.path.exists(p):
            with open(p, "r", encoding="utf-8") as f:
                content = f.read()
            return content, 200, {"Content-Type": "text/html; charset=utf-8"}
    return "Audits template not found", 404


@system_bp.route('/api/audits', methods=['GET'])
@system_bp.route("/api/audits", methods=["GET"])
async def api_get_audits():
    if not _is_tier5_request():
        return jsonify({"success": False, "error": "Forbidden: Tier 5 Administrator clearance required."}), 403
    try:
        registry = get_audit_registry()
        catalog = registry.get_catalog()
        return jsonify({"success": True, "audits": catalog})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@system_bp.route('/api/audits/results/<audit_id>', methods=['GET'])
@system_bp.route("/api/audits/result/<audit_id>", methods=["GET"])
async def api_audit_result(audit_id):
    if not _is_tier5_request():
        return jsonify({"success": False, "error": "Forbidden: Tier 5 Administrator clearance required."}), 403
    try:
        registry = get_audit_registry()
        data = registry.get_audit(audit_id)
        if not data:
            return jsonify({"success": False, "error": f"Audit '{audit_id}' not found"}), 404
        return jsonify({"success": True, "audit": data})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@system_bp.route('/api/audits/run', methods=['POST'])
@system_bp.route("/api/audits/run", methods=["POST"])
async def api_run_audit():
    if not _is_tier5_request():
        return jsonify({"success": False, "error": "Forbidden: Tier 5 Administrator clearance required."}), 403
    try:
        data = await request.get_json(silent=True) or {}
        audit_id = data.get("audit_id", "all")
        registry = get_audit_registry()
        if audit_id == "all":
            results = await registry.run_all_audits()
            return jsonify({"success": True, "results": results})
        else:
            res = await registry.run_audit(audit_id)
            status_code = 200 if res.get("success") else 500
            return jsonify(res), status_code
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@system_bp.route('/api/audits/refresh', methods=['POST'])
@system_bp.route("/api/audits/refresh", methods=["POST"])
async def api_refresh_audits():
    if not _is_tier5_request():
        return jsonify({"success": False, "error": "Forbidden: Tier 5 Administrator clearance required."}), 403
    try:
        registry = get_audit_registry()
        registry.discover_audits()
        catalog = registry.get_catalog()
        return jsonify({"success": True, "audits": catalog, "message": "Audits re-scanned successfully"})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@system_bp.route('/admin/mailbox', methods=['GET'])
async def admin_mailbox_page():
    """Serve the unified Tier-5 Admin Mail Hub UI (inbound IMAP + outbound SMTP)."""
    if not _is_tier5_request():
        return "Forbidden: Tier 5 Administrator clearance required.", 403
    repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    template_path = os.path.join(repo_root, "services", "mail", "templates", "admin_mailbox.html")
    if not os.path.isfile(template_path):
        return "Unified mailbox template not found.", 404
    with open(template_path, "r", encoding="utf-8") as handle:
        content = handle.read()
    headers = {"Content-Type": "text/html; charset=utf-8", **_mail_no_store_headers()}
    return Response(content, status=200, headers=headers)


def _mailbox_json_response(payload: dict, status_code: int = 200):
    resp = jsonify(payload)
    resp.headers.update(_mail_no_store_headers())
    return resp, status_code


def _require_mailbox_tier5():
    if not _is_tier5_request():
        return _mailbox_json_response(
            {"success": False, "error": "Forbidden: Tier 5 Administrator clearance required."},
            403,
        )
    return None


@system_bp.route('/api/mailbox/status', methods=['GET'])
async def api_mailbox_status():
    denied = _require_mailbox_tier5()
    if denied:
        return denied
    try:
        eng = _get_mail_engine()
        st = await asyncio.to_thread(eng.get_mailbox_status)
        return _mailbox_json_response({"success": True, "status": st})
    except Exception as e:
        return _mailbox_json_response({"success": False, "error": str(e)}, 500)


@system_bp.route('/api/mailbox/folders', methods=['GET'])
async def api_mailbox_folders():
    denied = _require_mailbox_tier5()
    if denied:
        return denied
    try:
        eng = _get_mail_engine()
        ok, msg, folders = await asyncio.to_thread(eng.list_imap_folders)
        return _mailbox_json_response({"success": ok, "message": msg, "folders": folders})
    except Exception as e:
        return _mailbox_json_response({"success": False, "message": str(e), "folders": []}, 500)


@system_bp.route('/api/mailbox/inbox', methods=['GET'])
async def api_mailbox_inbox():
    denied = _require_mailbox_tier5()
    if denied:
        return denied
    try:
        eng = _get_mail_engine()
        folder = request.args.get("folder", "INBOX")
        q = request.args.get("q", "")
        unread = str(request.args.get("unread", "0")).lower() in ("1", "true", "yes")
        limit = int(request.args.get("limit", 30) or 30)
        ok, msg, items = await asyncio.to_thread(
            eng.fetch_inbox,
            folder=folder,
            limit=limit,
            search_query=q,
            unread_only=unread,
        )
        return _mailbox_json_response({"success": ok, "message": msg, "messages": items})
    except Exception as e:
        return _mailbox_json_response({"success": False, "message": str(e), "messages": []}, 500)


@system_bp.route('/api/mailbox/inbox/<uid>', methods=['GET'])
async def api_mailbox_inbox_detail(uid: str):
    denied = _require_mailbox_tier5()
    if denied:
        return denied
    try:
        eng = _get_mail_engine()
        folder = request.args.get("folder", "INBOX")
        mark_read = str(request.args.get("mark_read", "0")).lower() in ("1", "true", "yes")
        ok, msg, item = await asyncio.to_thread(
            eng.fetch_incoming_email,
            uid=uid,
            folder=folder,
            mark_read=mark_read,
        )
        return _mailbox_json_response(
            {"success": ok, "message": msg, "email": item},
            200 if ok and item else 404,
        )
    except Exception as e:
        return _mailbox_json_response({"success": False, "message": str(e), "email": None}, 500)


@system_bp.route('/api/mailbox/inbox/<uid>/read', methods=['POST'])
async def api_mailbox_inbox_read(uid: str):
    denied = _require_mailbox_tier5()
    if denied:
        return denied
    try:
        eng = _get_mail_engine()
        data = await request.get_json(silent=True) or {}
        folder = data.get("folder", "INBOX")
        is_read = bool(data.get("read", True))
        ok, msg = await asyncio.to_thread(
            eng.set_incoming_read_status,
            uid=uid,
            folder=folder,
            is_read=is_read,
        )
        return _mailbox_json_response({"success": ok, "message": msg}, 200 if ok else 400)
    except Exception as e:
        return _mailbox_json_response({"success": False, "message": str(e)}, 500)


@system_bp.route('/api/mailbox/reply', methods=['POST'])
async def api_mailbox_reply():
    denied = _require_mailbox_tier5()
    if denied:
        return denied
    try:
        eng = _get_mail_engine()
        data = await request.get_json(silent=True) or {}
        ok, msg, record = await asyncio.to_thread(
            eng.reply_to_email,
            to_address=data.get("to_address", ""),
            subject=data.get("subject", ""),
            body_text=data.get("body", ""),
            in_reply_to=data.get("in_reply_to", ""),
            references=data.get("references", ""),
            original_from=data.get("original_from", ""),
            original_date=data.get("original_date", ""),
            original_quote=data.get("original_quote", ""),
        )
        return _mailbox_json_response({"success": ok, "message": msg, "record": record}, 200 if ok else 400)
    except Exception as e:
        return _mailbox_json_response({"success": False, "message": str(e)}, 500)


@system_bp.route('/api/mailbox/outbound', methods=['GET'])
async def api_mailbox_outbound():
    denied = _require_mailbox_tier5()
    if denied:
        return denied
    try:
        eng = _get_mail_engine()
        limit = int(request.args.get("limit", 100) or 100)
        emails = await asyncio.to_thread(eng.load_local_mailbox, limit=limit)
        return _mailbox_json_response({"success": True, "emails": emails})
    except Exception as e:
        return _mailbox_json_response({"success": False, "message": str(e), "emails": []}, 500)


@system_bp.route('/api/mailbox/outbound/<email_id>', methods=['GET'])
async def api_mailbox_outbound_detail(email_id: str):
    denied = _require_mailbox_tier5()
    if denied:
        return denied
    try:
        eng = _get_mail_engine()
        item = await asyncio.to_thread(eng.get_email_by_id, email_id)
        if not item:
            return _mailbox_json_response({"success": False, "message": "Email record not found."}, 404)
        return _mailbox_json_response({"success": True, "email": item})
    except Exception as e:
        return _mailbox_json_response({"success": False, "message": str(e)}, 500)


@system_bp.route('/api/mailbox/send', methods=['POST'])
async def api_mailbox_send():
    denied = _require_mailbox_tier5()
    if denied:
        return denied
    try:
        import html as html_lib
        eng = _get_mail_engine()
        data = await request.get_json(silent=True) or {}
        to_address = str(data.get("to_address", "")).strip()
        subject = str(data.get("subject", "Siraugga Mail Test")).strip() or "Siraugga Mail Test"
        message = str(data.get("message", "")).strip() or "Outbound dispatch from Siraugga Unified Mail Hub."
        action_url = str(data.get("action_url", "")).strip()
        if not to_address:
            return _mailbox_json_response({"success": False, "message": "Recipient email address is required."}, 400)
        body_html = f"<p>{html_lib.escape(message).replace(chr(10), '<br>')}</p>"
        html_content = eng.build_email_template(
            title=subject,
            body_html=body_html,
            action_url=action_url or None,
            action_label="Open Portal" if action_url else None,
        )
        ok, msg, record = await asyncio.to_thread(
            eng.send_email,
            to_address,
            subject,
            html_content,
            message,
        )
        return _mailbox_json_response({"success": ok, "message": msg, "record": record}, 200 if ok else 400)
    except Exception as e:
        return _mailbox_json_response({"success": False, "message": str(e)}, 500)


@system_bp.route('/api/mailbox/clear', methods=['POST'])
async def api_mailbox_clear():
    denied = _require_mailbox_tier5()
    if denied:
        return denied
    try:
        eng = _get_mail_engine()
        ok = await asyncio.to_thread(eng.clear_local_mailbox)
        return _mailbox_json_response({
            "success": bool(ok),
            "message": "Outbound mailbox cleared." if ok else "Failed to clear outbound mailbox.",
        })
    except Exception as e:
        return _mailbox_json_response({"success": False, "message": str(e)}, 500)


@system_bp.route('/api/mailbox/settings', methods=['POST'])
async def api_mailbox_settings():
    denied = _require_mailbox_tier5()
    if denied:
        return denied
    try:
        eng = _get_mail_engine()
        data = await request.get_json(silent=True) or {}
        backend = str(data.get("backend", "smtp")).strip().lower() or "smtp"
        server_host = str(data.get("server", "smtp.gmail.com")).strip()
        server_port = int(data.get("port", 587) or 587)
        use_tls = bool(data.get("use_tls", True))
        username = str(data.get("username", "")).strip()
        password = str(data.get("password", ""))
        default_sender = str(data.get("default_sender", "")).strip()
        imap_server = str(data.get("imap_server", "")).strip()
        imap_port = int(data.get("imap_port", 993) or 993)
        imap_use_ssl = bool(data.get("imap_use_ssl", True))
        imap_username = str(data.get("imap_username", "")).strip()
        imap_password = str(data.get("imap_password", ""))

        ok, msg = await asyncio.to_thread(
            eng.apply_gateway_settings,
            backend,
            server_host,
            server_port,
            use_tls,
            username,
            password,
            default_sender,
            imap_server,
            imap_port,
            imap_use_ssl,
            imap_username,
            imap_password,
        )
        conn_ok = True
        full_msg = msg
        if ok and backend == "smtp":
            smtp_ok, smtp_msg = await asyncio.to_thread(eng.test_smtp_connection)
            imap_ok, imap_msg = await asyncio.to_thread(eng.test_imap_connection)
            conn_ok = bool(smtp_ok and imap_ok)
            full_msg = f"{msg} SMTP: {smtp_msg} | IMAP: {imap_msg}"
        return _mailbox_json_response({"success": ok, "conn_ok": conn_ok, "message": full_msg}, 200 if ok else 400)
    except Exception as e:
        return _mailbox_json_response({"success": False, "conn_ok": False, "message": str(e)}, 500)


@system_bp.route('/api/mailbox/upload-google-json', methods=['POST'])
async def api_mailbox_upload_google_json():
    denied = _require_mailbox_tier5()
    if denied:
        return denied
    try:
        eng = _get_mail_engine()
        data = await request.get_json(silent=True) or {}
        raw_json = str(data.get("google_json", "")).strip()
        if not raw_json:
            return _mailbox_json_response({"success": False, "message": "No Google credentials JSON supplied."}, 400)
        ok, msg, meta = await asyncio.to_thread(eng.apply_google_service_json, raw_json)
        return _mailbox_json_response({"success": ok, "message": msg, "meta": meta}, 200 if ok else 400)
    except Exception as e:
        return _mailbox_json_response({"success": False, "message": str(e)}, 500)


@system_bp.route('/api/mailbox/test', methods=['POST'])
async def api_mailbox_test():
    denied = _require_mailbox_tier5()
    if denied:
        return denied
    try:
        eng = _get_mail_engine()
        data = await request.get_json(silent=True) or {}
        protocol = str(data.get("protocol", "smtp")).strip().lower()
        if protocol == "imap":
            ok, msg = await asyncio.to_thread(eng.test_imap_connection)
            return _mailbox_json_response({"success": ok, "protocol": "imap", "message": msg})
        if protocol == "all":
            smtp_ok, smtp_msg = await asyncio.to_thread(eng.test_smtp_connection)
            imap_ok, imap_msg = await asyncio.to_thread(eng.test_imap_connection)
            return _mailbox_json_response({
                "success": bool(smtp_ok and imap_ok),
                "protocol": "all",
                "message": f"SMTP: {smtp_msg} | IMAP: {imap_msg}",
            })
        ok, msg = await asyncio.to_thread(eng.test_smtp_connection)
        return _mailbox_json_response({"success": ok, "protocol": "smtp", "message": msg})
    except Exception as e:
        return _mailbox_json_response({"success": False, "message": str(e)}, 500)


@system_bp.route('/api/vault/<path:subpath>', methods=['GET', 'POST', 'DELETE'])
async def api_vault_gateway(subpath: str):
    """Super Admin Tier 5 Unified Vault & Bitwarden CLI Gateway with AES-256-GCM transit and X_SHI3LD_X .vault fallback."""
    no_store_headers = {
        "Cache-Control": "no-store, no-cache, must-revalidate, private",
        "Pragma": "no-cache",
        "X-Content-Type-Options": "nosniff",
    }
    user = get_current_user()
    has_master_sig = current_app.security_mgr.check_master_signature()
    if not has_master_sig or not (user and current_app.security_mgr.is_admin_user(user)):
        resp = jsonify({"ok": False, "success": False, "error": "Access Denied: Super Admin Tier 5 clearance and hardware signature required."})
        resp.headers.update(no_store_headers)
        return resp, 403

    try:
        vs = _get_devcore_vault_service()
        method = request.method.upper()
        raw_body = (await request.get_json(silent=True) or {}) if method in ("POST", "DELETE") else {}
        q_arg = request.args.get("q", "")
        actor_name = user.get("username", "admin")

        def _dispatch():
            if subpath == "handshake" and method == "POST":
                return {"ok": True, "handshake": vs.transit.issue_handshake(actor_id=actor_name)}, 200

            if subpath == "status" and method == "GET":
                return {"ok": True, **vs.get_overview()}, 200

            if subpath == "bw/login" and method == "POST":
                data = vs.transit.decrypt_from_transit(raw_body)
                ok, msg = vs.bw.login(
                    email=data.get("email", ""),
                    password=data.get("password", ""),
                    code=data.get("code", ""),
                    method=data.get("method", "0"),
                    client_id=data.get("client_id", ""),
                    client_secret=data.get("client_secret", ""),
                )
                return {"ok": ok, "message": msg, "status": vs.get_overview()}, (200 if ok else 400)

            if subpath == "bw/unlock" and method == "POST":
                data = vs.transit.decrypt_from_transit(raw_body)
                ok, msg = vs.bw.unlock(password=data.get("password", ""))
                return {"ok": ok, "message": msg, "status": vs.get_overview()}, (200 if ok else 400)

            if subpath == "bw/lock" and method == "POST":
                ok, msg = vs.bw.lock()
                return {"ok": ok, "message": msg, "status": vs.get_overview()}, 200

            if subpath == "bw/sync" and method == "POST":
                ok, msg = vs.bw.sync()
                return {"ok": ok, "message": msg, "status": vs.get_overview()}, (200 if ok else 400)

            if subpath == "local/init" and method == "POST":
                data = vs.transit.decrypt_from_transit(raw_body)
                uname = data.get("username") or actor_name
                pwd = data.get("password") or ""
                st = vs.shield.initialize(username=uname, password=pwd, allow_recovery=True)
                return {"ok": True, "message": "Local X_SHI3LD_X .vault initialized and unlocked.", "shield_vault": st, "status": vs.get_overview()}, 200

            if subpath == "local/unlock" and method == "POST":
                data = vs.transit.decrypt_from_transit(raw_body)
                uname = data.get("username") or actor_name
                pwd = data.get("password") or ""
                st = vs.shield.unlock(username=uname, password=pwd)
                return {"ok": True, "message": f"Local .vault unlocked for '{uname}'.", "shield_vault": st, "status": vs.get_overview()}, 200

            if subpath == "local/lock" and method == "POST":
                st = vs.shield.lock()
                return {"ok": True, "message": "Local .vault locked in memory.", "shield_vault": st, "status": vs.get_overview()}, 200

            if subpath == "local/user" and method == "POST":
                data = vs.transit.decrypt_from_transit(raw_body)
                st = vs.shield.add_or_update_user(
                    target_username=data.get("target_username", ""),
                    target_password=data.get("target_password", ""),
                )
                return {"ok": True, "message": "Team member access updated and recovery bridge rotated.", "shield_vault": st}, 200

            if subpath == "local/recovery-challenge" and method == "POST":
                data = vs.transit.decrypt_from_transit(raw_body)
                ch = vs.shield.get_recovery_challenge(verify_username=data.get("username", actor_name))
                return {"ok": True, "challenge": ch}, 200

            if subpath == "local/recover" and method == "POST":
                data = vs.transit.decrypt_from_transit(raw_body)
                st = vs.shield.emergency_recover(
                    verify_username=data.get("username", actor_name),
                    recovery_token=data.get("recovery_token", ""),
                    new_password=data.get("new_password", ""),
                )
                return {"ok": True, "message": "Emergency Split-Key Recovery succeeded and cipher rotated.", "shield_vault": st, "status": vs.get_overview()}, 200

            if subpath == "local/rotate-kms" and method == "POST":
                new_id = vs.keychain.rotate_key()
                return {"ok": True, "message": f"Rotated KMS Keychain to active DEK '{new_id}'.", "kms_keychain": vs.keychain.get_status()}, 200

            if subpath == "local/protect-file" and method == "POST":
                data = vs.transit.decrypt_from_transit(raw_body)
                rel_target = (data.get("target") or "").strip().lstrip("/")
                allowed = {"profiles.json", "gethub_token.txt", ".env", "cache/bridge_queue.json"}
                if rel_target not in allowed:
                    return {"ok": False, "error": f"Target must be one of {sorted(allowed)}"}, 400
                uname = data.get("username") or actor_name
                pwd = data.get("password") or ""
                if not pwd or len(pwd) < 4:
                    return {"ok": False, "error": "Vault password (min 4 chars) required to encrypt file at rest."}, 400
                res = vs.shield.encrypt_external_file(vs.base_dir / rel_target, username=uname, password=pwd)
                return {"ok": True, "message": f"Created encrypted at-rest container '{res['vault_file']}'.", "result": res, "protected_files": vs.get_protected_files_inventory()}, 200

            if subpath == "items":
                if method == "GET":
                    return {"ok": True, "items": vs.list_all_items(search=q_arg)}, 200
                if method == "POST":
                    data = vs.transit.decrypt_from_transit(raw_body)
                    saved = vs.add_item(
                        name=data.get("name", ""),
                        secret=data.get("secret", ""),
                        category=data.get("category", "API Key"),
                        username=data.get("username", ""),
                        notes=data.get("notes", ""),
                        uri=data.get("uri", ""),
                        target_engine=data.get("target_engine", "auto"),
                    )
                    return {"ok": True, "message": "Credential encrypted and stored in vault.", "saved": saved, "items": vs.list_all_items()}, 200

            if subpath.startswith("items/") and subpath.endswith("/reveal") and method == "POST":
                item_id = subpath[len("items/"):-len("/reveal")].strip("/")
                key_id = raw_body.get("key_id") or ""
                revealed = vs.reveal_item(item_id)
                if key_id:
                    enc = vs.transit.encrypt_for_transit(key_id, revealed)
                    return {"ok": True, "envelope": enc}, 200
                return {"ok": True, "item": revealed}, 200

            if subpath.startswith("items/") and method == "DELETE":
                item_id = subpath[len("items/"):].strip("/")
                deleted = vs.delete_item(item_id)
                return {"ok": deleted, "items": vs.list_all_items()}, 200

            if subpath == "harvest/scan" and method == "GET":
                report = vs.harvester.scan_report(include_raw=False) if hasattr(vs.harvester, "scan_report") else {"findings": vs.harvester.scan(include_raw=False), "stats": {}, "skipped": [], "errors": []}
                items = report["findings"]
                return {
                    "ok": True,
                    "count": len(items),
                    "discovered": items,
                    "stats": report.get("stats", {}),
                    "skipped": report.get("skipped", []),
                    "errors": report.get("errors", []),
                }, 200

            if subpath == "harvest/import" and method == "POST":
                data = vs.transit.decrypt_from_transit(raw_body)
                summary = vs.harvest_into_vault(target_engine=data.get("target_engine", "auto"))
                return {
                    "ok": True,
                    "message": f"Harvested {summary['scanned_count']} secrets into vault (Local .vault: {summary['imported_shield_vault']}, Bitwarden CLI: {summary['imported_bitwarden_cli']}). Original files preserved.",
                    "summary": summary,
                    "items": vs.list_all_items(),
                }, 200

            return {"ok": False, "error": f"Unknown vault endpoint: {method} /api/vault/{subpath}"}, 404

        payload, code = await asyncio.to_thread(_dispatch)
        resp = jsonify(payload)
        resp.headers.update(no_store_headers)
        return resp, code
    except Exception as e:
        resp = jsonify({"ok": False, "success": False, "error": str(e)})
        resp.headers.update(no_store_headers)
        return resp, 400


@system_bp.route('/admin/cloudflare', methods=['GET'])
async def cloudflare_admin_page():
    """Serve the Tier-5 Cloudflare Control Plane UI."""
    if not _is_tier5_request():
        return "Forbidden: Tier 5 Administrator clearance required.", 403
    repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    candidates = [
        os.path.join(repo_root, "sandbox", "templates", "cloudflare.html"),
        os.path.join(repo_root, "templates", "cloudflare.html"),
    ]
    for path in candidates:
        if os.path.isfile(path):
            with open(path, "r", encoding="utf-8") as handle:
                content = handle.read()
            return Response(content, status=200, headers={"Content-Type": "text/html; charset=utf-8", **_mail_no_store_headers()})
    return "Cloudflare template not found", 404


@system_bp.route('/api/admin/cloudflare/overview', methods=['GET'])
async def api_cloudflare_overview():
    """Return Zone, Traffic Analytics, DNS, Pages, and Tunnel status for Tier-5 admins."""
    if not _is_tier5_request():
        return _mailbox_json_response({"ok": False, "error": "Forbidden: Tier 5 Administrator clearance required."}, 403)
    try:
        days_raw = request.args.get("days", "7")
        try:
            days = max(1, min(30, int(days_raw)))
        except ValueError:
            days = 7

        def _fetch_overview():
            import datetime
            repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            scripts_dir = os.path.join(repo_root, "scripts")
            if scripts_dir not in sys.path:
                sys.path.insert(0, scripts_dir)
            from cloudflare_auth import CloudflareClient

            cf = CloudflareClient()
            auth_mode = cf.creds.auth_mode()
            zone_id = cf.creds.zone_id
            account_id = cf.creds.account_id
            errors = {}

            zone_info = {}
            if zone_id:
                try:
                    zr = (cf.api("GET", f"/zones/{zone_id}") or {}).get("result") or {}
                    zone_info = {
                        "id": zr.get("id", zone_id),
                        "name": zr.get("name", cf.creds.zone or ""),
                        "status": zr.get("status", "unknown"),
                        "paused": bool(zr.get("paused", False)),
                        "plan": (zr.get("plan") or {}).get("name", "Free"),
                        "name_servers": zr.get("name_servers") or [],
                    }
                except Exception as exc:
                    errors["zone"] = str(exc)

            dns_records = []
            if zone_id:
                try:
                    dr = (cf.api("GET", f"/zones/{zone_id}/dns_records?per_page=100") or {}).get("result") or []
                    dns_records = [
                        {
                            "id": r.get("id", ""),
                            "type": r.get("type", ""),
                            "name": r.get("name", ""),
                            "content": r.get("content", ""),
                            "proxied": bool(r.get("proxied", False)),
                            "ttl": r.get("ttl", 1),
                        }
                        for r in dr
                    ]
                except Exception as exc:
                    errors["dns"] = str(exc)

            pages_projects = []
            if account_id:
                try:
                    pr = (cf.api("GET", f"/accounts/{account_id}/pages/projects") or {}).get("result") or []
                    for p in pr:
                        latest = p.get("latest_deployment") or {}
                        stage = latest.get("latest_stage") or {}
                        pages_projects.append({
                            "name": p.get("name", ""),
                            "subdomain": p.get("subdomain", ""),
                            "domains": p.get("domains") or [],
                            "latest_status": stage.get("status", "unknown"),
                            "latest_created_on": latest.get("created_on", ""),
                        })
                except Exception as exc:
                    errors["pages"] = str(exc)

            tunnels = []
            if account_id:
                try:
                    tr = (cf.api("GET", f"/accounts/{account_id}/cfd_tunnel?is_deleted=false") or {}).get("result") or []
                    tunnels = [
                        {
                            "id": t.get("id", ""),
                            "name": t.get("name", ""),
                            "status": t.get("status", "unknown"),
                            "connections": len(t.get("connections") or []),
                        }
                        for t in tr
                    ]
                except Exception as exc:
                    errors["tunnels"] = str(exc)

            analytics, analytics_err = _fetch_cloudflare_traffic_analytics(cf, zone_id, days)
            if analytics_err:
                errors["analytics"] = analytics_err

            return {
                "ok": True,
                "auth_mode": auth_mode,
                "zone": zone_info,
                "dns": dns_records,
                "pages": pages_projects,
                "tunnels": tunnels,
                "analytics": analytics,
                "errors": errors,
            }

        payload = await asyncio.to_thread(_fetch_overview)
        return _mailbox_json_response(payload, 200)
    except Exception as exc:
        return _mailbox_json_response({"ok": False, "error": str(exc)}, 500)


_PUBLIC_TRAFFIC_CACHE = {}
_PUBLIC_TRAFFIC_CACHE_TTL = 300


def _fetch_cloudflare_traffic_analytics(cf, zone_id, days):
    """Query Cloudflare GraphQL httpRequests1dGroups and aggregate daily totals."""
    import datetime
    daily = []
    totals = {"requests": 0, "pageViews": 0, "bytes": 0, "cachedBytes": 0, "threats": 0, "uniques": 0}
    if not zone_id:
        return {"days": days, "totals": totals, "daily": daily}, None
    try:
        today = datetime.date.today()
        since = today - datetime.timedelta(days=days - 1)
        gql = """
        query($zoneTag: string!, $since: Date!, $until: Date!) {
          viewer {
            zones(filter: {zoneTag: $zoneTag}) {
              httpRequests1dGroups(limit: 40, orderBy: [date_ASC], filter: {date_geq: $since, date_leq: $until}) {
                dimensions { date }
                sum { requests pageViews bytes cachedBytes threats }
                uniq { uniques }
              }
            }
          }
        }
        """
        gql_res = cf.graphql(gql, {"zoneTag": zone_id, "since": since.isoformat(), "until": today.isoformat()})
        err = str(gql_res["errors"]) if gql_res.get("errors") else None
        zones_data = ((gql_res.get("data") or {}).get("viewer") or {}).get("zones") or []
        groups = zones_data[0].get("httpRequests1dGroups", []) if zones_data else []
        for g in groups:
            s = g.get("sum") or {}
            u = g.get("uniq") or {}
            row = {
                "date": (g.get("dimensions") or {}).get("date", ""),
                "requests": int(s.get("requests") or 0),
                "pageViews": int(s.get("pageViews") or 0),
                "bytes": int(s.get("bytes") or 0),
                "cachedBytes": int(s.get("cachedBytes") or 0),
                "threats": int(s.get("threats") or 0),
                "uniques": int(u.get("uniques") or 0),
            }
            daily.append(row)
            for k in totals:
                totals[k] += row[k]
        return {"days": days, "totals": totals, "daily": daily}, err
    except Exception as exc:
        return {"days": days, "totals": totals, "daily": daily}, str(exc)


@system_bp.route('/traffic', methods=['GET'])
async def public_traffic_page():
    """Serve the public-facing Cloudflare traffic & credibility dashboard."""
    repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    candidates = [
        os.path.join(repo_root, "sandbox", "templates", "traffic.html"),
        os.path.join(repo_root, "templates", "traffic.html"),
    ]
    for path in candidates:
        if os.path.isfile(path):
            with open(path, "r", encoding="utf-8") as handle:
                content = handle.read()
            return Response(content, status=200, headers={"Content-Type": "text/html; charset=utf-8", **_mail_no_store_headers()})
    return "Public traffic template not found", 404


@system_bp.route('/api/public/traffic', methods=['GET'])
async def api_public_traffic():
    """Return public-safe Cloudflare traffic analytics with 5-minute in-memory caching."""
    try:
        days_raw = request.args.get("days", "7")
        try:
            days = max(1, min(30, int(days_raw)))
        except ValueError:
            days = 7

        now_ts = time.time()
        cached = _PUBLIC_TRAFFIC_CACHE.get(days)
        if cached and (now_ts - cached[0]) < _PUBLIC_TRAFFIC_CACHE_TTL:
            return _mailbox_json_response(cached[1], 200)

        def _fetch_public():
            import datetime
            repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            scripts_dir = os.path.join(repo_root, "scripts")
            if scripts_dir not in sys.path:
                sys.path.insert(0, scripts_dir)
            from cloudflare_auth import CloudflareClient

            cf = CloudflareClient()
            zone_id = cf.creds.zone_id
            zone_info = {"name": cf.creds.zone or "mikeytech.dev", "status": "active"}
            if zone_id:
                try:
                    zr = (cf.api("GET", f"/zones/{zone_id}") or {}).get("result") or {}
                    zone_info = {
                        "name": zr.get("name", zone_info["name"]),
                        "status": zr.get("status", "active"),
                    }
                except Exception:
                    pass

            analytics, _ = _fetch_cloudflare_traffic_analytics(cf, zone_id, days)
            return {
                "ok": True,
                "zone": zone_info,
                "analytics": analytics,
                "cached_at": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
            }

        payload = await asyncio.to_thread(_fetch_public)
        _PUBLIC_TRAFFIC_CACHE[days] = (now_ts, payload)
        return _mailbox_json_response(payload, 200)
    except Exception:
        return _mailbox_json_response({"ok": False, "error": "Traffic metrics temporarily unavailable."}, 500)
