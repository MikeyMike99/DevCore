"""Unified SMTP + IMAP hybrid email engine for DevCore, CyberBrief, and E-Profile."""

from __future__ import annotations

import email
import email.policy
from email.header import decode_header
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import parsedate_to_datetime
import html as html_lib
import imaplib
import json
import os
import re
import smtplib
import ssl
import threading
import uuid
from datetime import datetime
import importlib
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

cfg_mod = importlib.import_module("services.mail.config")
from .config import Config, config, derive_imap_host, legacy_mailbox_candidates

_mailbox_lock = threading.Lock()
_inbox_lock = threading.Lock()

SMTP_MISSING_CREDENTIALS_ERROR = (
    "SMTP delivery failed: Missing MAIL_USERNAME or MAIL_PASSWORD in configuration. No email sent."
)
IMAP_MISSING_CREDENTIALS_ERROR = (
    "IMAP read failed: Missing IMAP/MAIL username, password, or IMAP server host in configuration."
)

_SENSITIVE_ENV_KEYS = {"MAIL_PASSWORD", "IMAP_PASSWORD"}


def _ensure_cache_dir() -> Path:
    target_dir = config.MAILBOX_FILE.parent
    target_dir.mkdir(parents=True, exist_ok=True)
    return config.MAILBOX_FILE


def _ensure_inbox_cache_dir() -> Path:
    target_dir = config.INBOX_CACHE_FILE.parent
    target_dir.mkdir(parents=True, exist_ok=True)
    return config.INBOX_CACHE_FILE


def _read_json_list(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        if isinstance(data, list):
            return [item for item in data if isinstance(item, dict)]
    except Exception:
        return []
    return []


def _seed_legacy_mailbox_if_needed(mailbox_path: Path) -> List[Dict[str, Any]]:
    """Merge legacy cyberbrief/e_profile outbound records once when migrating to unified store."""
    if mailbox_path.resolve() != (cfg_mod.ROOT_DIR / "cache" / "mailbox.json").resolve():
        return []
    seen_ids = set()
    merged: List[Dict[str, Any]] = []
    for candidate in legacy_mailbox_candidates():
        for rec in _read_json_list(candidate):
            rec_id = rec.get("id")
            if rec_id and rec_id in seen_ids:
                continue
            if rec_id:
                seen_ids.add(rec_id)
            merged.append(rec)
    if merged:
        merged = sorted(merged, key=lambda x: x.get("timestamp", ""), reverse=True)[:200]
        try:
            with open(mailbox_path, "w", encoding="utf-8") as handle:
                json.dump(merged, handle, indent=2)
        except Exception:
            pass
    return merged


def load_local_mailbox(limit: int = 100) -> List[Dict[str, Any]]:
    """Load outbound/local emails from the unified JSON cache, newest first."""
    mailbox_path = _ensure_cache_dir()
    with _mailbox_lock:
        if not mailbox_path.exists():
            seeded = _seed_legacy_mailbox_if_needed(mailbox_path)
            return seeded[:limit]
        data = _read_json_list(mailbox_path)
        return sorted(data, key=lambda x: x.get("timestamp", ""), reverse=True)[:limit]


def get_email_by_id(email_id: str) -> Optional[Dict[str, Any]]:
    """Retrieve one outbound/local email record by unique ID."""
    for item in load_local_mailbox(limit=500):
        if item.get("id") == email_id:
            return item
    return None


def clear_local_mailbox() -> bool:
    """Purge all records from the outbound/local mailbox cache."""
    mailbox_path = _ensure_cache_dir()
    with _mailbox_lock:
        try:
            with open(mailbox_path, "w", encoding="utf-8") as handle:
                json.dump([], handle, indent=2)
            return True
        except Exception:
            return False


def _append_to_local_mailbox(record: Dict[str, Any]) -> bool:
    mailbox_path = _ensure_cache_dir()
    with _mailbox_lock:
        try:
            current = _read_json_list(mailbox_path) if mailbox_path.exists() else _seed_legacy_mailbox_if_needed(mailbox_path)
            current.insert(0, record)
            current = current[:200]
            with open(mailbox_path, "w", encoding="utf-8") as handle:
                json.dump(current, handle, indent=2)
            return True
        except Exception:
            return False


def build_email_template(
    title: str,
    body_html: str,
    action_url: Optional[str] = None,
    action_label: Optional[str] = None,
) -> str:
    """Build a responsive dark-themed HTML email template."""
    safe_title = html_lib.escape(title or "")
    button_html = ""
    if action_url and action_label:
        button_html = f"""
        <div style="margin: 25px 0; text-align: center;">
            <a href="{html_lib.escape(action_url)}" style="background-color: #00f3ff; color: #000; padding: 12px 24px; text-decoration: none; font-weight: bold; border-radius: 4px; display: inline-block;">
                {html_lib.escape(action_label)}
            </a>
        </div>
        """

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{safe_title}</title>
</head>
<body style="margin: 0; padding: 0; background-color: #0a0a0b; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; color: #e0e0e0;">
    <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background-color: #0a0a0b; padding: 30px 15px;">
        <tr>
            <td align="center">
                <table role="presentation" width="100%" style="max-width: 600px; background-color: #121217; border: 1px solid rgba(0, 243, 255, 0.2); border-radius: 8px; padding: 30px;">
                    <tr>
                        <td style="border-bottom: 1px solid rgba(255, 255, 255, 0.1); padding-bottom: 15px;">
                            <span style="font-size: 20px; font-weight: bold; color: #00f3ff; letter-spacing: 1px;">SIRAUGGA MAIL</span>
                            <span style="float: right; font-size: 12px; color: #888;">Zero-Trust Hub</span>
                        </td>
                    </tr>
                    <tr>
                        <td style="padding-top: 20px;">
                            <h2 style="color: #ffffff; margin-top: 0;">{safe_title}</h2>
                            <div style="line-height: 1.6; font-size: 15px; color: #cccccc;">
                                {body_html}
                            </div>
                            {button_html}
                        </td>
                    </tr>
                    <tr>
                        <td style="border-top: 1px solid rgba(255, 255, 255, 0.1); padding-top: 15px; font-size: 12px; color: #666; text-align: center;">
                            Automated notification dispatched from Siraugga / Michael Robberts Platform.<br>
                            Access restricted under Role-Based Access Control (RBAC).
                        </td>
                    </tr>
                </table>
            </td>
        </tr>
    </table>
</body>
</html>"""


def _clean_password(raw_password: str, server_host: str) -> str:
    val = raw_password or ""
    if "gmail" in (server_host or "").lower() or "googlemail" in (server_host or "").lower():
        return val.replace(" ", "").strip()
    return val.strip()


def _smtp_credentials() -> Tuple[str, str]:
    """Return (username, password) from Config, stripping Google App Password spaces."""
    username = (config.MAIL_USERNAME or "").strip()
    password = _clean_password(config.MAIL_PASSWORD or "", config.MAIL_SERVER or "")
    return username, password


def _open_smtp_connection(username: str, password: str) -> smtplib.SMTP:
    server_host = config.MAIL_SERVER
    server_port = int(config.MAIL_PORT)
    if server_port == 465:
        server = smtplib.SMTP_SSL(server_host, server_port, timeout=10)
        server.ehlo()
    else:
        server = smtplib.SMTP(server_host, server_port, timeout=10)
        server.ehlo()
        if config.MAIL_USE_TLS or server_port == 587 or "gmail" in server_host.lower():
            server.starttls()
            server.ehlo()
    try:
        server.login(username, password)
    except Exception:
        server.close()
        raise
    return server


def _record_failure(record: Dict[str, Any], error_msg: str) -> Tuple[bool, str, Dict[str, Any]]:
    record["status"] = "FAILED"
    record["error"] = error_msg
    _append_to_local_mailbox(record)
    return False, error_msg, record


def send_email(
    to_address: str,
    subject: str,
    html_content: str,
    text_content: Optional[str] = None,
    sender: Optional[str] = None,
    headers: Optional[Dict[str, str]] = None,
) -> Tuple[bool, str, Dict[str, Any]]:
    """Dispatch an email via the configured backend ('local' or 'smtp')."""
    sender = sender or config.MAIL_DEFAULT_SENDER
    backend = (config.MAIL_BACKEND or "local").lower()
    email_id = str(uuid.uuid4())
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    if not text_content:
        text_content = re.sub(r"<[^>]+>", " ", html_content or "")
        text_content = re.sub(r"\s+", " ", text_content).strip()

    record = {
        "id": email_id,
        "timestamp": now_str,
        "to": to_address,
        "from": sender,
        "subject": subject,
        "text": text_content,
        "html": html_content,
        "headers": headers or {},
        "backend": backend,
        "status": "QUEUED",
    }

    if backend == "local":
        record["status"] = "DELIVERED_LOCAL"
        record["details"] = "Captured in unified local mailbox (services/mail/cache/mailbox.json). External delivery bypassed."
        _append_to_local_mailbox(record)
        return True, "Email captured in local mailbox (NOT sent over the internet).", record

    if backend == "smtp":
        username, password = _smtp_credentials()
        if not username or not password:
            return _record_failure(record, SMTP_MISSING_CREDENTIALS_ERROR)

        if not sender or "eprofile.local" in sender:
            sender = username
            record["from"] = sender

        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = sender
        msg["To"] = to_address
        for h_k, h_v in (headers or {}).items():
            msg[h_k] = str(h_v)
        msg.attach(MIMEText(text_content, "plain", "utf-8"))
        msg.attach(MIMEText(html_content, "html", "utf-8"))

        server_host = config.MAIL_SERVER
        server_port = int(config.MAIL_PORT)
        try:
            server = _open_smtp_connection(username, password)
            try:
                server.sendmail(sender, [to_address], msg.as_string())
            finally:
                try:
                    server.quit()
                except Exception:
                    server.close()
        except smtplib.SMTPAuthenticationError:
            return _record_failure(
                record,
                f"SMTP Authentication Failed (535): Username or App Password rejected by {server_host}. Check credentials.",
            )
        except smtplib.SMTPSenderRefused as exc:
            return _record_failure(
                record,
                f"Sender Refused: The sender address '{sender}' is rejected by SMTP server: {exc.smtp_error}",
            )
        except smtplib.SMTPRecipientsRefused:
            return _record_failure(
                record,
                f"Recipient Refused: The destination address '{to_address}' was rejected. Ensure recipient exists.",
            )
        except Exception as exc:
            return _record_failure(record, f"SMTP Transmission Failed: {exc}")

        record["status"] = "SENT_SMTP"
        record["details"] = f"Transmitted via {server_host}:{server_port}"
        _append_to_local_mailbox(record)
        return True, f"Email delivered via SMTP ({server_host}).", record

    record["status"] = "UNKNOWN_BACKEND"
    record["error"] = f"Unrecognized backend '{backend}'. Saved locally."
    _append_to_local_mailbox(record)
    return True, "Unrecognized backend; archived to local mailbox.", record


def test_smtp_connection() -> Tuple[bool, str]:
    """Verify SMTP connectivity and authentication without sending an email."""
    if (config.MAIL_BACKEND or "local").lower() == "local":
        return True, "Email Engine is configured in 'local' mock mode. Real external connections are bypassed."

    username, password = _smtp_credentials()
    if not username or not password:
        return False, "Missing MAIL_USERNAME or MAIL_PASSWORD in configuration. Cannot authenticate."

    try:
        server = _open_smtp_connection(username, password)
        server.quit()
        return True, f"Successfully connected to {config.MAIL_SERVER}:{config.MAIL_PORT} and authenticated as '{username}'."
    except smtplib.SMTPAuthenticationError:
        return (
            False,
            "Authentication Failed (535): Invalid username or Google App Password. Ensure 2-Step Verification is enabled and use a 16-character App Password.",
        )
    except smtplib.SMTPConnectError:
        return False, f"Connection Failed: Could not connect to {config.MAIL_SERVER}:{config.MAIL_PORT}. Network or port issue."
    except Exception as exc:
        return False, f"Connection failed: {exc}"


def resolve_imap_config() -> Dict[str, Any]:
    """Resolve effective IMAP settings, auto-deriving from SMTP settings when unset."""
    explicit_host = (getattr(config, "IMAP_SERVER", "") or "").strip()
    derived_host = derive_imap_host(getattr(config, "MAIL_SERVER", "") or "")
    host = explicit_host or derived_host
    port = int(getattr(config, "IMAP_PORT", 993) or 993)
    use_ssl = bool(getattr(config, "IMAP_USE_SSL", True))
    username = (getattr(config, "IMAP_USERNAME", "") or getattr(config, "MAIL_USERNAME", "") or "").strip()
    raw_pw = getattr(config, "IMAP_PASSWORD", "") or getattr(config, "MAIL_PASSWORD", "") or ""
    password = _clean_password(raw_pw, host or getattr(config, "MAIL_SERVER", ""))
    return {
        "server": host,
        "port": port,
        "use_ssl": use_ssl,
        "username": username,
        "password": password,
        "auto_derived": not bool(explicit_host) and bool(derived_host),
    }


def _imap_credentials() -> Tuple[str, str, Dict[str, Any]]:
    imap_cfg = resolve_imap_config()
    return imap_cfg["username"], imap_cfg["password"], imap_cfg


def _open_imap_connection(username: str, password: str, imap_cfg: Dict[str, Any]) -> imaplib.IMAP4:
    host = imap_cfg["server"]
    port = int(imap_cfg["port"])
    use_ssl = bool(imap_cfg["use_ssl"])
    ssl_ctx = ssl.create_default_context()

    if use_ssl or port == 993:
        conn: imaplib.IMAP4 = imaplib.IMAP4_SSL(host, port, ssl_context=ssl_ctx, timeout=15)
    else:
        conn = imaplib.IMAP4(host, port, timeout=15)
        conn.starttls(ssl_context=ssl_ctx)

    try:
        conn.login(username, password)
    except Exception:
        try:
            conn.logout()
        except Exception:
            pass
        raise
    return conn


def _quote_imap_folder(folder: str) -> str:
    clean = (folder or "INBOX").replace("\r", "").replace("\n", "").strip() or "INBOX"
    if clean.startswith('"') and clean.endswith('"'):
        return clean
    if any(ch in clean for ch in (" ", "(", ")", "{", "%", "*")):
        escaped = clean.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    return clean


def _decode_header_str(value: Any) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        value = str(value)
    parts: List[str] = []
    for chunk, charset in decode_header(value):
        if isinstance(chunk, bytes):
            enc = charset or "utf-8"
            try:
                parts.append(chunk.decode(enc, errors="replace"))
            except LookupError:
                parts.append(chunk.decode("utf-8", errors="replace"))
        else:
            parts.append(chunk)
    return "".join(parts).strip()


def _format_email_date(raw_date: str) -> str:
    if not raw_date:
        return ""
    try:
        dt = parsedate_to_datetime(raw_date)
        if dt.tzinfo is not None:
            dt = dt.astimezone()
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return raw_date.strip()


def sanitize_email_html(raw_html: str) -> str:
    """Strip executable tags, inline event handlers, and unsafe URI schemes from email HTML."""
    if not raw_html:
        return ""
    cleaned = re.sub(
        r"<\s*(script|iframe|object|embed|applet|form|base|meta)\b[^>]*>.*?<\s*/\s*\1\s*>",
        "",
        raw_html,
        flags=re.IGNORECASE | re.DOTALL,
    )
    cleaned = re.sub(
        r"<\s*(script|iframe|object|embed|applet|form|base|meta)\b[^>]*\/?>",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(
        r"""\s+on[a-z0-9_-]+\s*=\s*(?:"[^"]*"|'[^']*'|[^\s>]+)""",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(
        r"""(href|src|action|xlink:href)\s*=\s*(["'])\s*(?:javascript|vbscript|data:text/html)[^"']*\2""",
        r'\1=\2#\2',
        cleaned,
        flags=re.IGNORECASE,
    )
    return cleaned


def _extract_message_parts(msg: email.message.Message) -> Dict[str, Any]:
    text_parts: List[str] = []
    html_parts: List[str] = []
    attachments: List[Dict[str, Any]] = []

    if msg.is_multipart():
        for part in msg.walk():
            if part.is_multipart():
                continue
            disp = str(part.get_content_disposition() or "").lower()
            ctype = (part.get_content_type() or "application/octet-stream").lower()
            filename = part.get_filename()
            if filename:
                filename = _decode_header_str(filename)

            if disp == "attachment" or (filename and ctype not in ("text/plain", "text/html")):
                payload = part.get_payload(decode=True) or b""
                attachments.append({
                    "filename": filename or "attachment",
                    "content_type": ctype,
                    "size": len(payload),
                })
                continue

            payload = part.get_payload(decode=True)
            if payload is None:
                raw_content = part.get_payload()
                decoded = raw_content if isinstance(raw_content, str) else ""
            else:
                charset = part.get_content_charset() or "utf-8"
                try:
                    decoded = payload.decode(charset, errors="replace")
                except LookupError:
                    decoded = payload.decode("utf-8", errors="replace")

            if ctype == "text/plain" and not text_parts:
                text_parts.append(decoded)
            elif ctype == "text/html" and not html_parts:
                html_parts.append(decoded)
            elif ctype == "text/plain":
                text_parts.append(decoded)
            elif ctype == "text/html":
                html_parts.append(decoded)
    else:
        ctype = (msg.get_content_type() or "text/plain").lower()
        payload = msg.get_payload(decode=True)
        if payload is None:
            raw_content = msg.get_payload()
            decoded = raw_content if isinstance(raw_content, str) else ""
        else:
            charset = msg.get_content_charset() or "utf-8"
            try:
                decoded = payload.decode(charset, errors="replace")
            except LookupError:
                decoded = payload.decode("utf-8", errors="replace")
        if ctype == "text/html":
            html_parts.append(decoded)
        else:
            text_parts.append(decoded)

    plain_text = "\n\n".join(p.strip() for p in text_parts if p and p.strip()).strip()
    raw_html = "\n".join(p for p in html_parts if p).strip()
    safe_html = sanitize_email_html(raw_html)
    if not plain_text and safe_html:
        plain_text = html_lib.unescape(re.sub(r"<[^>]+>", " ", safe_html))
        plain_text = re.sub(r"\s+", " ", plain_text).strip()

    return {
        "text": plain_text,
        "html": safe_html,
        "attachments": attachments,
    }


def _parse_imap_fetch_items(raw_data: List[Any]) -> List[Dict[str, Any]]:
    """Group imaplib FETCH tuples into structured per-message dictionaries."""
    parsed: List[Dict[str, Any]] = []
    for entry in raw_data or []:
        if not isinstance(entry, tuple) or len(entry) < 2:
            continue
        meta_bytes = entry[0] if isinstance(entry[0], (bytes, bytearray)) else str(entry[0]).encode("utf-8", "replace")
        payload_bytes = entry[1] if isinstance(entry[1], (bytes, bytearray)) else b""
        meta = meta_bytes.decode("latin-1", errors="replace")

        uid_match = re.search(r"\bUID\s+(\d+)", meta, re.IGNORECASE)
        flags_match = re.search(r"\bFLAGS\s*\(([^)]*)\)", meta, re.IGNORECASE)
        size_match = re.search(r"\bRFC822\.SIZE\s+(\d+)", meta, re.IGNORECASE)

        uid = uid_match.group(1) if uid_match else ""
        flags = flags_match.group(1).split() if flags_match else []
        size = int(size_match.group(1)) if size_match else len(payload_bytes)

        parsed.append({
            "uid": uid,
            "flags": flags,
            "is_read": any(f.lower() == "\\seen" for f in flags),
            "size": size,
            "raw": bytes(payload_bytes),
        })
    return parsed


def _build_incoming_record(
    uid: str,
    folder: str,
    raw_bytes: bytes,
    is_read: bool,
    size: int = 0,
    include_body: bool = True,
) -> Dict[str, Any]:
    msg = email.message_from_bytes(raw_bytes, policy=email.policy.default)
    subject = _decode_header_str(msg.get("Subject")) or "(No Subject)"
    sender = _decode_header_str(msg.get("From")) or "(Unknown Sender)"
    to_addr = _decode_header_str(msg.get("To"))
    cc_addr = _decode_header_str(msg.get("Cc"))
    reply_to = _decode_header_str(msg.get("Reply-To"))
    raw_date = str(msg.get("Date") or "")
    formatted_date = _format_email_date(raw_date)
    message_id = str(msg.get("Message-ID") or "").strip()
    in_reply_to = str(msg.get("In-Reply-To") or "").strip()
    references = str(msg.get("References") or "").strip()

    record: Dict[str, Any] = {
        "uid": str(uid),
        "id": str(uid),
        "folder": folder,
        "direction": "inbound",
        "from": sender,
        "to": to_addr,
        "cc": cc_addr,
        "reply_to": reply_to or sender,
        "subject": subject,
        "date": raw_date,
        "timestamp": formatted_date,
        "message_id": message_id,
        "in_reply_to": in_reply_to,
        "references": references,
        "is_read": bool(is_read),
        "size": int(size or len(raw_bytes)),
        "attachments": [],
        "snippet": "",
    }
    if include_body:
        parts = _extract_message_parts(msg)
        record["text"] = parts["text"]
        record["html"] = parts["html"]
        record["attachments"] = parts["attachments"]
        snippet_src = re.sub(r"\s+", " ", parts["text"] or "").strip()
        record["snippet"] = snippet_src[:180]
    return record


def _load_local_inbox() -> List[Dict[str, Any]]:
    inbox_path = _ensure_inbox_cache_dir()
    with _inbox_lock:
        items = _read_json_list(inbox_path)
    return sorted(items, key=lambda x: x.get("timestamp", ""), reverse=True)


def _save_local_inbox(items: List[Dict[str, Any]]) -> bool:
    inbox_path = _ensure_inbox_cache_dir()
    with _inbox_lock:
        try:
            with open(inbox_path, "w", encoding="utf-8") as handle:
                json.dump(items[:200], handle, indent=2)
            return True
        except Exception:
            return False


def clear_local_inbox() -> bool:
    return _save_local_inbox([])


def inject_local_incoming_email(
    sender: str,
    subject: str,
    text_content: str,
    html_content: str = "",
    to_address: str = "",
    folder: str = "INBOX",
    is_read: bool = False,
    message_id: str = "",
    attachments: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Append a synthetic inbound message to local mock inbox storage for testing."""
    uid = f"local-{uuid.uuid4().hex[:12]}"
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    safe_html = sanitize_email_html(html_content)
    snippet = re.sub(r"\s+", " ", text_content or "").strip()[:180]
    record: Dict[str, Any] = {
        "uid": uid,
        "id": uid,
        "folder": folder or "INBOX",
        "direction": "inbound",
        "from": sender,
        "to": to_address or config.MAIL_USERNAME or "admin@eprofile.local",
        "cc": "",
        "reply_to": sender,
        "subject": subject or "(No Subject)",
        "date": now_str,
        "timestamp": now_str,
        "message_id": message_id or f"<{uid}@local.mailbox>",
        "in_reply_to": "",
        "references": "",
        "is_read": bool(is_read),
        "size": len((text_content or "").encode("utf-8")) + len((safe_html or "").encode("utf-8")),
        "text": text_content or "",
        "html": safe_html,
        "snippet": snippet,
        "attachments": attachments or [],
    }
    items = _load_local_inbox()
    items.insert(0, record)
    _save_local_inbox(items)
    return record


def test_imap_connection() -> Tuple[bool, str]:
    """Verify IMAP connectivity and credentials and report INBOX counts."""
    if (config.MAIL_BACKEND or "local").lower() == "local":
        items = _load_local_inbox()
        unread = sum(1 for m in items if not m.get("is_read"))
        return True, f"Local mock inbox active ({len(items)} message(s), {unread} unread)."

    username, password, imap_cfg = _imap_credentials()
    if not username or not password or not imap_cfg["server"]:
        return False, IMAP_MISSING_CREDENTIALS_ERROR

    try:
        conn = _open_imap_connection(username, password, imap_cfg)
        try:
            status, sel_data = conn.select("INBOX", readonly=True)
            if status != "OK":
                return False, f"Connected to {imap_cfg['server']}, but could not select INBOX."
            total = int((sel_data[0] or b"0").decode("ascii", "ignore") or 0)
            _, unseen_data = conn.search(None, "UNSEEN")
            unread = len((unseen_data[0] or b"").split()) if unseen_data and unseen_data[0] else 0
            return (
                True,
                f"IMAP connected to {imap_cfg['server']}:{imap_cfg['port']} as '{username}' ({total} total, {unread} unread).",
            )
        finally:
            try:
                conn.logout()
            except Exception:
                pass
    except imaplib.IMAP4.error as exc:
        return (
            False,
            f"IMAP Authentication or Protocol Error: {exc}. Ensure IMAP is enabled and App Password is valid.",
        )
    except Exception as exc:
        return False, f"IMAP connection failed: {exc}"


def list_imap_folders() -> Tuple[bool, str, List[Dict[str, str]]]:
    """List available folders in the configured inbox."""
    if (config.MAIL_BACKEND or "local").lower() == "local":
        return True, "Local mock folders.", [
            {"name": "INBOX", "label": "Inbox"},
            {"name": "Archive", "label": "Archive"},
        ]

    username, password, imap_cfg = _imap_credentials()
    if not username or not password or not imap_cfg["server"]:
        return False, IMAP_MISSING_CREDENTIALS_ERROR, [{"name": "INBOX", "label": "Inbox"}]

    try:
        conn = _open_imap_connection(username, password, imap_cfg)
        try:
            status, raw_list = conn.list()
            if status != "OK":
                return False, "Could not list IMAP folders.", [{"name": "INBOX", "label": "Inbox"}]
            folders: List[Dict[str, str]] = []
            seen = set()
            for item in raw_list or []:
                line = item.decode("utf-8", "replace") if isinstance(item, (bytes, bytearray)) else str(item)
                match = re.search(r'\)\s+"[^"]*"\s+(?:"([^"]+)"|(\S+))\s*$', line)
                if not match:
                    continue
                fname = (match.group(1) or match.group(2) or "").strip()
                if not fname or fname in seen or "\\Noselect" in line:
                    continue
                seen.add(fname)
                label = fname.replace("[Gmail]/", "")
                folders.append({"name": fname, "label": label})
            if not folders:
                folders.append({"name": "INBOX", "label": "Inbox"})
            return True, f"Loaded {len(folders)} folder(s).", folders
        finally:
            try:
                conn.logout()
            except Exception:
                pass
    except Exception as exc:
        return False, f"Failed to list IMAP folders: {exc}", [{"name": "INBOX", "label": "Inbox"}]


def _matches_query(item: Dict[str, Any], query: str) -> bool:
    q = (query or "").strip().lower()
    if not q:
        return True
    haystack = " ".join([
        str(item.get("from", "")),
        str(item.get("to", "")),
        str(item.get("subject", "")),
        str(item.get("snippet", "")),
        str(item.get("text", "")),
    ]).lower()
    return q in haystack


def fetch_inbox(
    folder: str = "INBOX",
    limit: int = 30,
    search_query: str = "",
    unread_only: bool = False,
) -> Tuple[bool, str, List[Dict[str, Any]]]:
    """Fetch incoming emails without marking unread messages as seen."""
    limit = max(1, min(int(limit or 30), 100))
    folder = (folder or "INBOX").strip() or "INBOX"

    if (config.MAIL_BACKEND or "local").lower() == "local":
        items = [m for m in _load_local_inbox() if (m.get("folder") or "INBOX") == folder or folder == "ALL"]
        if unread_only:
            items = [m for m in items if not m.get("is_read")]
        if search_query:
            items = [m for m in items if _matches_query(m, search_query)]
        return True, f"Loaded {len(items[:limit])} local incoming email(s).", items[:limit]

    username, password, imap_cfg = _imap_credentials()
    if not username or not password or not imap_cfg["server"]:
        return False, IMAP_MISSING_CREDENTIALS_ERROR, []

    try:
        conn = _open_imap_connection(username, password, imap_cfg)
        try:
            status, _ = conn.select(_quote_imap_folder(folder), readonly=True)
            if status != "OK":
                return False, f"Unable to open IMAP folder '{folder}'.", []

            base_criteria = ["UNSEEN"] if unread_only else ["ALL"]
            uids: List[bytes] = []
            clean_q = (search_query or "").replace("\r", " ").replace("\n", " ").strip()
            used_imap_search = False
            if clean_q and clean_q.isascii():
                escaped_q = clean_q.replace("\\", "\\\\").replace('"', '\\"')
                st, sdata = conn.uid("SEARCH", None, *base_criteria, "TEXT", f'"{escaped_q}"')
                if st == "OK" and sdata:
                    uids = (sdata[0] or b"").split()
                    used_imap_search = True
            if not used_imap_search:
                st, sdata = conn.uid("SEARCH", None, *base_criteria)
                if st == "OK" and sdata:
                    uids = (sdata[0] or b"").split()

            if not uids:
                return True, f"No messages matched in {folder}.", []

            scan_cap = limit if (not clean_q or used_imap_search) else max(limit * 3, 100)
            target_uids = list(reversed(uids))[:scan_cap]
            uid_set = b",".join(target_uids)

            hdr_query = "(FLAGS RFC822.SIZE BODY.PEEK[HEADER.FIELDS (FROM TO CC REPLY-TO SUBJECT DATE MESSAGE-ID IN-REPLY-TO REFERENCES)])"
            f_status, f_data = conn.uid("FETCH", uid_set, hdr_query)
            if f_status != "OK":
                return False, "Failed to fetch message headers from IMAP.", []

            rows = _parse_imap_fetch_items(f_data)
            records_by_uid: Dict[str, Dict[str, Any]] = {}
            small_uids: List[bytes] = []
            for row in rows:
                uid_str = row["uid"]
                if not uid_str:
                    continue
                rec = _build_incoming_record(
                    uid=uid_str,
                    folder=folder,
                    raw_bytes=row["raw"],
                    is_read=row["is_read"],
                    size=row["size"],
                    include_body=False,
                )
                records_by_uid[uid_str] = rec
                if row["size"] <= 131072 and len(small_uids) < 20:
                    small_uids.append(uid_str.encode("ascii"))

            if small_uids:
                b_status, b_data = conn.uid("FETCH", b",".join(small_uids), "(FLAGS BODY.PEEK[])")
                if b_status == "OK":
                    for brow in _parse_imap_fetch_items(b_data):
                        uid_str = brow["uid"]
                        if not uid_str:
                            continue
                        full_rec = _build_incoming_record(
                            uid=uid_str,
                            folder=folder,
                            raw_bytes=brow["raw"],
                            is_read=brow["is_read"],
                            size=brow["size"],
                            include_body=True,
                        )
                        records_by_uid[uid_str] = full_rec

            ordered: List[Dict[str, Any]] = []
            for uid_b in target_uids:
                uid_s = uid_b.decode("ascii", "ignore")
                rec = records_by_uid.get(uid_s)
                if not rec:
                    continue
                if clean_q and not used_imap_search and not _matches_query(rec, clean_q):
                    continue
                if not rec.get("snippet") and rec.get("size", 0) > 131072:
                    rec["snippet"] = "(Large message — open to read full content)"
                ordered.append(rec)
                if len(ordered) >= limit:
                    break

            return True, f"Loaded {len(ordered)} incoming message(s) from {folder}.", ordered
        finally:
            try:
                conn.logout()
            except Exception:
                pass
    except imaplib.IMAP4.error as exc:
        return False, f"IMAP error while reading {folder}: {exc}", []
    except Exception as exc:
        return False, f"Failed to read {folder}: {exc}", []


def fetch_incoming_email(
    uid: str,
    folder: str = "INBOX",
    mark_read: bool = False,
) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
    """Fetch a single incoming email by UID, including sanitized HTML, plaintext, and attachment metadata."""
    clean_uid = str(uid or "").strip()
    folder = (folder or "INBOX").strip() or "INBOX"
    if not clean_uid:
        return False, "Missing message UID.", None

    if (config.MAIL_BACKEND or "local").lower() == "local":
        items = _load_local_inbox()
        target = next((m for m in items if str(m.get("uid") or m.get("id")) == clean_uid), None)
        if not target:
            return False, "Message not found in local inbox.", None
        if mark_read and not target.get("is_read"):
            target["is_read"] = True
            _save_local_inbox(items)
        return True, "Loaded message from local inbox.", target

    if not clean_uid.isdigit():
        return False, "Invalid IMAP UID.", None

    username, password, imap_cfg = _imap_credentials()
    if not username or not password or not imap_cfg["server"]:
        return False, IMAP_MISSING_CREDENTIALS_ERROR, None

    try:
        conn = _open_imap_connection(username, password, imap_cfg)
        try:
            status, _ = conn.select(_quote_imap_folder(folder), readonly=not mark_read)
            if status != "OK":
                return False, f"Unable to open IMAP folder '{folder}'.", None

            fetch_spec = "(FLAGS RFC822.SIZE RFC822)" if mark_read else "(FLAGS RFC822.SIZE BODY.PEEK[])"
            f_status, f_data = conn.uid("FETCH", clean_uid.encode("ascii"), fetch_spec)
            if f_status != "OK":
                return False, "Failed to fetch message from IMAP.", None
            rows = _parse_imap_fetch_items(f_data)
            if not rows:
                return False, "Message not found on IMAP server.", None
            row = rows[0]
            rec = _build_incoming_record(
                uid=clean_uid,
                folder=folder,
                raw_bytes=row["raw"],
                is_read=(True if mark_read else row["is_read"]),
                size=row["size"],
                include_body=True,
            )
            return True, "Loaded message from IMAP.", rec
        finally:
            try:
                conn.logout()
            except Exception:
                pass
    except Exception as exc:
        return False, f"Failed to fetch message {clean_uid}: {exc}", None


def set_incoming_read_status(
    uid: str,
    folder: str = "INBOX",
    is_read: bool = True,
) -> Tuple[bool, str]:
    """Set or clear the \\Seen flag on an incoming message."""
    clean_uid = str(uid or "").strip()
    folder = (folder or "INBOX").strip() or "INBOX"
    if not clean_uid:
        return False, "Missing message UID."

    if (config.MAIL_BACKEND or "local").lower() == "local":
        items = _load_local_inbox()
        for item in items:
            if str(item.get("uid") or item.get("id")) == clean_uid:
                item["is_read"] = bool(is_read)
                _save_local_inbox(items)
                return True, f"Marked message as {'read' if is_read else 'unread'}."
        return False, "Message not found in local inbox."

    if not clean_uid.isdigit():
        return False, "Invalid IMAP UID."

    username, password, imap_cfg = _imap_credentials()
    if not username or not password or not imap_cfg["server"]:
        return False, IMAP_MISSING_CREDENTIALS_ERROR

    try:
        conn = _open_imap_connection(username, password, imap_cfg)
        try:
            status, _ = conn.select(_quote_imap_folder(folder), readonly=False)
            if status != "OK":
                return False, f"Unable to open IMAP folder '{folder}'."
            op = "+FLAGS.SILENT" if is_read else "-FLAGS.SILENT"
            st, _ = conn.uid("STORE", clean_uid.encode("ascii"), op, r"(\Seen)")
            if st != "OK":
                return False, "Failed to update read status on IMAP server."
            return True, f"Marked message as {'read' if is_read else 'unread'}."
        finally:
            try:
                conn.logout()
            except Exception:
                pass
    except Exception as exc:
        return False, f"Failed to update read status: {exc}"


def reply_to_email(
    to_address: str,
    subject: str,
    body_text: str,
    in_reply_to: str = "",
    references: str = "",
    original_from: str = "",
    original_date: str = "",
    original_quote: str = "",
) -> Tuple[bool, str, Dict[str, Any]]:
    """Send a threaded reply to an incoming email via the configured backend."""
    clean_to = (to_address or "").strip()
    if not clean_to:
        return False, "Recipient email address is required.", {}
    clean_body = (body_text or "").strip()
    if not clean_body:
        return False, "Reply body cannot be empty.", {}

    clean_subject = (subject or "").strip() or "(No Subject)"
    if not clean_subject.lower().startswith("re:"):
        clean_subject = f"Re: {clean_subject}"

    headers: Dict[str, str] = {}
    if in_reply_to:
        headers["In-Reply-To"] = in_reply_to.strip()
        ref_parts = [r for r in (references or "").split() if r]
        if in_reply_to.strip() not in ref_parts:
            ref_parts.append(in_reply_to.strip())
        headers["References"] = " ".join(ref_parts)
    elif references:
        headers["References"] = references.strip()

    body_html = f"<p>{html_lib.escape(clean_body).replace(chr(10), '<br>')}</p>"
    text_out = clean_body
    if original_quote:
        header_line = f"On {original_date or 'earlier'}, {original_from or clean_to} wrote:"
        quoted_lines = "\n".join(f"> {ln}" for ln in original_quote.splitlines()[:80])
        text_out += f"\n\n{header_line}\n{quoted_lines}"
        body_html += (
            f'<div style="margin-top:16px;padding-left:12px;border-left:2px solid #334155;color:#94a3b8;font-size:13px;">'
            f"<p style=\"margin:0 0 6px 0;\">{html_lib.escape(header_line)}</p>"
            f'<pre style="white-space:pre-wrap;font-family:inherit;margin:0;">{html_lib.escape(original_quote[:4000])}</pre>'
            "</div>"
        )

    html_out = build_email_template(clean_subject, body_html)
    return send_email(
        to_address=clean_to,
        subject=clean_subject,
        html_content=html_out,
        text_content=text_out,
        headers=headers or None,
    )


def update_env_file(key_values: Dict[str, str]) -> bool:
    """Update key-value pairs in services/mail/.env with owner-only permissions."""
    env_path = Config.ROOT_DIR / ".env"
    env_path.parent.mkdir(parents=True, exist_ok=True)
    existing_lines: List[str] = []
    if env_path.exists():
        try:
            with open(env_path, "r", encoding="utf-8") as handle:
                existing_lines = handle.readlines()
        except Exception:
            existing_lines = []

    updated_keys = set()
    new_lines: List[str] = []
    for line in existing_lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            k = stripped.split("=", 1)[0].strip()
            if k in key_values:
                new_lines.append(f"{k}={key_values[k]}\n")
                updated_keys.add(k)
            else:
                new_lines.append(line)
        else:
            new_lines.append(line)

    for k, v in key_values.items():
        if k not in updated_keys:
            new_lines.append(f"{k}={v}\n")

    try:
        with open(env_path, "w", encoding="utf-8") as handle:
            handle.writelines(new_lines)
        try:
            os.chmod(env_path, 0o600)
        except OSError:
            pass
        cfg_mod._FILE_ENV.update(key_values)
        return True
    except Exception:
        return False


def apply_gateway_settings(
    backend: str,
    server_host: str,
    server_port: int,
    use_tls: bool,
    username: str,
    password: str,
    default_sender: str,
    imap_server: str = "",
    imap_port: int = 993,
    imap_use_ssl: bool = True,
    imap_username: str = "",
    imap_password: str = "",
) -> Tuple[bool, str]:
    """Apply SMTP & IMAP gateway settings in memory and persist them to services/mail/.env."""
    username = (username or "").strip()
    server_host = (server_host or "").strip()
    clean_password = _clean_password(password or "", server_host)
    if not clean_password and config.MAIL_PASSWORD and backend == "smtp":
        clean_password = config.MAIL_PASSWORD

    if backend == "smtp" and username:
        if not default_sender or "eprofile.local" in default_sender:
            default_sender = username

    clean_imap_server = (imap_server or "").strip()
    clean_imap_user = (imap_username or "").strip()
    clean_imap_pw = _clean_password(imap_password or "", clean_imap_server or server_host)
    if not clean_imap_pw and config.IMAP_PASSWORD and not imap_password:
        clean_imap_pw = config.IMAP_PASSWORD

    key_values: Dict[str, str] = {
        "MAIL_BACKEND": backend,
        "MAIL_SERVER": server_host,
        "MAIL_PORT": str(server_port),
        "MAIL_USE_TLS": "True" if use_tls else "False",
        "MAIL_USERNAME": username,
        "MAIL_PASSWORD": clean_password,
        "MAIL_DEFAULT_SENDER": (default_sender or "").strip(),
        "IMAP_SERVER": clean_imap_server,
        "IMAP_PORT": str(int(imap_port or 993)),
        "IMAP_USE_SSL": "True" if imap_use_ssl else "False",
        "IMAP_USERNAME": clean_imap_user,
        "IMAP_PASSWORD": clean_imap_pw,
    }

    file_saved = update_env_file(key_values)

    for k, v in key_values.items():
        cfg_mod._FILE_ENV[k] = v
        os.environ.pop(k, None)

    for target in (config, Config):
        target.MAIL_BACKEND = backend
        target.MAIL_SERVER = server_host
        target.MAIL_PORT = int(server_port)
        target.MAIL_USE_TLS = bool(use_tls)
        target.MAIL_USERNAME = username
        target.MAIL_PASSWORD = clean_password
        target.MAIL_DEFAULT_SENDER = (default_sender or "").strip()
        target.IMAP_SERVER = clean_imap_server
        target.IMAP_PORT = int(imap_port or 993)
        target.IMAP_USE_SSL = bool(imap_use_ssl)
        target.IMAP_USERNAME = clean_imap_user
        target.IMAP_PASSWORD = clean_imap_pw

    if not file_saved:
        return False, "Failed to persist credentials to .env (applied in-memory only)."

    return True, "Email gateway (SMTP & IMAP) settings updated and active!"


def apply_google_service_json(raw_json: str) -> Tuple[bool, str, Dict[str, Any]]:
    """Validate and save a Google service account or OAuth client secret JSON."""
    try:
        parsed = json.loads(raw_json.strip())
        if not isinstance(parsed, dict):
            return False, "Invalid JSON structure: Expected a JSON object.", {}
    except Exception as exc:
        return False, f"Invalid JSON syntax: {exc}", {}

    target_path = Config.ROOT_DIR / ".google_credentials.json"
    target_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(target_path, "w", encoding="utf-8") as handle:
            json.dump(parsed, handle, indent=2)
        os.chmod(target_path, 0o600)
    except Exception as exc:
        return False, f"Failed to write Google JSON credentials: {exc}", {}

    client_email = parsed.get("client_email") or parsed.get("web", {}).get("client_id") or "Google Credentials"
    project_id = parsed.get("project_id", "Default Project")
    update_env_file({"GOOGLE_APPLICATION_CREDENTIALS": str(target_path)})

    metadata = {
        "path": str(target_path),
        "client_email": client_email,
        "project_id": project_id,
        "type": parsed.get("type", "oauth2/service_account"),
    }
    return True, f"Google credentials JSON saved successfully for project '{project_id}'.", metadata


def get_mailbox_status() -> Dict[str, Any]:
    """Return non-secret mail configuration and counts for the UI."""
    imap_cfg = resolve_imap_config()
    outbound = load_local_mailbox(limit=200)
    has_pw = bool((config.MAIL_PASSWORD or "").strip())
    has_imap_pw = bool(imap_cfg["password"])
    return {
        "backend": config.MAIL_BACKEND,
        "smtp_server": config.MAIL_SERVER,
        "smtp_port": int(config.MAIL_PORT),
        "use_tls": bool(config.MAIL_USE_TLS),
        "username": config.MAIL_USERNAME,
        "default_sender": config.MAIL_DEFAULT_SENDER,
        "has_password": has_pw,
        "imap_server": imap_cfg["server"],
        "imap_port": int(imap_cfg["port"]),
        "imap_use_ssl": bool(imap_cfg["use_ssl"]),
        "imap_username": imap_cfg["username"],
        "imap_auto_derived": bool(imap_cfg["auto_derived"]),
        "has_imap_password": has_imap_pw,
        "has_google_json": Config.resolve_google_credentials_path() is not None,
        "outbound_count": len(outbound),
    }


# ---------------------------------------------------------------------------
# Personalized Newsletter & Welcome Templates (CyberBrief)
# ---------------------------------------------------------------------------

_APPETITE_STYLE_MAP = {
    "headlines": "headlines",
    "quick_threat_wire": "headlines",
    "briefs": "briefs",
    "hybrid_brief": "briefs",
    "weekly_digest": "briefs",
    "executive_espresso": "briefs",
    "deep_dive": "deep_dive",
    "defense_playbook": "deep_dive",
    "reconstruction": "reconstruction",
    "cyber_thriller": "cyber_thriller",
    "snarky_hacker": "cyber_thriller",
}

_STYLE_META = {
    "headlines": ("⚡", "Radar Headlines", "#19e6ff", "⚡ Open on Newsfeed →"),
    "briefs": ("📋", "Executive Brief", "#b388ff", "📖 Read More on Site →"),
    "deep_dive": ("🔬", "Deep Dive", "#00ff88", "🔬 Inspect Full Deep Dive on Site →"),
    "reconstruction": ("⚔️", "Attack Reconstruction", "#ffaa00", "⚔️ Access Complete Lab Simulation on Site →"),
    "cyber_thriller": ("🍿", "Cyber Thriller", "#ff7878", "🍿 Continue Story on Site →"),
}

_ALT_STYLE = {
    "headlines": "briefs",
    "briefs": "cyber_thriller",
    "deep_dive": "cyber_thriller",
    "reconstruction": "cyber_thriller",
    "cyber_thriller": "deep_dive",
}

_ALT_HOOKS = {
    "briefs": "Short on time? The same advisory distilled into a three-sentence executive brief.",
    "deep_dive": "The headline tells you what broke. The deep dive tells you why it was breakable.",
    "cyber_thriller": "What did this look like from inside the SOC at 3 AM? Read it as a cyber thriller.",
}

_LAYOUT_LABELS = {
    "hybrid_brief": "Hybrid Brief (Headlines + Featured Dossier)",
    "quick_threat_wire": "Rapid Threat Wire (1-Min Bulletins)",
    "weekly_digest": "Weekly Threat Debrief",
    "full_story_daily": "Daily Featured Dossier",
}

LINKEDIN_URL = "https://www.linkedin.com/in/michael-robberts-40b68a180"
CREDLY_URL = "https://www.credly.com/users/michael-robberts.d08637aa"
CREDLY_BADGE_ID = "95063855-9875-40cd-9d3f-13bc9ad1448e"
INBOX_RELIEF_NOTICE = (
    "If you have not subscribed to this newsletter, please just hit that pretty button below to relieve your inbox."
)


def _import_cyberbrief_attr(module_name: str, attr_name: str, default=None):
    for mod_path in (f"services.cyberbrief.{module_name}", module_name):
        try:
            mod = __import__(mod_path, fromlist=[attr_name])
            return getattr(mod, attr_name)
        except Exception:
            continue
    return default


def _first_sentences(text: str, count: int) -> str:
    parts = [p.strip() for p in re.split(r"(?<=[.!?])\s+", (text or "").strip()) if p.strip()]
    return " ".join(parts[:count])


def _story_fields(item: Dict[str, Any]) -> Dict[str, Any]:
    fmt_date = _import_cyberbrief_attr(
        "threat_intel_engine",
        "format_display_date",
        lambda ts, d="": d or "",
    )
    return {
        "id": item.get("story_id") or "threat-advisory",
        "title": item.get("title") or "Critical Cyber Threat Intelligence",
        "date": item.get("display_date") or fmt_date(item.get("timestamp", 0), item.get("date", "")),
        "level": str(item.get("threat_level") or "HIGH"),
        "score": item.get("score", 80),
        "cves": item.get("cves") or [],
        "summary": item.get("summary") or "",
        "remediation": item.get("remediation") or "",
        "source": item.get("source") or "threat telemetry",
    }


def _cta(url: str, label: str, color: str) -> str:
    return (
        f'<a href="{url}" style="display: inline-block; background-color: {color}; color: #000000; '
        f'font-family: monospace; font-size: 12px; font-weight: bold; padding: 8px 18px; '
        f'border-radius: 4px; text-decoration: none;">{label}</a>'
    )


def _section(color: str, kicker: str, inner_html: str) -> str:
    return f"""
    <div style="background: rgba(255, 255, 255, 0.02); border: 1px solid rgba(255, 255, 255, 0.1); border-left: 4px solid {color}; border-radius: 8px; padding: 18px 20px; margin-bottom: 20px;">
        <div style="font-size: 11px; font-family: monospace; font-weight: bold; color: {color}; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 10px;">{kicker}</div>
        {inner_html}
    </div>"""


def _paragraph(text: str) -> str:
    return f'<p style="margin: 0 0 10px 0; color: #c8d2e0; font-size: 14px; line-height: 1.6;">{text}</p>'


def _headline_bulletin(f: Dict[str, Any], url: str) -> Tuple[str, str]:
    color = "#ff7878" if f["score"] >= 90 else "#ffaa00"
    cves = ", ".join(f["cves"]) or "No CVE assigned"
    block = f"""
    <div style="border-left: 3px solid {color}; padding: 8px 0 8px 12px; margin-bottom: 12px;">
        <div style="font-family: monospace; font-size: 11px; color: #888899; margin-bottom: 4px;">
            <strong style="color: {color};">{html_lib.escape(f['level'])} · {f['score']}/100</strong> · Released {html_lib.escape(f['date'])} · {html_lib.escape(cves)}
        </div>
        <div style="font-size: 15px; font-weight: 600; line-height: 1.4; margin-bottom: 8px;">
            <a href="{url}" style="color: #ffffff; text-decoration: none;">{html_lib.escape(f['title'])}</a>
        </div>
        {_cta(url, _STYLE_META['headlines'][3], '#19e6ff')}
    </div>"""
    text = f"- [{f['level']}] {f['title']}\n  Released: {f['date']} | {cves}\n  Open on Newsfeed: {url}\n"
    return block, text


def _featured_teaser(style: str, f: Dict[str, Any], url: str) -> Tuple[str, str]:
    if style == "headlines":
        return _headline_bulletin(f, url)

    lead = _first_sentences(f["summary"], 1)
    cve = f["cves"][0] if f["cves"] else "No CVE assigned yet"

    if style == "briefs":
        brief = _first_sentences(f["summary"], 2) or "A new advisory has been published for this threat."
        if f["remediation"]:
            brief += f" Recommended action: {_first_sentences(f['remediation'], 1)}"
        paragraphs = [brief]
    elif style == "deep_dive":
        paragraphs = [
            "The patch closes the door. The real question is why the door was there at all.",
            f"Key identifier: {cve}",
            lead or "A new exploitable weakness has been confirmed.",
            "The full deep dive traces the root cause, the exploit primitive, and a prioritized blue-team runbook.",
        ]
    elif style == "reconstruction":
        paragraphs = [
            "Simulated lab timeline (educational reconstruction, not a real incident log):",
            f"02:14 — The initial alert fired: {lead or f['title']}",
            f"02:31 — The team pinned the entry point to {cve}.",
            "02:47 — Then a second process spawned that nobody on the team recognized…",
        ]
    else:
        paragraphs = [
            f"The SOC floor was quiet at 03:07 — until a single line from {f['source']} scrolled across the night-shift console: “{f['title']}.”",
            "The analyst read it twice, then pulled the logs. The timestamps didn't add up. Someone had been inside for hours.",
            "Reaching for the phone to wake the incident commander, the analyst froze. On the screen, a new session had just opened — one nobody on the team had started —",
        ]

    _, _, color, cta_label = _STYLE_META[style]
    block = f"""
    <div style="font-family: monospace; font-size: 11px; color: #888899; margin-bottom: 6px;">
        <strong style="color: {color};">{html_lib.escape(f['level'])}</strong> · Released {html_lib.escape(f['date'])}
    </div>
    <h2 style="color: #ffffff; font-size: 19px; margin: 0 0 12px 0; line-height: 1.3;">{html_lib.escape(f['title'])}</h2>
    {''.join(_paragraph(html_lib.escape(p)) for p in paragraphs)}
    <div style="margin-top: 14px;">{_cta(url, cta_label, color)}</div>"""
    text = (
        f"{f['title']}\nReleased: {f['date']} | {f['level']}\n\n"
        + "\n".join(paragraphs)
        + f"\n\n{cta_label.rstrip(' →')}: {url}\n"
    )
    return block, text


def build_devcore_engineering_news_section(base_url: str = "", token: str = "") -> Tuple[str, str]:
    clean_base = (base_url or "").rstrip("/")
    encode_tok = _import_cyberbrief_attr("notify_mod", "encode_tracking_token")
    if token and callable(encode_tok):
        try:
            dev_url = f"{clean_base}/newsletter/r/{encode_tok('dev_releases', '/projects', sub_token=token)}"
            docs_url = f"{clean_base}/newsletter/r/{encode_tok('devcore_docs', '/docs', sub_token=token)}"
        except Exception:
            dev_url = f"{clean_base}/projects"
            docs_url = f"{clean_base}/docs"
    else:
        dev_url = f"{clean_base}/projects"
        docs_url = f"{clean_base}/docs"

    html = _section(
        "#00ff88",
        "🛡️ DEVCORE · E-Profile Development & Engineering News",
        '<h3 style="color: #ffffff; font-size: 15px; margin: 0 0 8px 0;">What\'s Happening in E-Profile Development & New Releases</h3>'
        + _paragraph(
            "DevCore Autonomous AI Agent and Siraugga zero-trust framework engineering developments: Zero-downtime hot-patching, accessible WebSocket streaming, POPIA-compliant offline PII scrubbing, and Super Admin JIT elevation."
        )
        + """<div style="margin: 10px 0; font-size: 12px; font-family: monospace; color: #a0aec0;">
            <div style="margin-bottom: 4px;">⚡ <strong style="color: #19e6ff;">DevCore v2.4:</strong> Zero-downtime hot-patch sequence and AST memory syncing.</div>
            <div style="margin-bottom: 4px;">🔐 <strong style="color: #00ff88;">Siraugga Security:</strong> KMS keychain, mantrap defense, and encrypted session rollover.</div>
            <div>🎧 <strong style="color: #b388ff;">Accessible Audio Suite:</strong> High-contrast NVDA coordinate audio engine and TTS feeds.</div>
        </div>"""
        + '<div style="margin-top: 12px;">'
        + _cta(dev_url, "🛠️ Explore DevCore Releases →", "#00ff88")
        + " &nbsp; "
        + _cta(docs_url, "📚 Architecture Docs & Devlogs →", "#19e6ff")
        + "</div>",
    )
    text = (
        "E-PROFILE DEVELOPMENT & RELEASES:\n"
        "DEVCORE PLATFORM & ENGINEERING INTEL:\n"
        "What's Happening in E-Profile Development & New Releases\n"
        "- DevCore v2.4: Zero-downtime hot-patch sequence and AST memory syncing\n"
        "- Siraugga Security: KMS keychain, mantrap defense, and encrypted session rollover\n"
        "- Accessible Audio Suite: High-contrast NVDA coordinate audio engine\n"
        f"DevCore Releases: {dev_url}\nArchitecture Docs: {docs_url}\n"
    )
    return html, text


def build_personalized_newsletter_email(
    subscriber: Dict[str, Any],
    manifest: Dict[str, Any],
    base_url: str = "",
) -> Tuple[str, str, str, Dict[str, str]]:
    encode_tracking_token = _import_cyberbrief_attr("notify_mod", "encode_tracking_token")

    clean_base = (base_url or "").rstrip("/")
    token = subscriber.get("token") or "token"
    delivery = subscriber.get("delivery") or {}
    content_pref = subscriber.get("content") or {}
    modules = subscriber.get("engagement_modules") or {}

    layout = delivery.get("format") or "hybrid_brief"
    style = _APPETITE_STYLE_MAP.get(content_pref.get("primary_appetite") or layout, "briefs")
    emoji, style_label, style_color, _ = _STYLE_META[style]
    layout_label = _LAYOUT_LABELS.get(layout, "Featured Dossier")

    items = manifest.get("items") or []
    featured = _story_fields(items[0] if items else {})

    pref_url = f"{clean_base}/newsletter/preferences?token={token}"
    unsub_purge_url = f"{clean_base}/newsletter/unsubscribe?token={token}&purge=1"
    visit_site_url = f"{clean_base}/newsletter"
    terms_url = f"{clean_base}/terms-and-conditions"

    def track_url(slot: str, path: str) -> str:
        if callable(encode_tracking_token):
            return f"{clean_base}/newsletter/r/{encode_tracking_token(slot, path, sub_token=token)}"
        return f"{clean_base}{path}"

    def story_url(slot: str, f: Dict[str, Any], appetite: str) -> str:
        return track_url(slot, f"/newsletter/story/{f['id']}?appetite={appetite}")

    blocks: List[str] = []
    text_parts: List[str] = []

    blocks.append(f"""
    <div style="border-bottom: 1px solid rgba(25, 230, 255, 0.25); padding-bottom: 16px; margin-bottom: 20px;">
        <div style="font-size: 11px; font-family: monospace; letter-spacing: 2px; color: #19e6ff; text-transform: uppercase;">
            Cyber Threat Intelligence Dispatch
        </div>
        <div style="font-size: 12px; color: #888899; font-family: monospace; margin-top: 4px;">
            {layout_label} · <strong style="color: {style_color};">{emoji} {style_label}</strong> · Latest release: <strong style="color: #ffffff;">{html_lib.escape(featured['date'])}</strong>
        </div>
        <div style="margin-top: 10px;">
            <a href="{pref_url}" style="font-size: 11px; font-family: monospace; color: #19e6ff; text-decoration: none; border: 1px solid #19e6ff; padding: 4px 8px; border-radius: 4px; display: inline-block;">⚙️ Switch Style</a>
        </div>
    </div>""")
    text_parts.append(f"CYBER THREAT INTELLIGENCE DISPATCH\n{layout_label} · {emoji} {style_label}\nLatest release: {featured['date']}\n")

    if layout == "quick_threat_wire":
        bulletins = [_story_fields(it) for it in items[:5]]
        subject = f"[Threat Wire] {len(bulletins)} Rapid Vulnerability Bulletins"
        rows = [_headline_bulletin(f, story_url("headline", f, "headlines")) for f in bulletins]
        blocks.append(_section("#19e6ff", "⚡ Rapid Threat Wire (1-Min Bulletins)", "".join(h for h, _ in rows)))
        text_parts.append("RAPID THREAT WIRE:\n" + "\n".join(t for _, t in rows))
    else:
        featured_html, featured_text = _featured_teaser(style, featured, story_url(style, featured, style))
        blocks.append(_section(style_color, f"Featured Dossier · {emoji} {style_label}", featured_html))
        text_parts.append(f"FEATURED DOSSIER · {style_label.upper()}\n{featured_text}")

        headline_items = []
        if layout in ("hybrid_brief", "weekly_digest"):
            headline_items = [_story_fields(it) for it in items[1:5]]
        if headline_items:
            rows = [_headline_bulletin(f, story_url("headline", f, "headlines")) for f in headline_items]
            blocks.append(_section("#19e6ff", "⚡ Advisory Headlines Brief", "".join(h for h, _ in rows)))
            text_parts.append("ADVISORY HEADLINES BRIEF:\n" + "\n".join(t for _, t in rows))

        if layout == "hybrid_brief":
            subject = f"[Cyber Intel Brief] {featured['title']}"
            if headline_items:
                subject += f" + {len(headline_items)} Advisories"
        else:
            subject = f"[{style_label}] {featured['title']}"

    if items and modules.get("alt_appetite_teaser", True):
        alt_style = _ALT_STYLE[style]
        alt_emoji, alt_label, alt_color, _ = _STYLE_META[alt_style]
        alt_url = story_url("alt_teaser", featured, alt_style)
        hook = _ALT_HOOKS[alt_style]
        blocks.append(
            _section(
                alt_color,
                f"🔀 Alternate Perspective Preview · {alt_emoji} {alt_label}",
                _paragraph(f'<strong style="color: {alt_color};">Curiosity Hook:</strong> {html_lib.escape(hook)}')
                + _cta(alt_url, f"{alt_emoji} Read as {alt_label} →", alt_color),
            )
        )
        text_parts.append(f"ALTERNATE PERSPECTIVE PREVIEW ({alt_label}):\nCuriosity Hook: {hook}\n{alt_url}\n")

    if modules.get("audio_link", True):
        audio_url = track_url("audio_cta", "/downloads")
        blocks.append(
            _section(
                "#b388ff",
                "🎧 Accessible Audio Suite",
                _paragraph("Prefer to listen? Visit the Accessible Audio Suite on the site.")
                + _cta(audio_url, "🎧 Stream Audio on Site →", "#b388ff"),
            )
        )
        text_parts.append(f"ACCESSIBLE AUDIO SUITE:\nStream Audio on Site: {audio_url}\n")

    radar = [f for f in (_story_fields(it) for it in items[:8]) if f["cves"]][:5]
    if radar and modules.get("zero_day_radar", True):
        radar_rows, radar_text = [], []
        for f in radar:
            url = story_url("zero_day_radar", f, style)
            cves = ", ".join(f["cves"])
            radar_rows.append(
                f'<li style="margin-bottom: 6px;"><a href="{url}" style="color: #19e6ff; font-family: monospace;">{html_lib.escape(cves)}</a>'
                f' <span style="color: #888899;">· {html_lib.escape(f["level"])} · {html_lib.escape(f["title"])}</span></li>'
            )
            radar_text.append(f"- {cves} [{f['level']}] {f['title']}: {url}")
        blocks.append(
            _section(
                "#ff7878",
                "🛰️ Bonus Zero-Day & KEV Radar",
                f'<ul style="margin: 0; padding-left: 18px; font-size: 13px;">{"".join(radar_rows)}</ul>',
            )
        )
        text_parts.append("BONUS ZERO-DAY & KEV RADAR:\n" + "\n".join(radar_text) + "\n")

    devcore_html, devcore_text = build_devcore_engineering_news_section(clean_base, token=token)
    blocks.append(devcore_html)
    text_parts.append(devcore_text)

    blocks.append(f"""
    <div style="text-align: center; margin: 24px 0; font-size: 12px; color: #a0aec0;">
        Curated by <strong style="color: #ffffff;">Michael Robberts</strong> ·
        <a href="{LINKEDIN_URL}" style="color: #19e6ff;">LinkedIn</a> ·
        <a href="{CREDLY_URL}" style="color: #19e6ff;">Credly Certifications</a>
        <div data-iframe-width="150" data-iframe-height="270" data-share-badge-id="{CREDLY_BADGE_ID}" data-share-badge-host="https://www.credly.com" style="margin-top: 8px;">
            <a href="https://www.credly.com/badges/{CREDLY_BADGE_ID}" style="color: #888899; font-size: 11px;">View verified Credly badge →</a>
        </div>
    </div>""")
    text_parts.append(f"Curated by Michael Robberts\nLinkedIn: {LINKEDIN_URL}\nCredly: {CREDLY_URL}\n")

    blocks.append(f"""
    <div style="margin-top: 30px; border-top: 1px solid rgba(255, 255, 255, 0.1); padding-top: 20px;">
        <div style="background: rgba(25, 230, 255, 0.04); border: 1px solid rgba(25, 230, 255, 0.15); border-radius: 6px; padding: 12px 14px; margin-bottom: 18px; font-size: 11px; color: #a0aec0; line-height: 1.5;">
            <strong style="color: #19e6ff;">Subscription Activity Requirement:</strong> We require subscribers to visit the site from time to time to keep their subscription active. If you do not visit the website from the emails you receive, your subscription record will be automatically purged.
            <div style="margin-top: 6px;">
                <a href="{visit_site_url}" style="color: #19e6ff; text-decoration: underline; font-weight: bold;">Visit Website to Keep Active →</a>
            </div>
        </div>
        <p style="margin: 0 0 12px 0; font-size: 12px; color: #cbd5e1; text-align: center;">{INBOX_RELIEF_NOTICE}</p>
        <table role="presentation" cellspacing="0" cellpadding="0" border="0" align="center" style="margin: 0 auto 16px auto;">
            <tr>
                <td align="center" bgcolor="#d32f2f" style="border-radius: 6px; background-color: #d32f2f; border: 1px solid #ff4d4d;">
                    <a href="{unsub_purge_url}" target="_blank" role="button" aria-label="1-Click Unsubscribe & Purge Data" style="display: inline-block; padding: 10px 24px; font-family: monospace, sans-serif; font-size: 12px; font-weight: bold; color: #ffffff; text-decoration: none; border-radius: 6px;">
                        🚫 1-Click Unsubscribe & Purge Data
                    </a>
                </td>
            </tr>
        </table>
        <div style="font-size: 11px; color: #666677; text-align: center; line-height: 1.6;">
            <p style="margin: 0 0 6px 0;">
                <a href="{pref_url}" style="color: #19e6ff; text-decoration: underline; margin-right: 10px;">⚙️ Manage Preferences</a>
                ·
                <a href="{terms_url}" style="color: #888899; text-decoration: underline; margin: 0 10px;">📄 Terms & Conditions</a>
                ·
                <a href="{unsub_purge_url}" style="color: #ff7878; text-decoration: underline; margin-left: 10px;">🚫 One-Click Purge</a>
            </p>
            <div style="font-size: 10px; color: #555566; font-family: monospace;">
                RFC 8058 Compliant · Zero-Database Local Storage Architecture
            </div>
        </div>
    </div>""")
    text_parts.append(
        "\n" + "=" * 60
        + "\nSUBSCRIPTION ACTIVITY REQUIREMENT:\n"
        + "We require subscribers to visit the site from time to time to keep their subscription active.\n"
        + f"Visit Website to Confirm Active Status: {visit_site_url}\n"
        + f"\n{INBOX_RELIEF_NOTICE}\n"
        + f"1-Click Unsubscribe & Purge Data: {unsub_purge_url}\n"
        + f"Manage Preferences: {pref_url}\n"
        + f"Terms and Conditions: {terms_url}\n"
    )

    master_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{html_lib.escape(subject)}</title>
</head>
<body style="margin: 0; padding: 0; background-color: #0a0a0b; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; color: #e0e0e0;">
    <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background-color: #0a0a0b; padding: 25px 12px;">
        <tr>
            <td align="center">
                <table role="presentation" width="100%" style="max-width: 640px; background-color: #10141d; border: 1px solid rgba(25, 230, 255, 0.25); border-radius: 8px; padding: 24px; text-align: left;">
                    <tr>
                        <td>
                            {''.join(blocks)}
                        </td>
                    </tr>
                </table>
            </td>
        </tr>
    </table>
</body>
</html>"""

    headers = {
        "List-Unsubscribe": f"<{clean_base}/newsletter/unsubscribe?token={token}>",
        "List-Unsubscribe-Post": "List-Unsubscribe=One-Click",
    }
    return subject, master_html, "\n".join(text_parts), headers


def build_welcome_subscription_email(
    subscriber: Dict[str, Any],
    base_url: str = "",
) -> Tuple[str, str, str, Dict[str, str]]:
    clean_base = (base_url or "").rstrip("/")
    if not clean_base:
        clean_base = getattr(config, "BASE_URL", "https://mikeymike.pythonanywhere.com").rstrip("/")

    addr = subscriber.get("email", "")
    token = subscriber.get("token") or "token"
    delivery = subscriber.get("delivery") or {}
    content_pref = subscriber.get("content") or {}

    chosen_format = delivery.get("format", "hybrid_brief")
    chosen_appetite = content_pref.get("primary_appetite", "cyber_thriller")
    format_label = chosen_format.replace("_", " ").title()
    appetite_label = chosen_appetite.replace("_", " ").title()

    unsub_url = f"{clean_base}/newsletter/unsubscribe?token={token}&purge=1"
    pref_url = f"{clean_base}/newsletter/preferences?token={token}"
    portal_url = f"{clean_base}/newsletter"
    terms_url = f"{clean_base}/terms"

    subject = "Welcome to Cyber Threat Intelligence – Did you subscribe?"

    recent_topics_html: List[str] = []
    recent_topics_text: List[str] = []
    load_manifest = _import_cyberbrief_attr("newsletter_mod", "load_active_manifest")
    if callable(load_manifest):
        try:
            manifest = load_manifest()
            for it in (manifest.get("items") or [])[:3]:
                it_title = html_lib.escape(it.get("title", "Threat Advisory"))
                it_id = it.get("story_id", "")
                it_lvl = html_lib.escape(str(it.get("threat_level", "HIGH")))
                it_score = it.get("score", 75)
                it_cves = ", ".join(it.get("cves", [])) or "Active Exploit Vector"
                raw_summary = it.get("summary", "")
                it_summary = html_lib.escape(raw_summary[:220]) + ("..." if len(raw_summary) > 220 else "")
                it_url = f"{clean_base}/newsletter/story/{it_id}"
                badge_color = "#ff7878" if it_score >= 90 else "#ffaa00"
                recent_topics_html.append(f"""
                <div style="background: rgba(255, 255, 255, 0.03); border-left: 3px solid {badge_color}; border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 6px; padding: 12px 14px; margin-bottom: 12px;">
                    <div style="font-family: monospace; font-size: 11px; margin-bottom: 4px;">
                        <span style="color: {badge_color}; font-weight: bold;">[{it_lvl}]</span>
                        <span style="color: #888899; margin-left: 6px;">{it_cves}</span>
                    </div>
                    <div style="font-size: 14px; font-weight: 600; margin-bottom: 4px;">
                        <a href="{it_url}" style="color: #19e6ff; text-decoration: none;">{it_title} →</a>
                    </div>
                    <div style="font-size: 12px; color: #a0aec0; line-height: 1.4; margin-bottom: 8px;">{it_summary}</div>
                    <div style="text-align: right;">
                        <a href="{it_url}" style="font-size: 11px; font-family: monospace; color: #00ff88; text-decoration: none;">🛡️ Read Dossier & Interactive Playbook →</a>
                    </div>
                </div>""")
                recent_topics_text.append(
                    f"- [{it_lvl}] {it.get('title')}\n  CVEs: {it_cves}\n  Summary: {raw_summary[:200]}\n  Dossier Link: {it_url}"
                )
        except Exception:
            pass

    topics_markup = (
        "".join(recent_topics_html)
        if recent_topics_html
        else '<p style="color: #888899; font-size: 13px;">Curating latest vulnerability telemetry...</p>'
    )
    devcore_html, devcore_text = build_devcore_engineering_news_section(clean_base, token=token)

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{html_lib.escape(subject)}</title>
</head>
<body style="margin: 0; padding: 0; background-color: #0a0a0b; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; color: #e0e0e0;">
    <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background-color: #0a0a0b; padding: 25px 12px;">
        <tr>
            <td align="center">
                <table role="presentation" width="100%" style="max-width: 640px; background-color: #10141d; border: 1px solid rgba(25, 230, 255, 0.25); border-radius: 8px; padding: 24px; text-align: left;">
                    <tr>
                        <td style="border-bottom: 1px solid rgba(255, 255, 255, 0.1); padding-bottom: 16px;">
                            <span style="font-size: 18px; font-weight: bold; color: #00f3ff; letter-spacing: 1px;">MICHAEL ROBBERTS</span>
                            <span style="float: right; font-size: 12px; color: #888899; font-family: monospace;">Zero-Trust Intel</span>
                        </td>
                    </tr>
                    <tr>
                        <td style="padding-top: 24px;">
                            <div style="font-size: 11px; font-family: monospace; letter-spacing: 2px; color: #19e6ff; text-transform: uppercase; margin-bottom: 6px;">Subscription Notification</div>
                            <h1 style="color: #ffffff; font-size: 22px; margin: 0 0 16px 0; font-weight: 700;">Did you subscribe to Cyber Threat Intelligence?</h1>
                            <p style="font-size: 14px; line-height: 1.6; color: #c8d2e0; margin: 0 0 16px 0;">
                                Hello, we received a subscription request for <strong style="color: #ffffff;">{html_lib.escape(addr)}</strong> to receive curated, multi-cadence cyber intelligence feeds and zero-day threat dispatches from the Michael Robberts E-Profile platform.
                            </p>
                            <div style="background: rgba(25, 230, 255, 0.05); border: 1px solid rgba(25, 230, 255, 0.2); border-radius: 6px; padding: 14px 16px; margin-bottom: 20px;">
                                <div style="font-size: 11px; font-family: monospace; color: #19e6ff; text-transform: uppercase; font-weight: bold; margin-bottom: 6px;">Selected Preferences:</div>
                                <div style="font-size: 13px; color: #e2e8f0; font-family: monospace;">
                                    Delivery Format: <strong style="color: #ffffff;">{html_lib.escape(format_label)}</strong><br>
                                    Primary Reading Appetite: <strong style="color: #19e6ff;">{html_lib.escape(appetite_label)}</strong>
                                </div>
                            </div>
                            <div style="margin-bottom: 22px;">
                                <div style="font-size: 11px; font-family: monospace; font-weight: bold; color: #19e6ff; text-transform: uppercase; letter-spacing: 1.5px; margin-bottom: 10px;">⚡ RECENT THREAT TELEMETRY (ACTIVE AT TIME OF SUBSCRIPTION)</div>
                                {topics_markup}
                            </div>
                            <div style="margin-bottom: 22px;">{devcore_html}</div>
                            <div style="margin: 20px 0; text-align: center;">
                                <a href="{pref_url}" style="background-color: #00f3ff; color: #000000; font-family: monospace; font-size: 13px; font-weight: bold; padding: 10px 22px; border-radius: 4px; text-decoration: none; display: inline-block;">⚙️ Manage Your Preferences</a>
                            </div>
                            <div style="margin: 24px 0; padding: 20px 16px; background-color: #1a0f12; border: 1px solid #772228; border-radius: 8px; text-align: center;">
                                <p style="margin: 0 0 14px 0; font-size: 13px; color: #ffffff; font-weight: 600; line-height: 1.4;">{INBOX_RELIEF_NOTICE}</p>
                                <table role="presentation" cellspacing="0" cellpadding="0" border="0" align="center" style="margin: 0 auto;">
                                    <tr>
                                        <td align="center" bgcolor="#d32f2f" style="border-radius: 6px; background-color: #d32f2f; border: 1px solid #ff4d4d;">
                                            <a href="{unsub_url}" target="_blank" role="button" aria-label="1-Click Unsubscribe & Purge Data" style="display: inline-block; padding: 12px 28px; font-family: monospace, sans-serif; font-size: 13px; font-weight: bold; color: #ffffff; text-decoration: none; border-radius: 6px;">🚫 1-Click Unsubscribe & Purge Data</a>
                                        </td>
                                    </tr>
                                </table>
                            </div>
                            <div style="margin: 24px 0 16px 0; padding: 14px 16px; background: rgba(255, 170, 0, 0.07); border: 1px solid rgba(255, 170, 0, 0.28); border-radius: 6px;">
                                <div style="font-size: 11px; font-family: monospace; font-weight: bold; color: #ffaa00; text-transform: uppercase; margin-bottom: 4px;">⏱️ Subscription Activity Requirement</div>
                                <p style="margin: 0 0 8px 0; font-size: 12px; color: #d0d8e8; line-height: 1.45;">
                                    To ensure our local registry remains clean and intentional, we require subscribers to visit the site from time to time to keep their subscription active. If you do not visit the website from the emails you receive, we will consider that you did not subscribe to the service, and your records will be automatically purged.
                                </p>
                                <div style="text-align: right;">
                                    <a href="{portal_url}" style="color: #ffaa00; font-family: monospace; font-size: 12px; font-weight: bold; text-decoration: underline;">🌐 Visit Live Threat Feed →</a>
                                </div>
                            </div>
                            <div style="border-top: 1px solid rgba(255, 255, 255, 0.1); padding-top: 16px; font-size: 11px; color: #64748b; text-align: center; line-height: 1.6;">
                                <p style="margin: 0 0 6px 0;">Michael Robberts E-Profile Platform · Automated Notification Dispatched via Secure SMTP</p>
                                <p style="margin: 0 0 8px 0;">
                                    <a href="{pref_url}" style="color: #19e6ff; text-decoration: underline; margin-right: 10px;">⚙️ Manage Preferences</a> ·
                                    <a href="{terms_url}" style="color: #94a3b8; text-decoration: underline; margin: 0 10px;">📄 Terms & Conditions</a> ·
                                    <a href="{unsub_url}" style="color: #ff7878; text-decoration: underline; margin-left: 10px;">🚫 One-Click Purge</a>
                                </p>
                            </div>
                        </td>
                    </tr>
                </table>
            </td>
        </tr>
    </table>
</body>
</html>"""

    plain_text_topics = ("\n".join(recent_topics_text)) if recent_topics_text else "Curating latest vulnerability telemetry..."
    plain_text = (
        "============================================================\n"
        "CYBER THREAT INTELLIGENCE · SUBSCRIPTION CONFIRMATION\n"
        "============================================================\n\n"
        f"Hello,\n\nWe received a subscription request for {addr} to receive Cyber Threat Intelligence feeds and advisories.\n\n"
        f"RECENT THREAT TELEMETRY:\n{plain_text_topics}\n\n"
        f"DEVCORE PLATFORM & ENGINEERING INTEL:\n{devcore_text}\n\n"
        f"Selected Format: {format_label} | Appetite: {appetite_label}\n"
        f"Manage Preferences: {pref_url}\n"
        f"1-Click Unsubscribe & Purge Data: {unsub_url}\n"
        f"Visit Live Threat Feed: {portal_url}\n"
        f"Terms and Conditions: {terms_url}\n"
    )
    headers = {
        "List-Unsubscribe": f"<{clean_base}/newsletter/unsubscribe?token={token}>",
        "List-Unsubscribe-Post": "List-Unsubscribe=One-Click",
    }
    return subject, html_content, plain_text, headers


def build_ready_appetite_email(
    to_address: str,
    story_id: str,
    appetite: str,
    story_data: Dict[str, Any],
    token: str = "",
    base_url: str = "",
) -> Tuple[str, str, str, Dict[str, str]]:
    clean_base = (base_url or "").rstrip("/") or getattr(config, "BASE_URL", "https://mikeymike.pythonanywhere.com").rstrip("/")
    import markdown

    appetite_cfg = _import_cyberbrief_attr("story_agent_dispatcher", "APPETITE_CONFIG", {}) or {}
    app_cfg = appetite_cfg.get(appetite, {})
    app_title = app_cfg.get("title", appetite.replace("_", " ").title())
    app_color = app_cfg.get("badge_color", "#19e6ff")

    title = story_data.get("story_id", story_id).replace("-", " ").title()
    if isinstance(story_data.get("item_metadata"), dict):
        title = story_data["item_metadata"].get("title", title)
    elif story_data.get("title"):
        title = story_data["title"]

    md_content = story_data.get("markdown", "")
    rendered_html = markdown.markdown(md_content, extensions=["tables", "fenced_code"])
    story_url = f"{clean_base}/newsletter/story/{story_id}?appetite={appetite}"
    pref_url = f"{clean_base}/newsletter/preferences?token={token}" if token else f"{clean_base}/newsletter/preferences"
    unsub_url = f"{clean_base}/newsletter/unsubscribe?token={token}&purge=1" if token else f"{clean_base}/newsletter/unsubscribe"
    subject = f"[Ready] {title} · {app_title}"
    devcore_html, devcore_text = build_devcore_engineering_news_section(clean_base, token=token)

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>{html_lib.escape(subject)}</title></head>
<body style="margin: 0; padding: 0; background-color: #0a0a0b; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; color: #e0e0e0;">
    <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background-color: #0a0a0b; padding: 25px 12px;">
        <tr><td align="center">
            <table role="presentation" width="100%" style="max-width: 640px; background-color: #10141d; border: 1px solid rgba(25, 230, 255, 0.25); border-radius: 8px; padding: 24px; text-align: left;">
                <tr><td style="border-bottom: 1px solid rgba(255, 255, 255, 0.1); padding-bottom: 16px;">
                    <span style="font-size: 18px; font-weight: bold; color: #00f3ff; letter-spacing: 1px;">MICHAEL ROBBERTS</span>
                    <span style="float: right; font-size: 12px; color: {app_color}; font-family: monospace;">⚡ SYNTHESIS COMPLETE</span>
                </td></tr>
                <tr><td style="padding-top: 20px;">
                    <div style="font-size: 11px; font-family: monospace; letter-spacing: 2px; color: {app_color}; text-transform: uppercase; margin-bottom: 6px;">{html_lib.escape(app_title)}</div>
                    <h1 style="color: #ffffff; font-size: 20px; margin: 0 0 14px 0; font-weight: 700;">{html_lib.escape(title)}</h1>
                    <p style="font-size: 13px; color: #a0aec0; line-height: 1.5; margin: 0 0 18px 0;">Your requested analysis is now ready:</p>
                    <div style="background: #141824; border: 1px solid rgba(255, 255, 255, 0.1); border-radius: 6px; padding: 18px; margin-bottom: 20px; color: #d0d8e8; line-height: 1.6; font-size: 13px;">{rendered_html}</div>
                    <div style="text-align: center; margin: 20px 0;">
                        <a href="{story_url}" style="background-color: {app_color}; color: #000000; font-family: monospace; font-size: 13px; font-weight: bold; padding: 10px 22px; border-radius: 4px; text-decoration: none; display: inline-block;">🛡️ Open Interactive Dossier on Web Portal →</a>
                    </div>
                    <div style="margin-top: 24px; margin-bottom: 20px;">{devcore_html}</div>
                    <div style="border-top: 1px solid rgba(255, 255, 255, 0.1); padding-top: 16px; font-size: 11px; color: #64748b; text-align: center;">
                        <a href="{pref_url}" style="color: #19e6ff;">Preferences</a> · <a href="{unsub_url}" style="color: #ff7878;">Unsubscribe & Purge</a>
                    </div>
                </td></tr>
            </table>
        </td></tr>
    </table>
</body>
</html>"""

    plain_text = (
        f"{subject}\n{'=' * 60}\n{title}\nAppetite: {app_title}\n{'=' * 60}\n\n"
        f"{md_content}\n\nOpen Interactive Dossier: {story_url}\n\n{devcore_text}\n"
        f"Manage Preferences: {pref_url}\nUnsubscribe & Purge: {unsub_url}\n"
    )
    headers = {
        "List-Unsubscribe": f"<{unsub_url}>",
        "List-Unsubscribe-Post": "List-Unsubscribe=One-Click",
    }
    return subject, html_content, plain_text, headers


def send_ready_appetite_email(
    to_address: str,
    story_id: str,
    appetite: str,
    story_data: Dict[str, Any],
    token: str = "",
    base_url: str = "",
) -> Tuple[bool, str, Dict[str, Any]]:
    subject, html_content, text_content, headers = build_ready_appetite_email(
        to_address=to_address,
        story_id=story_id,
        appetite=appetite,
        story_data=story_data,
        token=token,
        base_url=base_url,
    )
    return send_email(
        to_address=to_address,
        subject=subject,
        html_content=html_content,
        text_content=text_content,
        sender=config.NEWSLETTER_SENDER,
        headers=headers,
    )


def send_welcome_email(
    subscriber: Dict[str, Any],
    base_url: str = "",
) -> Tuple[bool, str, Dict[str, Any]]:
    subject, html_content, text_content, headers = build_welcome_subscription_email(subscriber, base_url=base_url)
    return send_email(
        to_address=subscriber["email"],
        subject=subject,
        html_content=html_content,
        text_content=text_content,
        sender=config.NEWSLETTER_SENDER,
        headers=headers,
    )
