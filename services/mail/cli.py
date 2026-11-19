"""Isolated CLI entry point for the unified DevCore mail service.

Supports outbound stdin JSON dispatch (used by ticket_mail and device_keys so DevCore
routes never import credentials into agent environments), plus SMTP/IMAP diagnostics
and incoming-mail inspection. Never prints mail passwords.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Optional

DEVCORE_ROOT = Path(__file__).resolve().parent.parent.parent
if str(DEVCORE_ROOT) not in sys.path:
    sys.path.insert(0, str(DEVCORE_ROOT))

from services.mail import engine  # noqa: E402
from services.mail.config import config  # noqa: E402


def _extra_owner_emails() -> List[str]:
    sec_dir = DEVCORE_ROOT / "security"
    if str(sec_dir) not in sys.path:
        sys.path.append(str(sec_dir))
    try:
        import owner_emails
        return owner_emails.extra_owner_emails()
    except Exception:
        return []


def _send_stdin_json() -> int:
    try:
        req = json.loads(sys.stdin.read() or "{}")
        to = req.get("to") or ""
        if to == "__admin__":
            to = (
                os.environ.get("TICKET_ADMIN_EMAIL")
                or config.TICKET_ADMIN_EMAIL
                or config.MAIL_USERNAME
                or config.MAIL_DEFAULT_SENDER
            )
            want = str(req.get("only_if_matches") or "").strip().lower()
            if want:
                allowed = [str(to or "").strip().lower()] + _extra_owner_emails()
                if want not in allowed:
                    print(json.dumps({"ok": False, "message": "Address does not match.", "status": "mismatch"}))
                    return 1
                to = want
        if not to:
            print(json.dumps({"ok": False, "message": "No recipient address is configured."}))
            return 1
        ok, message, record = engine.send_email(
            to,
            req.get("subject", ""),
            req.get("html", ""),
            req.get("text") or None,
            headers=req.get("headers") or None,
        )
        print(json.dumps({"ok": bool(ok), "message": message, "status": record.get("status")}))
        return 0 if ok else 1
    except Exception as exc:
        print(json.dumps({"ok": False, "message": f"Email engine error: {exc.__class__.__name__}: {exc}"}))
        return 1


def main(argv: Optional[List[str]] = None) -> int:
    if argv is None and len(sys.argv) == 1:
        return _send_stdin_json()

    parser = argparse.ArgumentParser(description="Unified DevCore Mail Service CLI")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--send-json", action="store_true", help="Read outbound JSON payload from stdin and send.")
    group.add_argument("--check", action="store_true", help="Verify SMTP and IMAP connectivity.")
    group.add_argument("--inbox", action="store_true", help="Fetch incoming emails as JSON.")
    group.add_argument("--read", metavar="UID", help="Fetch a single incoming email by UID as JSON.")
    group.add_argument("--send-test", metavar="EMAIL", help="Send a test email to EMAIL.")
    parser.add_argument("--folder", default="INBOX", help="IMAP folder name (default: INBOX).")
    parser.add_argument("--limit", type=int, default=20, help="Maximum messages to return (default: 20).")
    parser.add_argument("--unread", action="store_true", help="Filter to unread messages only.")
    parser.add_argument("--query", default="", help="Search query string.")
    args = parser.parse_args(argv)

    if args.send_json:
        return _send_stdin_json()

    if args.check:
        status = engine.get_mailbox_status()
        smtp_ok, smtp_msg = engine.test_smtp_connection()
        imap_ok, imap_msg = engine.test_imap_connection()
        print(json.dumps({
            "status": status,
            "smtp": {"ok": smtp_ok, "message": smtp_msg},
            "imap": {"ok": imap_ok, "message": imap_msg},
        }, indent=2))
        return 0 if (smtp_ok and imap_ok) else 1

    if args.inbox:
        ok, msg, items = engine.fetch_inbox(
            folder=args.folder,
            limit=args.limit,
            search_query=args.query,
            unread_only=args.unread,
        )
        print(json.dumps({"ok": ok, "message": msg, "messages": items}, indent=2))
        return 0 if ok else 1

    if args.read:
        ok, msg, item = engine.fetch_incoming_email(uid=args.read, folder=args.folder, mark_read=False)
        print(json.dumps({"ok": ok, "message": msg, "email": item}, indent=2))
        return 0 if ok else 1

    subject = "Siraugga Mail Engine Test"
    html_content = engine.build_email_template(
        title=subject,
        body_html=f"<p>Test email generated at {datetime.now():%Y-%m-%d %H:%M:%S} via '{config.MAIL_BACKEND}'.</p>",
    )
    ok, message, record = engine.send_email(args.send_test, subject, html_content)
    print(json.dumps({"ok": bool(ok), "message": message, "status": record.get("status")}, indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
