"""
Reusable "no limit" links.

An admin creates a link (/unlock/<code>). Every visitor who opens it and presses the
popup's button gets a browser cookie that lifts their daily prompt limit, until the link
expires or is revoked. Only hashes of the code and the browser tokens are stored, and
revoking a link also ends unlimited access for every browser that used it.
"""
import hashlib
import json
import os
import secrets
import threading
import time
from http.cookies import SimpleCookie

DEVCORE_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STORE_FILE = os.path.join(DEVCORE_ROOT, "data", "unlock_links.json")
PUBLIC_URL = (os.environ.get("DEVCORE_PUBLIC_URL") or "https://mikeytech.dev").rstrip("/")
COOKIE_NAME = "devcore_unlimited"
COOKIE_MAX_AGE = 365 * 86400
DEFAULT_TTL_DAYS = 14
MAX_USES = 1000  # browsers per link

_lock = threading.RLock()
_cache = {"mtime": None, "data": {}}


def _h(value: str) -> str:
    return hashlib.sha256(str(value).encode()).hexdigest()


def _load() -> dict:
    try:
        mtime = os.path.getmtime(STORE_FILE)
    except OSError:
        return {}
    if _cache["mtime"] != mtime:
        try:
            with open(STORE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            _cache.update(mtime=mtime, data=data if isinstance(data, dict) else {})
        except Exception:
            return {}
    return _cache["data"]


def _save(data: dict) -> None:
    os.makedirs(os.path.dirname(STORE_FILE), exist_ok=True)
    tmp = STORE_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=1)
    os.replace(tmp, STORE_FILE)
    _cache["mtime"] = None


def create(label: str = "", ttl_days: int = DEFAULT_TTL_DAYS) -> dict:
    code = secrets.token_urlsafe(16)
    now = time.time()
    entry = {"id": _h(code)[:10], "label": str(label or "")[:80], "created": now,
             "expires": now + max(1, int(ttl_days)) * 86400, "token_hashes": [], "last_used": None, "revoked": False}
    with _lock:
        data = dict(_load())
        data[_h(code)] = entry
        _save(data)
    return {**entry, "url": f"{PUBLIC_URL}/unlock/{code}"}


def _hashes(e: dict) -> list:
    """Browser tokens issued by this link (older entries kept a single 'token_hash')."""
    hs = list(e.get("token_hashes") or [])
    if e.get("token_hash") and e["token_hash"] not in hs:
        hs.append(e["token_hash"])
    return hs


def status(code: str) -> str:
    """'ok', 'full', 'expired', 'revoked' or 'invalid'. A link stays 'ok' however often it is used."""
    e = _load().get(_h(code or ""))
    if not e:
        return "invalid"
    if e.get("revoked"):
        return "revoked"
    if e["expires"] < time.time():
        return "expired"
    if len(_hashes(e)) >= MAX_USES:
        return "full"
    return "ok"


def claim(code: str):
    """Use the link (any number of browsers). Returns the browser token for the cookie, or None."""
    with _lock:
        data = dict(_load())
        key = _h(code or "")
        e = data.get(key)
        if not e or e.get("revoked") or e["expires"] < time.time() or len(_hashes(e)) >= MAX_USES:
            return None
        token = secrets.token_urlsafe(32)
        e = dict(e, token_hashes=_hashes(e) + [_h(token)], last_used=time.time())
        e.pop("token_hash", None)
        e.pop("claimed", None)
        data[key] = e
        _save(data)
    return token


def _token_from_headers(headers) -> str:
    try:
        raw = headers.get("Cookie", "") if headers else ""
        c = SimpleCookie()
        c.load(raw)
        return c[COOKIE_NAME].value if COOKIE_NAME in c else ""
    except Exception:
        return ""


def is_unlimited(headers) -> bool:
    token = _token_from_headers(headers)
    if not token:
        return False
    th = _h(token)
    # Browsers keep no-limit access after the link expires; revoking the link ends it
    return any(th in _hashes(e) and not e.get("revoked") for e in _load().values())


def list_links() -> list:
    out = []
    for e in _load().values():
        st = "revoked" if e.get("revoked") else "expired" if e["expires"] < time.time() else "active"
        out.append({"id": e["id"], "label": e.get("label", ""), "created": e["created"], "expires": e["expires"],
                    "uses": len(_hashes(e)), "last_used": e.get("last_used") or e.get("claimed"), "status": st})
    return sorted(out, key=lambda x: -x["created"])


def revoke(link_id: str) -> bool:
    with _lock:
        data = dict(_load())
        for k, e in data.items():
            if e.get("id") == link_id:
                data[k] = dict(e, revoked=True)
                _save(data)
                return True
    return False
