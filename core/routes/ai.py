"""Claude brain authentication + status endpoints for the standalone (Quart)
DevCore server. Mirrors the Flask ai_plugin endpoints so the Claude sign-in
works in standalone mode too. Shares the credential/brain helpers in
core.local_model_service."""
import asyncio
import json
import os
import re
import subprocess
import threading
import time
from pathlib import Path

from quart import Blueprint, request, jsonify, current_app
from security import guest_session

ai_bp = Blueprint("ai_routes_bp", __name__)

_login = {"proc": None, "buf": ""}


def _claude_bin():
    import shutil
    return shutil.which("claude") or os.path.expanduser("~/.local/bin/claude")


def _owner_ok():
    """Owner gate: the host master key must be present."""
    try:
        return bool(current_app.security_mgr.is_host_owner_request(request.remote_addr, request.headers))
    except Exception:
        return False


def _extract_oauth_url(raw):
    clean = raw.replace("\x1b", "").replace("\x07", "").replace("]8;;", "")
    m = re.search(r"https://claude\.com/cai/oauth/authorize\?\S+", clean)
    if not m:
        return None
    url = m.group(0)
    i = url.find("https://", 8)
    return url[:i] if i != -1 else url


async def _run(fn):
    return await asyncio.get_event_loop().run_in_executor(None, fn)


@ai_bp.route("/api/ai/status")
async def ai_status():
    from core.local_model_service import get_anthropic_credential
    if get_anthropic_credential():
        return jsonify({"connected": True, "backend": "api", "message": "Connected via API key."})
    cb = _claude_bin()
    if cb and os.path.exists(cb):
        logged_in = False
        try:
            r = await _run(lambda: subprocess.run([cb, "auth", "status"], capture_output=True, text=True, timeout=8))
            logged_in = bool((json.loads(r.stdout or "{}") or {}).get("loggedIn"))
        except Exception:
            logged_in = False
        if logged_in:
            return jsonify({"connected": True, "backend": "subscription",
                            "message": "Connected via your Claude subscription — no API key needed."})
        return jsonify({"connected": False, "backend": "subscription",
                        "message": "Not connected. Sign in with your Claude subscription (no API key needed), or paste an API key below."})
    return jsonify({"connected": False, "backend": "none",
                    "message": "Claude is not set up yet. Paste an API key below to connect."})


@ai_bp.route("/api/ai/connect", methods=["POST"])
async def ai_connect():
    if not _owner_ok():
        return jsonify({"ok": False, "error": "Admin privileges are required to connect Claude."}), 403
    data = (await request.get_json(silent=True)) or {}
    key = (data.get("api_key") or "").strip()
    if not key.startswith("sk-ant-"):
        return jsonify({"ok": False, "error": "That doesn't look like an Anthropic API key (expected sk-ant-...)."}), 400
    from core.local_model_service import set_claude_api_key, run_claude_model
    try:
        set_claude_api_key(key)
    except Exception:
        os.environ["ANTHROPIC_API_KEY"] = key
    result = await _run(lambda: run_claude_model("Connectivity test.", "Reply with exactly: OK",
                                                 "Claude Opus 5.5", 64, "selftest"))
    ok = not result.startswith("[LOCAL_BRAIN_")
    return jsonify({"ok": ok, "message": "Connected and tested successfully." if ok else result[:200]}), (200 if ok else 502)


@ai_bp.route("/api/ai/login/start", methods=["POST"])
async def ai_login_start():
    if not _owner_ok():
        return jsonify({"ok": False, "error": "Admin privileges are required."}), 403
    cb = _claude_bin()
    if not (cb and os.path.exists(cb)):
        return jsonify({"ok": False, "error": "The Claude CLI is not installed on the server."}), 400
    old = _login.get("proc")
    if old and old.poll() is None:
        try:
            old.kill()
        except Exception:
            pass
    _login["buf"] = ""
    proc = subprocess.Popen(
        [cb, "auth", "login", "--claudeai"],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, bufsize=1,
    )
    _login["proc"] = proc

    def _reader(p):
        try:
            for ch in iter(lambda: p.stdout.read(1), ""):
                _login["buf"] += ch
        except Exception:
            pass
    threading.Thread(target=_reader, args=(proc,), daemon=True).start()

    for _ in range(120):
        url = _extract_oauth_url(_login["buf"])
        if url:
            return jsonify({"ok": True, "url": url})
        await asyncio.sleep(0.1)
    return jsonify({"ok": False, "error": "Timed out waiting for the sign-in link. Try again."}), 504


@ai_bp.route("/api/ai/login/complete", methods=["POST"])
async def ai_login_complete():
    if not _owner_ok():
        return jsonify({"ok": False, "error": "Admin privileges are required."}), 403
    data = (await request.get_json(silent=True)) or {}
    code = (data.get("code") or "").strip()
    if not code:
        return jsonify({"ok": False, "error": "Paste the code from the sign-in page."}), 400
    proc = _login.get("proc")
    if not proc or proc.poll() is not None:
        return jsonify({"ok": False, "error": "No active sign-in. Click Sign in again."}), 409
    try:
        proc.stdin.write(code + "\n")
        proc.stdin.flush()
    except Exception as e:
        return jsonify({"ok": False, "error": f"Could not submit code: {e}"}), 500
    try:
        await _run(lambda: proc.wait(timeout=30))
    except Exception:
        pass
    cb = _claude_bin()
    logged_in = False
    try:
        r = await _run(lambda: subprocess.run([cb, "auth", "status"], capture_output=True, text=True, timeout=8))
        logged_in = bool((json.loads(r.stdout or "{}") or {}).get("loggedIn"))
    except Exception:
        pass
    return jsonify({
        "ok": logged_in,
        "message": "Signed in with your Claude subscription." if logged_in
        else "Sign-in did not complete. Check the code and try again.",
    }), (200 if logged_in else 502)


@ai_bp.route("/api/chat", methods=["POST"])
@ai_bp.route("/ai_agent/api/chat", methods=["POST"])
async def start_chat():
    data = await request.get_json(silent=True) or {}
    prompt = (data.get("prompt") or data.get("text") or "").strip()
    msg_type = data.get("type", "prompt")
    model = data.get("model") or "Gemini 3.8 Flash (High)"
    conversation_id = data.get("conversation_id")
    token = data.get("token") or request.headers.get("Authorization", "").replace("Bearer ", "").strip()
    client_id = (data.get("client_id") or request.headers.get("X-Client-ID") or request.args.get("client_id") or "").strip()
    req_mode = data.get("mode") or ("steer" if msg_type == "steer" else ("queue" if msg_type == "queue_prompt" else "normal"))

    agent_mgr = current_app.agent_mgr
    security_mgr = current_app.security_mgr

    user = None
    if token:
        user = security_mgr.get_user_from_token(token, remote_addr=request.remote_addr, headers=request.headers)
    if not user:
        user = security_mgr.get_user_from_token(None, remote_addr=request.remote_addr, headers=request.headers)
    if not user:
        guest_name = guest_session.guest_username(request.headers)  # session cookie, never the IP
        user = {"username": guest_name, "name": "Guest", "role": "guest", "token_scope": "user"}

    base_user = user.get("username") or user.get("name") or "guest"
    slot_key = f"{base_user}::{client_id}" if client_id else base_user
    user = dict(user)
    user["username"] = base_user
    user["_slot_key"] = slot_key
    try:
        from agents import unlock_links
        user["_unlimited"] = unlock_links.is_unlimited(request.headers)
    except Exception:
        user["_unlimited"] = False

    from core.roles import is_admin_role
    is_role_admin = bool(user and is_admin_role(user.get("role")))
    # Everyone except admins must accept the Terms & Privacy first (enforced here, not only in the page)
    if not is_role_admin and msg_type in ("prompt", "steer", "queue_prompt") and not guest_session.terms_accepted(request.headers):
        return jsonify({"success": False, "terms_required": True,
                        "error": "Please accept the Terms & Privacy before using Siraugga."}), 403
    if guest_session.terms_accepted(request.headers):
        # Abuse guard explained in the terms: in-memory, daily-rotating hash; never stored
        user["_net_key"] = guest_session.network_key(guest_session.connection_address(request.headers, request.remote_addr))
    if hasattr(agent_mgr, "set_task_context"):
        agent_mgr.set_task_context(slot_key)
    admin_override = is_role_admin or (os.environ.get("ADMIN_OVERRIDE", "false").lower() == "true")

    target_project = (data.get("project") or "").strip()
    if target_project and hasattr(current_app, "project_mgr"):
        # The active project is shared by everyone, so only someone allowed may switch it
        # (root: admins only). Otherwise the chat still runs; the switch is just ignored.
        if security_mgr.can_switch_project(user, target_project):
            try:
                if target_project.lower() in security_mgr.ROOT_PROJECT_NAMES:
                    current_app.project_mgr.set_active_project("")
                elif target_project in current_app.project_mgr.list_projects(user=user):
                    from core.roles import tier_for_role
                    current_app.project_mgr.set_active_project(target_project, user_tier=tier_for_role(user.get("role")))
            except Exception:
                pass

    if msg_type == "cli_input":
        cli_in = data.get("input") or data.get("text") or prompt
        await agent_mgr.send_input(cli_in)
        return jsonify({"success": True, "message": "CLI input dispatched"})

    if msg_type == "cancel":
        if hasattr(agent_mgr, "cancel_task"):
            await agent_mgr.cancel_task(user=user)
        return jsonify({"success": True, "message": "Task cancelled"})

    if not prompt:
        return jsonify({"error": "Empty prompt provided"}), 400

    is_running = agent_mgr.is_running(slot_key) if hasattr(agent_mgr, "is_running") else False
    if is_running and req_mode != "queue":
        if not prompt.startswith("[STEER_NOW]\n"):
            prompt = f"[STEER_NOW]\n{prompt}"
        req_mode = "steer"

    if req_mode == "queue" and hasattr(agent_mgr, "queue_prompt"):
        clean_q = prompt[len("[QUEUE_NEXT]\n"):].strip() if prompt.startswith("[QUEUE_NEXT]\n") else prompt
        await agent_mgr.queue_prompt(clean_q, model=model, conversation_id=conversation_id, user=user, admin_override=admin_override)
        return jsonify({"success": True, "message": "Prompt queued", "mode": "queue", "conversation_id": conversation_id})
    elif req_mode == "steer" and hasattr(agent_mgr, "steer_task"):
        clean_s = prompt[len("[STEER_NOW]\n"):].strip() if prompt.startswith("[STEER_NOW]\n") else prompt
        await agent_mgr.steer_task(clean_s, model=model, conversation_id=conversation_id, user=user, admin_override=admin_override)
        return jsonify({"success": True, "message": "Task steered", "mode": "steer", "conversation_id": conversation_id})
    else:
        asyncio.create_task(agent_mgr.start_task(prompt, model=model, conversation_id=conversation_id, user=user, admin_override=admin_override))
        return jsonify({"success": True, "message": "Task started", "mode": "normal", "conversation_id": conversation_id})


@ai_bp.route("/api/stream", methods=["GET"])
@ai_bp.route("/ai_agent/api/stream", methods=["GET"])
@ai_bp.route("/stream", methods=["GET"])
async def get_stream():
    since_seq = request.args.get("since_seq", default=0, type=int)
    client_id = (request.headers.get("X-Client-ID") or request.args.get("client_id") or "").strip()
    token = request.headers.get("Authorization", "").replace("Bearer ", "").strip() or request.args.get("token", "").strip()
    agent_mgr = current_app.agent_mgr
    security_mgr = current_app.security_mgr

    user = security_mgr.get_user_from_token(token or None, remote_addr=request.remote_addr, headers=request.headers)
    if not user:
        base_user = guest_session.guest_username(request.headers)  # session cookie, never the IP
    else:
        base_user = user.get("username") or user.get("name") or "guest"
    if base_user.strip().lower() in ("admin", "michael (admin)", "michael"):
        base_user = "Michael (Admin)"
    slot_key = f"{base_user}::{client_id}" if client_id else base_user

    items = list(getattr(agent_mgr, "message_queue", []) or [])

    devcore_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    sf = Path(devcore_root) / ".runtime" / "stream_events.json"
    if sf.is_file():
        try:
            shared = json.loads(sf.read_text(encoding="utf-8"))
            if isinstance(shared, list):
                existing_seqs = {it.get("seq") for it in items if isinstance(it, dict)}
                for s in shared:
                    if isinstance(s, dict) and s.get("seq") not in existing_seqs:
                        items.append(s)
                items.sort(key=lambda x: x.get("seq", 0))
        except Exception:
            pass

    def _norm_base(val):
        if not val:
            return ""
        b = str(val).split("::", 1)[0].strip()
        return "Michael (Admin)" if b.lower() in ("admin", "michael (admin)", "michael") else b

    def _match_owner(item_owner):
        if not item_owner:
            return _norm_base(base_user) == "Michael (Admin)"
        if item_owner == slot_key:
            return True
        if "::" in str(item_owner) and "::" in str(slot_key):
            ib, ic = str(item_owner).split("::", 1)
            sb, sc = str(slot_key).split("::", 1)
            return _norm_base(ib) == _norm_base(sb) and ic == sc
        return _norm_base(item_owner) == _norm_base(slot_key)

    messages = []
    max_seq = since_seq
    for it in items:
        seq_val = it.get("seq", 0)
        if seq_val > since_seq:
            msg_obj = dict(it.get("msg", {}))
            item_owner = it.get("owner") or msg_obj.get("owner")
            if not _match_owner(item_owner):
                if seq_val > max_seq:
                    max_seq = seq_val
                continue
            if "seq" not in msg_obj:
                msg_obj["seq"] = seq_val
            messages.append(msg_obj)
            if seq_val > max_seq:
                max_seq = seq_val

    is_running = agent_mgr.is_running(slot_key) if hasattr(agent_mgr, "is_running") else False
    active_conv = agent_mgr.get_user_conversation_id(slot_key) if hasattr(agent_mgr, "get_user_conversation_id") else None
    return jsonify({
        "messages": messages,
        "last_seq": max_seq,
        "is_running": is_running,
        "heartbeat": time.time(),
        "active_conversation_id": active_conv
    })


@ai_bp.route("/api/heartbeat", methods=["GET", "POST"])
@ai_bp.route("/ai_agent/api/heartbeat", methods=["GET", "POST"])
@ai_bp.route("/api/ping", methods=["GET", "POST"])
@ai_bp.route("/ai_agent/api/ping", methods=["GET", "POST"])
@ai_bp.route("/heartbeat", methods=["GET", "POST"])
async def heartbeat_endpoint():
    agent_mgr = current_app.agent_mgr
    security_mgr = current_app.security_mgr
    client_id = (request.headers.get("X-Client-ID") or request.args.get("client_id") or "").strip()
    token = request.headers.get("Authorization", "").replace("Bearer ", "").strip() or request.args.get("token", "").strip()
    user = None
    if token:
        user = security_mgr.get_user_from_token(token, remote_addr=request.remote_addr, headers=request.headers)
    if not user:
        user = security_mgr.get_user_from_token(None, remote_addr=request.remote_addr, headers=request.headers)
    if not user:
        base_user = guest_session.guest_username(request.headers)  # session cookie, never the IP
    else:
        base_user = user.get("username") or user.get("name") or "guest"
    slot_key = f"{base_user}::{client_id}" if client_id else base_user

    is_running = agent_mgr.is_running(slot_key) if hasattr(agent_mgr, "is_running") else False
    return jsonify({
        "status": "alive",
        "time": time.time(),
        "is_running": is_running,
        "current_seq": getattr(agent_mgr, "current_seq", 0),
        "active_project": getattr(getattr(current_app, "project_mgr", None), "active_project", None)
    })


@ai_bp.route("/api/kill", methods=["POST"])
@ai_bp.route("/ai_agent/api/kill", methods=["POST"])
async def kill_chat():
    agent_mgr = current_app.agent_mgr
    security_mgr = current_app.security_mgr
    client_id = (request.headers.get("X-Client-ID") or request.args.get("client_id") or "").strip()
    token = request.headers.get("Authorization", "").replace("Bearer ", "").strip() or request.args.get("token", "").strip()
    user = security_mgr.get_user_from_token(token or None, remote_addr=request.remote_addr, headers=request.headers)
    if not user:
        user = {"username": guest_session.guest_username(request.headers), "name": "Guest", "role": "guest", "token_scope": "user"}
    base_user = user.get("username") or user.get("name") or "guest"
    slot_key = f"{base_user}::{client_id}" if client_id else base_user
    user = dict(user)
    user["username"] = base_user
    user["_slot_key"] = slot_key
    if hasattr(agent_mgr, "cancel_task"):
        await agent_mgr.cancel_task(user=user)
    return jsonify({"success": True, "message": "Task cancelled"})
