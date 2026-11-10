"""Bridge from DevCore's public entry point to the local e-profile backend.

The e-profile site on Cloudflare Pages forwards its dynamic requests (login, admin
panel, projects, blog, ...) through the tunnel to DevCore with the header
`X-EProfile-Proxy: <PROXY_SECRET>`. Only requests carrying that exact secret are
streamed to the e-profile server on 127.0.0.1:EPROFILE_PORT (scripts/eprofile_server.sh).
Everything else, and every CyberBrief path, continues to DevCore untouched. The
secret header is always removed before a request goes anywhere.

Settings live in services/eprofile_bridge/.env (gitignored):
  PROXY_SECRET=...      same value as the Pages env var ORIGIN_SECRET
  EPROFILE_PORT=5100
"""
from __future__ import annotations

import hmac
from pathlib import Path

from dotenv import dotenv_values

HEADER = b"x-eprofile-proxy"
_CFG = {k: v for k, v in dotenv_values(Path(__file__).with_name(".env")).items() if v}
SECRET = _CFG.get("PROXY_SECRET", "")
PORT = int(_CFG.get("EPROFILE_PORT", "5100"))
MAX_BODY = 25 * 1024 * 1024
_HOP = {b"connection", b"keep-alive", b"transfer-encoding", b"te", b"trailer", b"upgrade",
        b"proxy-authorization", b"proxy-authenticate", b"host", b"content-length"}

OFFLINE_HTML = (b"<!doctype html><meta charset=utf-8><title>Offline</title>"
                b"<p>The e-profile backend is not running right now.</p>")


def _strip(scope) -> tuple[dict, bool]:
    """Remove the proxy header; report whether it carried the right secret."""
    ok = False
    kept = []
    for k, v in scope.get("headers", []):
        if k.lower() == HEADER:
            ok = ok or (bool(SECRET) and hmac.compare_digest(v.decode("latin-1"), SECRET))
        else:
            kept.append((k, v))
    return dict(scope, headers=kept), ok


def _relative_location(value: bytes) -> bytes:
    """e-profile only knows itself as 127.0.0.1:PORT, so absolute redirects it builds
    (e.g. Flask's /path -> /path/ slash redirect) would send visitors to the PC's
    internal address. Turn those into site-relative redirects."""
    import re
    return re.sub(rb"^https?://(?:127\.0\.0\.1|localhost)(?::\d+)?(?=/|$)", b"", value) or b"/"


async def _respond(send, status: int, body: bytes, ctype=b"text/html; charset=utf-8"):
    await send({"type": "http.response.start", "status": status,
                "headers": [(b"content-type", ctype), (b"cache-control", b"no-store")]})
    await send({"type": "http.response.body", "body": body})


def mount(inner, owns_path=lambda p: False):
    """Wrap `inner` (DevCore + CyberBrief). `owns_path(path)` marks paths that must stay
    with `inner` even when they arrive through the e-profile proxy (CyberBrief)."""
    import httpx

    client = httpx.AsyncClient(timeout=httpx.Timeout(120.0, connect=3.0), follow_redirects=False)

    async def router(scope, receive, send):
        if scope["type"] != "http":
            return await inner(scope, receive, send)
        scope, via_proxy = _strip(scope)
        if not via_proxy or owns_path(scope.get("path", "")):
            return await inner(scope, receive, send)

        body = bytearray()
        while True:
            msg = await receive()
            body += msg.get("body", b"")
            if len(body) > MAX_BODY:
                return await _respond(send, 413, b"Request too large")
            if not msg.get("more_body"):
                break

        path = scope.get("raw_path") or scope["path"].encode()
        url = f"http://127.0.0.1:{PORT}{path.decode('latin-1')}"
        if scope.get("query_string"):
            url += "?" + scope["query_string"].decode("latin-1")
        headers = [(k, v) for k, v in scope["headers"] if k.lower() not in _HOP]
        try:
            req = client.build_request(scope["method"], url, headers=headers, content=bytes(body))
            resp = await client.send(req, stream=True)
        except httpx.HTTPError:
            # 502 makes the Pages proxy show its own "offline" page.
            return await _respond(send, 502, OFFLINE_HTML)
        try:
            out_headers = []
            for k, v in resp.headers.raw:
                if k.lower() in _HOP:
                    continue
                if k.lower() == b"location":
                    v = _relative_location(v)
                out_headers.append((k, v))
            await send({"type": "http.response.start", "status": resp.status_code, "headers": out_headers})
            async for chunk in resp.aiter_raw():
                await send({"type": "http.response.body", "body": chunk, "more_body": True})
            await send({"type": "http.response.body", "body": b""})
        finally:
            await resp.aclose()

    return router
