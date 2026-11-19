"""Serves the live Linux terminal on Siraugga's own address (https://siraugga.mikeytech.dev/lab/t/<link>/).

The learner's browser only ever talks to Siraugga. This module passes the terminal page and its live connection
on to the Lab Cloud, which runs on this server (SIRAUGGA_LAB_URL, normally http://127.0.0.1:8788).

Safety rules:
  * The signed, expiring link in the address IS the key; the Lab Cloud checks it. No link, no terminal.
  * Only the shape of address a terminal needs is passed on (letters, digits, - _ . /). Nothing else can reach the lab.
  * The target is always the configured Lab Cloud, never an address taken from the request (no SSRF).
  * Read-only for web pages (GET); the live connection is a websocket. Size and connection limits apply.
"""
import asyncio
import logging
import os
import re
import time

import httpx
from quart import Response, websocket

from core import lab_cloud, lab_capacity

log = logging.getLogger("siraugga.lab_proxy")

PREFIX = lab_cloud.PROXY_PREFIX                      # "/lab"
_TOKEN = re.compile(r"^[A-Za-z0-9_.\-]{16,700}$")     # payload.signature (base64url + hex)
_REST = re.compile(r"^[A-Za-z0-9_.\-/]{0,120}$")
MAX_BODY = 4 * 1024 * 1024
MAX_WS = lab_capacity.MAX_TERMINALS                   # live terminals at once (see core/lab_capacity.py for the full rules)
_PASS_HEADERS = ("content-type", "cache-control", "etag", "last-modified")


def _clean(token: str, rest: str) -> bool:
    return bool(_TOKEN.fullmatch(token or "")) and bool(_REST.fullmatch(rest or "")) and ".." not in (rest or "")


def _upstream_http(token: str, rest: str) -> str:
    return os.environ["SIRAUGGA_LAB_URL"].rstrip("/") + f"/t/{token}/{rest}"


def _upstream_ws(token: str, rest: str) -> str:
    base = os.environ["SIRAUGGA_LAB_URL"].rstrip("/")
    base = "wss://" + base[len("https://"):] if base.startswith("https://") else "ws://" + base[len("http://"):]
    return f"{base}/t/{token}/{rest}"


async def _page(token: str, rest: str = ""):
    if not lab_cloud.configured() or not _clean(token, rest):
        return Response("Not found", status=404)
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(100.0, connect=3.0)) as c:
            r = await c.get(_upstream_http(token, rest), headers={"Accept-Encoding": "identity"})
    except (httpx.HTTPError, OSError):
        return Response("The practice terminal is not ready. Please try again in a minute.", status=503,
                        headers={"Cache-Control": "no-store"})
    if len(r.content) > MAX_BODY:
        return Response("Too large", status=502)
    headers = {k: v for k, v in r.headers.items() if k.lower() in _PASS_HEADERS}
    headers["Cache-Control"] = "no-store"
    headers["X-Content-Type-Options"] = "nosniff"
    headers["Referrer-Policy"] = "no-referrer"
    # The terminal page is allowed to be shown inside Siraugga's own pages, and nowhere else.
    headers["Content-Security-Policy"] = "frame-ancestors 'self'"
    return Response(r.content, status=r.status_code, headers=headers)


async def _socket(token: str, rest: str = ""):
    import websockets
    if not lab_cloud.configured() or not _clean(token, rest):
        await websocket.close(1008)
        return
    conn, why = lab_capacity.acquire(token)       # a place under the memory-aware ceiling and the per-learner limit
    if conn is None:
        log.info("terminal refused (%s)", why)
        await websocket.close(1008)
        return
    wanted = list(getattr(websocket, "requested_subprotocols", []) or [])
    last = [time.monotonic()]                      # last time anything moved in either direction
    try:
        async with websockets.connect(_upstream_ws(token, rest), subprotocols=wanted or None,
                                      max_size=2 ** 20, open_timeout=100, ping_interval=20) as up:
            await websocket.accept(subprotocol=up.subprotocol)

            async def down():            # browser -> terminal
                while True:
                    msg = await websocket.receive()
                    last[0] = time.monotonic()
                    await up.send(msg)

            async def back():            # terminal -> browser
                async for msg in up:
                    last[0] = time.monotonic()
                    await websocket.send(msg)

            async def idle_watch():      # an abandoned terminal gives its place back
                while lab_capacity.idle_for(last[0]) < lab_capacity.current_idle_limit():   # shorter when we are busy or full
                    await asyncio.sleep(15)
                log.info("terminal closed after %ds idle", int(lab_capacity.idle_for(last[0])))

            tasks = [asyncio.ensure_future(down()), asyncio.ensure_future(back()), asyncio.ensure_future(idle_watch())]
            try:
                await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            finally:
                for t in tasks:
                    t.cancel()
    except asyncio.CancelledError:
        raise
    except Exception as e:                # unreachable lab, expired link, closed terminal: just end the connection
        log.info("terminal connection ended: %s", type(e).__name__)
        try:
            await websocket.close(1011)
        except Exception:
            pass
    finally:
        lab_capacity.release(conn)


def attach(bp):
    """Add the terminal routes to a blueprint (called once from core/routes/projects.py)."""
    async def lab_terminal_page(token, rest=""):
        return await _page(token, rest)

    async def lab_terminal_socket(token, rest=""):
        return await _socket(token, rest)

    bp.add_url_rule(f"{PREFIX}/t/<token>/", view_func=lab_terminal_page, endpoint="lab_terminal_page", methods=["GET"])
    bp.add_url_rule(f"{PREFIX}/t/<token>/<path:rest>", view_func=lab_terminal_page, endpoint="lab_terminal_page_rest", methods=["GET"])
    bp.add_websocket(f"{PREFIX}/t/<token>/<path:rest>", endpoint="lab_terminal_socket", view_func=lab_terminal_socket)
