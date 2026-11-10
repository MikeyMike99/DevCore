"""Tests for the CyberBrief admin page and its DevCore-delegated login.
Run from the DevCore root:  python -m unittest services.cyberbrief.test_admin
Works on a temporary subscriber file and never sends mail."""
import asyncio
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from . import admin_gate, notify_mod
from .app import create_app, mount
from .config import Config


class FakeSecurity:
    """Stands in for DevCore's SecurityManager."""

    def __init__(self, admin_token="good-token"):
        self.admin_token = admin_token

    def get_user_from_token(self, token, remote_addr=None, headers=None):
        return {"role": "admin"} if token == self.admin_token else None

    def is_admin_user(self, user):
        return bool(user and user.get("role") == "admin")


class AdminPageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.orig_file = notify_mod.SUBSCRIBERS_FILE
        notify_mod.SUBSCRIBERS_FILE = self.tmp / "subscribers.json"
        notify_mod.SUBSCRIBERS_FILE.write_text("[]", encoding="utf-8")
        self.orig_backend = Config.MAIL_BACKEND
        Config.MAIL_BACKEND = notify_mod.config.MAIL_BACKEND = "local"
        self.client = create_app().test_client()
        self.admin = {admin_gate.HEADER: admin_gate.SECRET}

    def tearDown(self):
        notify_mod.SUBSCRIBERS_FILE = self.orig_file
        Config.MAIL_BACKEND = notify_mod.config.MAIL_BACKEND = self.orig_backend
        shutil.rmtree(self.tmp, ignore_errors=True)

    def post(self, url, payload, admin=True):
        return self.client.post(url, json=payload, headers=self.admin if admin else {})

    def test_page_hidden_without_admin(self):
        self.assertEqual(self.client.get("/admin/notify").status_code, 404)
        forged = {admin_gate.HEADER: "guess"}
        self.assertEqual(self.client.get("/admin/notify", headers=forged).status_code, 404)

    def test_page_renders_for_admin(self):
        r = self.client.get("/admin/notify", headers=self.admin)
        self.assertEqual(r.status_code, 200)
        self.assertIn(b"CyberBrief admin", r.data)
        self.assertEqual(r.headers.get("Cache-Control"), "no-store")

    def test_add_pause_resume_remove(self):
        r = self.post("/admin/notify/subscribers", {"email": "Test@Example.com", "cadence": "weekly",
                                                    "format": "briefs", "topics": ["ransomware"]})
        self.assertEqual(r.status_code, 200, r.data)
        subs = json.loads(notify_mod.SUBSCRIBERS_FILE.read_text())
        self.assertEqual(subs[0]["email"], "test@example.com")
        self.assertEqual(subs[0]["delivery"]["cadence"], "weekly")
        self.assertIn("newsletter", subs[0]["topics"])

        page = self.client.get("/admin/notify", headers=self.admin).data
        self.assertIn(b"test@example.com", page)

        self.assertEqual(self.post("/admin/notify/subscribers/status", {"email": "test@example.com", "status": "unsubscribed"}).status_code, 200)
        self.assertEqual(notify_mod.get_subscriber_by_email("test@example.com")["status"], "unsubscribed")
        self.assertEqual(self.post("/admin/notify/subscribers/status", {"email": "test@example.com", "status": "active"}).status_code, 200)
        self.assertEqual(notify_mod.get_subscriber_by_email("test@example.com")["status"], "active")

        self.assertEqual(self.post("/admin/notify/subscribers/remove", {"email": "test@example.com"}).status_code, 200)
        self.assertEqual(json.loads(notify_mod.SUBSCRIBERS_FILE.read_text()), [])

    def test_bad_input(self):
        self.assertEqual(self.post("/admin/notify/subscribers", {"email": "not-an-email"}).status_code, 400)
        self.assertEqual(self.post("/admin/notify/subscribers/status", {"email": "x@y.z", "status": "deleted"}).status_code, 400)
        self.assertEqual(self.post("/admin/notify/subscribers/status", {"email": "nobody@y.z", "status": "active"}).status_code, 404)

    def test_writes_need_admin_and_json(self):
        self.assertEqual(self.post("/admin/notify/subscribers", {"email": "a@b.co"}, admin=False).status_code, 404)
        r = self.client.post("/admin/notify/subscribers", data="email=a@b.co", headers=self.admin,
                             content_type="application/x-www-form-urlencoded")
        self.assertEqual(r.status_code, 400)
        self.assertEqual(self.post("/admin/notify/send/release", {}).status_code, 404)


class RouterGateTests(unittest.TestCase):
    """The ASGI router: strips forged headers and marks only DevCore-approved admins."""

    def run_scope(self, path, headers):
        seen = {}

        async def fake_devcore(scope, receive, send):
            seen["devcore"] = True

        router = mount(fake_devcore, start_scheduler=False)
        gate_scope = admin_gate.strip_and_mark(
            {"type": "http", "path": path, "headers": headers, "client": ("203.0.113.9", 1234)},
            FakeSecurity())
        return gate_scope, router

    def marked(self, scope):
        return any(k == admin_gate.HEADER.encode() for k, _ in scope["headers"])

    def test_forged_header_removed(self):
        scope, _ = self.run_scope("/admin/notify", [(admin_gate.HEADER.encode(), admin_gate.SECRET.encode())])
        self.assertFalse(self.marked(scope))

    def test_devcore_admin_marked(self):
        scope, _ = self.run_scope("/admin/notify", [(b"authorization", b"Bearer good-token")])
        self.assertTrue(self.marked(scope))

    def test_wrong_token_not_marked(self):
        scope, _ = self.run_scope("/admin/notify", [(b"authorization", b"Bearer nope")])
        self.assertFalse(self.marked(scope))

    def test_public_paths_never_marked(self):
        scope, _ = self.run_scope("/newsletter/preferences", [(b"authorization", b"Bearer good-token")])
        self.assertFalse(self.marked(scope))

    def test_other_paths_go_to_devcore(self):
        seen = {}

        async def fake_devcore(scope, receive, send):
            seen["hit"] = scope["path"]

        asyncio.run(mount(fake_devcore, start_scheduler=False)({"type": "http", "path": "/login", "headers": []}, None, None))
        self.assertEqual(seen.get("hit"), "/login")


if __name__ == "__main__":
    unittest.main()
