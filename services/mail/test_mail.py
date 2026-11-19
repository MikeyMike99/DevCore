"""Unit tests for the unified DevCore mail service (`services/mail`)."""

from __future__ import annotations

import importlib
import os
import shutil
import sys
import tempfile
import unittest
from email.message import EmailMessage
from pathlib import Path
from unittest.mock import MagicMock, patch

DEVCORE_ROOT = Path(__file__).resolve().parent.parent.parent
if str(DEVCORE_ROOT) not in sys.path:
    sys.path.insert(0, str(DEVCORE_ROOT))

mail_cfg_mod = importlib.import_module("services.mail.config")  # noqa: E402
from services.mail import engine as mail_engine  # noqa: E402
from services.mail.config import Config, config, derive_imap_host  # noqa: E402


def _make_raw_mime_email(
    sender: str = "Alice <alice@example.com>",
    to_addr: str = "devcore@example.com",
    subject: str = "=?utf-8?b?VGVzdCBTdWJqZWN0?= Alerts",
    text_body: str = "Plaintext message body",
    html_body: str = '<p onclick="evil()">Safe <script>alert(1)</script><a href="javascript:alert(2)">link</a> <a href="https://example.com">ok</a></p>',
    message_id: str = "<msg-123@example.com>",
    attachment_name: str = "report.txt",
) -> bytes:
    msg = EmailMessage()
    msg["From"] = sender
    msg["To"] = to_addr
    msg["Subject"] = subject
    msg["Date"] = "Mon, 16 Nov 2026 12:30:00 +0000"
    msg["Message-ID"] = message_id
    msg.set_content(text_body)
    msg.add_alternative(html_body, subtype="html")
    msg.add_attachment(b"hello attachment", maintype="text", subtype="plain", filename=attachment_name)
    return msg.as_bytes()


class TestUnifiedMailEngine(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp())
        self.orig_attrs = {
            attr: getattr(Config, attr)
            for attr in (
                "MAILBOX_FILE",
                "INBOX_CACHE_FILE",
                "MAIL_BACKEND",
                "MAIL_SERVER",
                "MAIL_PORT",
                "MAIL_USE_TLS",
                "MAIL_USERNAME",
                "MAIL_PASSWORD",
                "MAIL_DEFAULT_SENDER",
                "IMAP_SERVER",
                "IMAP_PORT",
                "IMAP_USE_SSL",
                "IMAP_USERNAME",
                "IMAP_PASSWORD",
            )
        }
        self.orig_file_env = dict(mail_cfg_mod._FILE_ENV)

        for target in (Config, config):
            target.MAILBOX_FILE = self.temp_dir / "mailbox.json"
            target.INBOX_CACHE_FILE = self.temp_dir / "inbox.json"
            target.MAIL_BACKEND = "local"
            target.MAIL_SERVER = "smtp.gmail.com"
            target.MAIL_PORT = 587
            target.MAIL_USE_TLS = True
            target.MAIL_USERNAME = "owner@gmail.com"
            target.MAIL_PASSWORD = "secret-app-password"
            target.MAIL_DEFAULT_SENDER = "owner@gmail.com"
            target.IMAP_SERVER = ""
            target.IMAP_PORT = 993
            target.IMAP_USE_SSL = True
            target.IMAP_USERNAME = ""
            target.IMAP_PASSWORD = ""

    def tearDown(self) -> None:
        for attr, val in self.orig_attrs.items():
            setattr(Config, attr, val)
            setattr(config, attr, val)
        mail_cfg_mod._FILE_ENV.clear()
        mail_cfg_mod._FILE_ENV.update(self.orig_file_env)
        os.environ.pop("MAIL_PASSWORD", None)
        os.environ.pop("IMAP_PASSWORD", None)
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_derive_imap_host_and_resolution(self) -> None:
        self.assertEqual(derive_imap_host("smtp.gmail.com"), "imap.gmail.com")
        self.assertEqual(derive_imap_host("smtp.customdomain.org"), "imap.customdomain.org")
        imap_cfg = mail_engine.resolve_imap_config()
        self.assertEqual(imap_cfg["server"], "imap.gmail.com")
        self.assertTrue(imap_cfg["auto_derived"])
        self.assertEqual(imap_cfg["username"], "owner@gmail.com")

    def test_sanitize_email_html_blocks_xss(self) -> None:
        dirty = '<div onload="x()"><script>steal()</script><iframe src="https://bad"></iframe><a href="javascript:bad()">Click</a><p>Clean</p></div>'
        clean = mail_engine.sanitize_email_html(dirty)
        self.assertNotIn("<script", clean.lower())
        self.assertNotIn("<iframe", clean.lower())
        self.assertNotIn("onload=", clean.lower())
        self.assertNotIn("javascript:", clean.lower())
        self.assertIn("<p>Clean</p>", clean)

    def test_local_inbox_lifecycle_and_reply(self) -> None:
        rec = mail_engine.inject_local_incoming_email(
            sender="sender@example.com",
            subject="Verify Account",
            text_content="Code: 991244",
            html_content='<p>Code: <strong>991244</strong><script>bad()</script></p>',
            message_id="<inbound-1@example.com>",
        )
        ok, _, items = mail_engine.fetch_inbox(folder="INBOX", unread_only=True)
        self.assertTrue(ok)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["uid"], rec["uid"])
        self.assertNotIn("<script", items[0]["html"].lower())

        ok_read, _, detail = mail_engine.fetch_incoming_email(rec["uid"], mark_read=False)
        self.assertTrue(ok_read)
        self.assertFalse(detail["is_read"])

        ok_flag, _ = mail_engine.set_incoming_read_status(rec["uid"], is_read=True)
        self.assertTrue(ok_flag)
        ok_unread, _, unread_items = mail_engine.fetch_inbox(unread_only=True)
        self.assertTrue(ok_unread)
        self.assertEqual(len(unread_items), 0)

        ok_rep, _, rep_rec = mail_engine.reply_to_email(
            to_address="sender@example.com",
            subject="Verify Account",
            body_text="Received, thank you.",
            in_reply_to="<inbound-1@example.com>",
            references="<inbound-1@example.com>",
            original_quote="Code: 991244",
        )
        self.assertTrue(ok_rep)
        self.assertEqual(rep_rec["subject"], "Re: Verify Account")
        self.assertEqual(rep_rec["headers"]["In-Reply-To"], "<inbound-1@example.com>")
        self.assertIn("> Code: 991244", rep_rec["text"])

        mail_engine.clear_local_inbox()
        _, _, empty_items = mail_engine.fetch_inbox()
        self.assertEqual(len(empty_items), 0)

    def test_imap_fetch_uses_body_peek_and_sanitizes_body(self) -> None:
        for target in (Config, config):
            target.MAIL_BACKEND = "smtp"
            target.MAIL_SERVER = "smtp.gmail.com"
            target.MAIL_USERNAME = "admin@gmail.com"
            target.MAIL_PASSWORD = "app-password-secret"

        raw_msg = _make_raw_mime_email()
        hdr_only = raw_msg.split(b"\r\n\r\n", 1)[0] if b"\r\n\r\n" in raw_msg else raw_msg.split(b"\n\n", 1)[0]

        mock_conn = MagicMock()
        mock_conn.select.return_value = ("OK", [b"1"])
        mock_conn.uid.side_effect = [
            ("OK", [b"42"]),
            ("OK", [(b"1 (UID 42 FLAGS () RFC822.SIZE 512 BODY[HEADER.FIELDS (FROM TO)] {100}", hdr_only + b"\r\n"), b")"]),
            ("OK", [(b"1 (UID 42 FLAGS () BODY[] {512}", raw_msg), b")"]),
            ("OK", [(b"1 (UID 42 FLAGS () RFC822.SIZE 512 BODY[] {512}", raw_msg), b")"]),
            ("OK", [b""]),
        ]

        with patch("services.mail.engine.imaplib.IMAP4_SSL", return_value=mock_conn):
            ok, _, items = mail_engine.fetch_inbox(folder="INBOX", limit=10)
            self.assertTrue(ok)
            self.assertEqual(len(items), 1)
            self.assertFalse(items[0]["is_read"])
            self.assertIn("Test Subject Alerts", items[0]["subject"])

            fetch_specs = [c.args[2] for c in mock_conn.uid.call_args_list if c.args[0] == "FETCH"]
            self.assertTrue(fetch_specs)
            self.assertTrue(all("BODY.PEEK" in spec for spec in fetch_specs))

            ok_single, _, single = mail_engine.fetch_incoming_email("42", mark_read=False)
            self.assertTrue(ok_single)
            self.assertIsNotNone(single)
            self.assertIn("Plaintext message body", single["text"])
            self.assertNotIn("<script", single["html"].lower())
            self.assertNotIn("onclick=", single["html"].lower())
            self.assertNotIn("javascript:", single["html"].lower())
            self.assertEqual(len(single["attachments"]), 1)
            self.assertEqual(single["attachments"][0]["filename"], "report.txt")

            ok_mark, _ = mail_engine.set_incoming_read_status("42", is_read=True)
            self.assertTrue(ok_mark)
            store_calls = [c.args for c in mock_conn.uid.call_args_list if c.args[0] == "STORE"]
            self.assertEqual(len(store_calls), 1)
            self.assertEqual(store_calls[0][2], "+FLAGS.SILENT")

    def test_apply_gateway_settings_isolates_secrets_from_os_environ(self) -> None:
        with patch.object(mail_engine, "update_env_file", return_value=True):
            ok, _ = mail_engine.apply_gateway_settings(
                backend="smtp",
                server_host="smtp.gmail.com",
                server_port=587,
                use_tls=True,
                username="user@gmail.com",
                password="abcd efgh ijkl mnop",
                default_sender="user@gmail.com",
                imap_server="",
                imap_port=993,
                imap_use_ssl=True,
                imap_username="",
                imap_password="",
            )
        self.assertTrue(ok)
        self.assertEqual(config.MAIL_PASSWORD, "abcdefghijklmnop")
        self.assertNotIn("MAIL_PASSWORD", os.environ)
        self.assertNotIn("IMAP_PASSWORD", os.environ)
        status = mail_engine.get_mailbox_status()
        self.assertTrue(status["has_password"])
        self.assertNotIn("abcdefghijklmnop", str(status))
        self.assertEqual(status["imap_server"], "imap.gmail.com")
        self.assertTrue(status["imap_auto_derived"])


class TestDevCoreMailboxRoutes(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp())
        self.orig_mailbox = Config.MAILBOX_FILE
        self.orig_inbox = Config.INBOX_CACHE_FILE
        self.orig_backend = Config.MAIL_BACKEND
        for target in (Config, config):
            target.MAILBOX_FILE = self.temp_dir / "mailbox.json"
            target.INBOX_CACHE_FILE = self.temp_dir / "inbox.json"
            target.MAIL_BACKEND = "local"

    def tearDown(self) -> None:
        for target in (Config, config):
            target.MAILBOX_FILE = self.orig_mailbox
            target.INBOX_CACHE_FILE = self.orig_inbox
            target.MAIL_BACKEND = self.orig_backend
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    async def test_mailbox_routes_require_tier5_and_work_for_admin(self) -> None:
        from quart import Quart
        from core.routes.system import system_bp

        test_app = Quart(__name__)
        test_app.secret_key = "test-mailbox-secret"
        test_app.register_blueprint(system_bp)
        client = test_app.test_client()

        with patch("core.routes.system._is_tier5_request", return_value=False):
            deny_page = await client.get("/admin/mailbox")
            self.assertEqual(deny_page.status_code, 403)
            deny_api = await client.get("/api/mailbox/status")
            self.assertEqual(deny_api.status_code, 403)

        mail_engine.inject_local_incoming_email(
            sender="alert@github.com",
            subject="DevCore Release",
            text_content="All checks passed.",
        )

        with patch("core.routes.system._is_tier5_request", return_value=True):
            page_res = await client.get("/admin/mailbox")
            self.assertEqual(page_res.status_code, 200)
            body = await page_res.get_data()
            self.assertIn(b"Unified Mail Hub", body)

            status_res = await client.get("/api/mailbox/status")
            self.assertEqual(status_res.status_code, 200)
            self.assertIn("no-store", status_res.headers.get("Cache-Control", ""))
            status_data = await status_res.get_json()
            self.assertTrue(status_data["success"])
            self.assertNotIn("password", status_data["status"])

            inbox_res = await client.get("/api/mailbox/inbox")
            self.assertEqual(inbox_res.status_code, 200)
            inbox_data = await inbox_res.get_json()
            self.assertTrue(inbox_data["success"])
            self.assertEqual(len(inbox_data["messages"]), 1)
            uid = inbox_data["messages"][0]["uid"]

            reply_res = await client.post("/api/mailbox/reply", json={
                "to_address": "alert@github.com",
                "subject": "DevCore Release",
                "body": "Thanks for the update.",
                "in_reply_to": f"<{uid}@local.mailbox>",
            })
            self.assertEqual(reply_res.status_code, 200)
            reply_data = await reply_res.get_json()
            self.assertTrue(reply_data["success"])
            self.assertEqual(reply_data["record"]["status"], "DELIVERED_LOCAL")


if __name__ == "__main__":
    unittest.main()
