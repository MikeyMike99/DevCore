"""Admin authentication for CyberBrief, delegated to DevCore (Siraugga).

CyberBrief has no login of its own. For /admin/notify* requests the ASGI router in
app.py asks DevCore's SecurityManager who the caller is (bearer token, direct local
connection, or the owner's trusted-device cookie). Only when DevCore says "admin"
does the router attach HEADER with a random per-process SECRET. Any copy of that
header sent by a client is stripped first, so it cannot be forged from outside.
"""
import hmac
import secrets

HEADER = "x-cyberbrief-admin"
_HEADER_B = HEADER.encode("latin-1")
SECRET = secrets.token_urlsafe(32)  # new on every server start; never stored or logged

ADMIN_PREFIX = "/admin/notify"
ADMIN_PREFIXES = (ADMIN_PREFIX, "/chat/admin")


def strip_and_mark(scope, security_mgr) -> dict:
    """Return a copy of an ASGI http scope without any client-sent admin header,
    plus our own header when DevCore confirms the caller is an admin."""
    raw = [(k, v) for k, v in scope.get("headers", []) if k.lower() != _HEADER_B]
    if scope.get("path", "").startswith(ADMIN_PREFIXES) and _devcore_admin(scope, raw, security_mgr):
        raw.append((_HEADER_B, SECRET.encode("latin-1")))
    return dict(scope, headers=raw)


def _devcore_admin(scope, raw_headers, security_mgr) -> bool:
    if security_mgr is None:
        return False
    try:
        from werkzeug.datastructures import Headers  # case-insensitive .get()

        headers = Headers([(k.decode("latin-1"), v.decode("latin-1")) for k, v in raw_headers])
        token = headers.get("Authorization", "").replace("Bearer ", "").strip() or None
        client = scope.get("client") or ("", 0)
        user = security_mgr.get_user_from_token(token, remote_addr=client[0], headers=headers)
        return bool(user) and bool(security_mgr.is_admin_user(user))
    except Exception:
        return False


def request_is_admin(flask_request) -> bool:
    """Used inside the Flask app: true only for requests the router marked."""
    return hmac.compare_digest(flask_request.headers.get(HEADER, ""), SECRET)
