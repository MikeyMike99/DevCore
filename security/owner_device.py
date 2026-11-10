"""
Trusted owner devices: lets the owner be Super Admin on the public domain (mikeytech.dev) from
their own browser, without trusting an IP address.

Why not the IP: through Cloudflare every request looks like it comes from the internet, and the
owner's public IP is shared by every device on their network (and sometimes other ISP
customers). Trusting it would make all of them Super Admin.

How it works instead:
  1. On the host itself (localhost: already verified as owner by the master key + a direct local
     connection), the owner asks for a handoff. The server makes a random single-use code that
     expires in HANDOFF_TTL seconds and is kept in memory only (as a hash).
  2. The browser opens https://<domain>/owner-device/claim?code=... ; the server consumes the
     code and sets a random device cookie (HttpOnly, Secure, SameSite=Strict) on the domain.
  3. Requests carrying a known, unexpired device cookie count as the host owner.

Only SHA-256 hashes of codes and device cookies are stored. Devices can be revoked all at once.
SameSite=Strict means other websites can't make the browser send the cookie (no CSRF).
"""
import hashlib
import json
import os
import secrets
import threading
import time
from http.cookies import SimpleCookie

COOKIE_NAME = "devcore_owner_device"
HINT_COOKIE = "devcore_owner_hint"   # "1" only; not a credential (lets the page renew silently)
DEVICE_TTL = 365 * 86400         # a trusted browser stays trusted for a year (revoke-all undoes it)
HANDOFF_TTL = 120                # a handoff code works once, within 2 minutes
STORE_FILE = os.path.expanduser("~/.config/devcore/owner_devices.json")

_lock = threading.Lock()
_handoffs = {}                   # sha256(code) -> expires_at   (memory only)


def _h(value: str) -> str:
    return hashlib.sha256(("devcore-owner-device|" + value).encode()).hexdigest()


def _load() -> dict:
    try:
        with open(STORE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save(devices: dict) -> None:
    os.makedirs(os.path.dirname(STORE_FILE), mode=0o700, exist_ok=True)
    tmp = STORE_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(devices, f)
    try:
        os.chmod(tmp, 0o600)
    except Exception:
        pass
    os.replace(tmp, STORE_FILE)


def new_handoff() -> str:
    """A single-use code for the owner's browser to claim on the domain. Call only after the
    request was verified as the host owner via a direct local connection."""
    code = secrets.token_urlsafe(32)
    now = time.time()
    with _lock:
        for k in [k for k, exp in _handoffs.items() if exp <= now]:
            _handoffs.pop(k, None)
        _handoffs[_h(code)] = now + HANDOFF_TTL
    return code


def claim(code: str, label: str = "") -> str:
    """Consume a handoff code and return a new device secret to put in the cookie, or '' when the
    code is unknown, used or expired."""
    if not code or len(code) > 100:
        return ""
    now = time.time()
    with _lock:
        exp = _handoffs.pop(_h(code), None)
        if not exp or exp <= now:
            return ""
        secret = secrets.token_urlsafe(32)
        devices = {k: v for k, v in _load().items() if float(v.get("expires_at", 0)) > now}
        devices[_h(secret)] = {"created_at": now, "expires_at": now + DEVICE_TTL, "label": str(label)[:120]}
        _save(devices)
    return secret


def _cookie_value(headers) -> str:
    try:
        c = SimpleCookie()
        c.load((headers.get("Cookie", "") if headers else "") or "")
        return c[COOKIE_NAME].value if COOKIE_NAME in c else ""
    except Exception:
        return ""


def is_trusted(headers) -> bool:
    """True when the request carries the cookie of a trusted, unexpired owner device."""
    secret = _cookie_value(headers)
    if not secret or len(secret) > 100:
        return False
    rec = _load().get(_h(secret))
    return bool(rec and float(rec.get("expires_at", 0)) > time.time())


def count() -> int:
    now = time.time()
    return sum(1 for v in _load().values() if float(v.get("expires_at", 0)) > now)


def revoke_all() -> int:
    with _lock:
        n = len(_load())
        _save({})
        _handoffs.clear()
    return n
