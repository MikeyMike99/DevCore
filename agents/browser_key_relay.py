"""
Browser-held key relay ("bring your own key, kept in your browser").

The guest's Gemini API key lives only in their browser. When their agent task runs,
`agy` is started with a placeholder key and GOOGLE_GEMINI_BASE_URL pointing at
/internal/llm-relay/<token>/ on this server. Each model request is forwarded over the
guest's own WebSocket to their browser, which attaches the real key, calls
generativelanguage.googleapis.com directly and streams the response back here.

The real key never reaches the server process, its disk, its logs or the agent.
"""
import asyncio
import json
import os
import re
import secrets
import time
import uuid

TERMS_VERSION = "2026-11-08"
PLACEHOLDER_KEY = "DEVCORE_BROWSER_RELAY_PLACEHOLDER"
ALLOWED_METHODS = ("streamGenerateContent", "generateContent", "countTokens")
_MODEL_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_ALLOWED_QUERY_KEYS = ("alt",)

FIRST_BYTE_TIMEOUT = 120.0
IDLE_TIMEOUT = 300.0

_SESSIONS = {}  # token -> {"slot": slot_key, "created": ts}
_PENDING = {}   # request id -> {"slot": slot_key, "token": token, "queue": asyncio.Queue}


def internal_base_url() -> str:
    return (os.environ.get("DEVCORE_INTERNAL_URL") or "http://127.0.0.1:5000").rstrip("/")


def create_session(slot_key: str, server_key: str = None) -> str:
    """server_key set = the server itself attaches that key and calls Google (shared demo key);
    unset = the request goes to the guest's browser, which attaches the guest's own key."""
    token = secrets.token_urlsafe(32)
    _SESSIONS[token] = {"slot": slot_key, "created": time.time(), "server_key": server_key}
    return token


def session_server_key(token: str):
    sess = _SESSIONS.get(token or "")
    return sess.get("server_key") if sess else None


# ---- Shared demo key (owner's budget-capped key, used server-side only) -------------------
DEMO_KEY_FILE = os.path.expanduser("~/.config/devcore/demo_gemini.key")
GOOGLE_API_BASE = (os.environ.get("DEVCORE_GEMINI_UPSTREAM") or "https://generativelanguage.googleapis.com").rstrip("/") + "/v1beta/models"
_DEMO_USAGE = {"day": "", "count": 0}


def demo_server_key():
    """The owner's shared demo key: env DEVCORE_DEMO_GEMINI_KEY, else ~/.config/devcore/demo_gemini.key.
    Kept outside every workspace and never put in the agent's environment."""
    key = (os.environ.get("DEVCORE_DEMO_GEMINI_KEY") or "").strip()
    if not key:
        try:
            with open(DEMO_KEY_FILE, "r", encoding="utf-8") as f:
                key = f.read().strip()
        except Exception:
            key = ""
    return key or None


def demo_daily_limit() -> int:
    try:
        return max(0, int(os.environ.get("DEVCORE_DEMO_DAILY_REQUESTS", "500")))
    except Exception:
        return 500


def take_demo_request() -> bool:
    """Counts one model request against the shared demo key's daily cap. False = cap reached."""
    today = time.strftime("%Y-%m-%d")
    if _DEMO_USAGE["day"] != today:
        _DEMO_USAGE["day"], _DEMO_USAGE["count"] = today, 0
    if _DEMO_USAGE["count"] >= demo_daily_limit():
        return False
    _DEMO_USAGE["count"] += 1
    return True


def end_session(token: str) -> None:
    if not token:
        return
    _SESSIONS.pop(token, None)
    for rid, pend in list(_PENDING.items()):
        if pend["token"] == token:
            pend["queue"].put_nowait({"kind": "end", "error": "Task finished"})


def session_slot(token: str):
    sess = _SESSIONS.get(token or "")
    return sess["slot"] if sess else None


def split_model_method(model_method: str):
    """'gemini-3.8-flash:streamGenerateContent' -> ('gemini-3.8-flash', 'streamGenerateContent') or None."""
    if ":" not in (model_method or ""):
        return None
    model, method = model_method.rsplit(":", 1)
    if method not in ALLOWED_METHODS or not _MODEL_RE.match(model):
        return None
    return model, method


def safe_query(args) -> dict:
    return {k: str(args.get(k)) for k in _ALLOWED_QUERY_KEYS if args.get(k) and re.match(r"^[A-Za-z0-9_-]{1,16}$", str(args.get(k)))}


def _client_queues_for(agent_mgr, slot_key):
    return [q for q, owner in list(getattr(agent_mgr, "connected_clients", {}).items()) if owner and owner == slot_key]


async def open_request(agent_mgr, token: str, model: str, method: str, query: dict, body_text: str):
    """Send one model request to the guest's browser. Returns (request_id, queue) or raises LookupError."""
    slot = session_slot(token)
    if not slot:
        raise LookupError("Unknown or expired relay session")
    targets = _client_queues_for(agent_mgr, slot)
    if not targets:
        raise LookupError("Your browser tab is not connected, so your API key is unavailable. Keep the tab open while the agent runs.")
    rid = uuid.uuid4().hex
    queue = asyncio.Queue()
    _PENDING[rid] = {"slot": slot, "token": token, "queue": queue}
    frame = json.dumps({
        "type": "llm_relay_request",
        "id": rid,
        "model": model,
        "method": method,
        "query": query,
        "body": body_text,
        "owner": slot,
    })
    # Only the most recently connected tab of this slot answers, so one request is never answered twice.
    try:
        targets[-1].put_nowait(frame)
    except Exception:
        _PENDING.pop(rid, None)
        raise LookupError("Could not reach your browser tab")
    return rid, queue


def close_request(rid: str) -> None:
    _PENDING.pop(rid, None)


def deliver_from_browser(slot_key: str, data: dict) -> bool:
    """Route an llm_relay_* frame from a browser to its pending request. Ignores frames from any other slot."""
    rid = str(data.get("id") or "")
    pend = _PENDING.get(rid)
    if not pend or pend["slot"] != slot_key:
        return False
    mtype = data.get("type")
    if mtype == "llm_relay_response":
        pend["queue"].put_nowait({"kind": "start", "status": int(data.get("status") or 502), "content_type": str(data.get("content_type") or "application/json")[:100]})
    elif mtype == "llm_relay_chunk":
        pend["queue"].put_nowait({"kind": "chunk", "data": str(data.get("data") or "")})
    elif mtype == "llm_relay_end":
        pend["queue"].put_nowait({"kind": "end", "error": data.get("error")})
    else:
        return False
    return True


def is_relay_frame(data) -> bool:
    return isinstance(data, dict) and str(data.get("type", "")).startswith("llm_relay_")
