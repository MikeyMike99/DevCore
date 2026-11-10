"""
Guest identity from a session cookie (never the IP address).

Every browser gets a random `devcore_guest` cookie (HttpOnly, Secure, SameSite=Lax) on its
first visit. A guest is identified as "guest-<hash of that cookie>", so the cookie value itself
is never stored or logged. IP addresses are never used as an identity and never stored; the only
use is the in-memory, daily-rotating abuse guard below, after the visitor accepted the terms.

The cookie is set on the first response (see the after_request hook in core/server.py), so the
chat WebSocket, which opens after the page has loaded, already carries it.
"""
import hashlib
import re
import secrets
from http.cookies import SimpleCookie

COOKIE_NAME = "devcore_guest"
COOKIE_MAX_AGE = 30 * 86400
_VALID = re.compile(r"^[A-Za-z0-9_-]{32,64}$")


def new_session_id() -> str:
    return secrets.token_urlsafe(32)


def session_from_headers(headers) -> str:
    """The guest session id from a Cookie header, or '' when there is none (or it's malformed)."""
    try:
        raw = headers.get("Cookie", "") if headers else ""
        c = SimpleCookie()
        c.load(raw or "")
        val = c[COOKIE_NAME].value if COOKIE_NAME in c else ""
    except Exception:
        return ""
    return val if _VALID.match(val or "") else ""


def guest_name_for(session_id: str) -> str:
    return "guest-" + hashlib.sha256(("devcore-guest|" + session_id).encode()).hexdigest()[:20]


def current_session_id(headers=None) -> str:
    """The session id for this request: from the cookie, or a new one that the after_request hook
    will send to the browser. Outside a request (e.g. a WebSocket without the cookie) it falls
    back to a one-off id."""
    sid = session_from_headers(headers)
    if sid:
        return sid
    try:
        from quart import g
        sid = getattr(g, "devcore_guest_sid", "") or new_session_id()
        g.devcore_guest_sid = sid
        return sid
    except Exception:
        return new_session_id()


def guest_username(headers=None) -> str:
    return guest_name_for(current_session_id(headers))


# --------------------------------------------------------------------------- #
# Abuse guard (only after the visitor accepted the terms, which explain it)
# --------------------------------------------------------------------------- #
# A guest who clears cookies gets a new identity, and with it a fresh daily prompt limit. To stop
# that being abused, guest prompts are also capped per network per day. The IP address is never
# stored: it is turned into a keyed hash whose key lives only in memory and is replaced every day,
# so a hash can't be turned back into an IP or linked across days. The counts are kept in memory
# only (nothing is written to disk) and are dropped when the day changes or the server restarts.

import hmac
import threading
import time as _time

NETWORK_CAP_MULTIPLIER = 5  # e.g. 5 guests' worth of prompts per network per day (schools, offices)
_net_lock = threading.Lock()
_net = {"day": "", "key": b"", "counts": {}}


def _net_today():
    day = _time.strftime("%Y-%m-%d")
    if _net["day"] != day:
        _net.update(day=day, key=secrets.token_bytes(32), counts={})
    return _net


def network_key(raw_ip: str) -> str:
    """Daily-rotating keyed hash of the connection's address; '' when there is none."""
    raw_ip = str(raw_ip or "").strip()
    if not raw_ip:
        return ""
    with _net_lock:
        key = _net_today()["key"]
    return hmac.new(key, raw_ip.encode(), hashlib.sha256).hexdigest()[:24]


def network_take(net_key: str, per_guest_limit: int) -> bool:
    """Count one guest prompt for this network; False when today's network cap is reached."""
    cap = max(1, int(per_guest_limit or 1)) * NETWORK_CAP_MULTIPLIER
    with _net_lock:
        counts = _net_today()["counts"]
        if counts.get(net_key, 0) >= cap:
            return False
        counts[net_key] = counts.get(net_key, 0) + 1
    return True


# --------------------------------------------------------------------------- #
# Terms & Privacy acceptance
# --------------------------------------------------------------------------- #

TERMS_VERSION = "2026-11-09"
TERMS_COOKIE = "devcore_terms"


def terms_accepted(headers) -> bool:
    try:
        c = SimpleCookie()
        c.load(headers.get("Cookie", "") if headers else "")
        return TERMS_COOKIE in c and c[TERMS_COOKIE].value == TERMS_VERSION
    except Exception:
        return False


def connection_address(headers, remote_addr) -> str:
    """The address the request came from (via Cloudflare), used ONLY for network_key()."""
    h = headers or {}
    return (h.get("CF-Connecting-IP") or (h.get("X-Forwarded-For") or "").split(",")[0].strip() or str(remote_addr or "")).strip()
