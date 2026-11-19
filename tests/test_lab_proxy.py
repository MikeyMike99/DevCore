"""The live terminal is served from Siraugga's own address: page + live connection are passed on to the lab,
and nothing else can be reached through it. Uses a fake lab, so it needs no Docker."""
import asyncio
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from aiohttp import web, WSMsgType  # noqa: E402
from quart import Blueprint, Quart  # noqa: E402

from core import lab_cloud, lab_proxy  # noqa: E402

TOKEN = "abcdefghijklmnop.0123456789abcdef0123456789abcdef"
SEEN = []


async def _fake_lab():
    async def page(request):
        SEEN.append(request.path)
        if request.match_info["token"] != TOKEN:
            return web.json_response({"error": "link expired or invalid"}, status=401)
        return web.Response(text="<html>ttyd fake</html>", content_type="text/html",
                            headers={"Content-Security-Policy": "frame-ancestors https://elsewhere.example"})

    async def sock(request):
        ws = web.WebSocketResponse(protocols=["tty"])
        await ws.prepare(request)
        async for m in ws:
            if m.type == WSMsgType.TEXT:
                await ws.send_str("echo:" + m.data)
            elif m.type == WSMsgType.BINARY:
                await ws.send_bytes(b"echo:" + m.data)
        return ws

    app = web.Application()
    app.router.add_get("/t/{token}/ws", sock)
    app.router.add_get("/t/{token}/{rest:.*}", page)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    return runner, site._server.sockets[0].getsockname()[1]


def _site():
    app = Quart(__name__)
    bp = Blueprint("t", __name__)
    lab_proxy.attach(bp)
    app.register_blueprint(bp)
    return app


class LabProxyTests(unittest.TestCase):
    def setUp(self):
        self._env = {k: os.environ.get(k) for k in ("SIRAUGGA_LAB_URL", "SIRAUGGA_LAB_SECRET", "SIRAUGGA_LAB_PUBLIC_URL")}
        os.environ["SIRAUGGA_LAB_SECRET"] = "unit"
        os.environ.pop("SIRAUGGA_LAB_PUBLIC_URL", None)
        SEEN.clear()

    def tearDown(self):
        for k, v in self._env.items():
            os.environ.pop(k, None) if v is None else os.environ.__setitem__(k, v)

    def _run(self, coro):
        return asyncio.run(coro)

    def test_default_terminal_address_is_this_site(self):
        os.environ["SIRAUGGA_LAB_URL"] = "http://127.0.0.1:9"
        self.assertEqual(lab_cloud.public_url(), "/lab")
        self.assertEqual(lab_cloud.public_origin(), "")          # nothing extra to allow in the page's frame list

    def test_page_is_passed_on_and_cannot_be_framed_elsewhere(self):
        async def go():
            runner, port = await _fake_lab()
            os.environ["SIRAUGGA_LAB_URL"] = f"http://127.0.0.1:{port}"
            try:
                r = await _site().test_client().get(f"/lab/t/{TOKEN}/")
                body = await r.get_data()
                return r.status_code, body, {k.lower(): v for k, v in r.headers.items()}
            finally:
                await runner.cleanup()
        code, body, headers = self._run(go())
        self.assertEqual(code, 200)
        self.assertIn(b"ttyd fake", body)
        self.assertEqual(headers["content-security-policy"], "frame-ancestors 'self'")   # the lab's own header is replaced
        self.assertIn("no-store", headers["cache-control"])

    def test_bad_links_and_paths_never_reach_the_lab(self):
        async def go():
            runner, port = await _fake_lab()
            os.environ["SIRAUGGA_LAB_URL"] = f"http://127.0.0.1:{port}"
            try:
                c = _site().test_client()
                out = []
                for path in ("/lab/t/short/", f"/lab/t/{TOKEN}/..%2f..%2fadmin", f"/lab/t/{TOKEN}/a b", f"/lab/t/{TOKEN};x/",
                             f"/lab/t/{TOKEN}/%00"):
                    out.append((await c.get(path)).status_code)
                out.append((await c.post(f"/lab/t/{TOKEN}/", data=b"x")).status_code)     # read-only
                return out
            finally:
                await runner.cleanup()
        codes = self._run(go())
        self.assertTrue(all(c in (400, 404, 405) for c in codes), codes)
        self.assertEqual(SEEN, [], "a rejected request reached the lab")

    def test_expired_link_is_refused_by_the_lab(self):
        async def go():
            runner, port = await _fake_lab()
            os.environ["SIRAUGGA_LAB_URL"] = f"http://127.0.0.1:{port}"
            try:
                return (await _site().test_client().get("/lab/t/" + "z" * 20 + ".00ff/")).status_code
            finally:
                await runner.cleanup()
        self.assertEqual(self._run(go()), 401)

    def test_lab_down_gives_a_friendly_message(self):
        os.environ["SIRAUGGA_LAB_URL"] = "http://127.0.0.1:9"
        async def go():
            r = await _site().test_client().get(f"/lab/t/{TOKEN}/")
            return r.status_code, (await r.get_data()).decode()
        code, text = self._run(go())
        self.assertEqual(code, 503)
        self.assertIn("not ready", text)
        self.assertNotIn("127.0.0.1", text)                       # no internal address leaks

    def test_off_when_not_configured(self):
        os.environ.pop("SIRAUGGA_LAB_URL", None)
        async def go():
            return (await _site().test_client().get(f"/lab/t/{TOKEN}/")).status_code
        self.assertEqual(self._run(go()), 404)

    def test_live_connection_is_relayed_both_ways(self):
        async def go():
            runner, port = await _fake_lab()
            os.environ["SIRAUGGA_LAB_URL"] = f"http://127.0.0.1:{port}"
            try:
                async with _site().test_client().websocket(f"/lab/t/{TOKEN}/ws", subprotocols=["tty"]) as ws:
                    await ws.send("hello")
                    a = await asyncio.wait_for(ws.receive(), 10)
                    await ws.send(b"\x01\x02")
                    b = await asyncio.wait_for(ws.receive(), 10)
                    return a, b
            finally:
                await runner.cleanup()
        a, b = self._run(go())
        self.assertEqual(a, "echo:hello")
        self.assertEqual(b, b"echo:\x01\x02")

    def test_clean_rules(self):
        self.assertTrue(lab_proxy._clean(TOKEN, "ws"))
        self.assertTrue(lab_proxy._clean(TOKEN, ""))
        for bad_rest in ("../x", "a/../b", "a b", "a?b", "%2e%2e", "a\n"):
            self.assertFalse(lab_proxy._clean(TOKEN, bad_rest), bad_rest)
        for bad_tok in ("", "short", TOKEN + "/", TOKEN + "?x", "a" * 800):
            self.assertFalse(lab_proxy._clean(bad_tok, ""), bad_tok)


if __name__ == "__main__":
    unittest.main()
