"""Isolated configuration for the unified DevCore mail service.

Secrets are read from `.env` via `dotenv_values()` into module-local state and are
never pushed into `os.environ`, preventing DevCore agent subprocesses from inheriting
mail passwords.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    from dotenv import dotenv_values
except ImportError:  # pragma: no cover - fallback when python-dotenv is absent
    def dotenv_values(dotenv_path=None, **_kw):
        out: Dict[str, str] = {}
        try:
            with open(dotenv_path or ".env", "r", encoding="utf-8") as handle:
                for raw in handle:
                    line = raw.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    k, v = line.split("=", 1)
                    k = k.strip().removeprefix("export ").strip()
                    v = v.strip()
                    if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
                        v = v[1:-1]
                    out[k] = v
        except OSError:
            pass
        return out


ROOT_DIR = Path(__file__).resolve().parent
DEVCORE_ROOT = ROOT_DIR.parent.parent
CYBERBRIEF_ROOT = DEVCORE_ROOT / "services" / "cyberbrief"
EPROFILE_ROOT = DEVCORE_ROOT / "playground" / "e_profile"

LEGACY_ENV_CANDIDATES: Tuple[Path, ...] = (
    ROOT_DIR / ".env",
    EPROFILE_ROOT / ".env",
    CYBERBRIEF_ROOT / ".env",
)


def _read_env_file(path: Path) -> Dict[str, str]:
    if not path.is_file():
        return {}
    try:
        return {k: v for k, v in dotenv_values(path).items() if v is not None}
    except Exception:
        return {}


def _load_merged_env() -> Dict[str, str]:
    """Load mail config with primary precedence on services/mail/.env.

    If services/mail/.env does not yet have credentials, fall back to the existing
    e_profile or cyberbrief .env files so configured SMTP/IMAP accounts keep working
    without re-entering secrets.
    """
    primary = _read_env_file(ROOT_DIR / ".env")
    if primary.get("MAIL_USERNAME") and primary.get("MAIL_PASSWORD"):
        return primary

    merged: Dict[str, str] = {}
    for candidate in (CYBERBRIEF_ROOT / ".env", EPROFILE_ROOT / ".env"):
        vals = _read_env_file(candidate)
        if vals.get("MAIL_USERNAME") and vals.get("MAIL_PASSWORD"):
            merged.update(vals)
        else:
            for k, v in vals.items():
                if v and not merged.get(k):
                    merged[k] = v
    merged.update({k: v for k, v in primary.items() if v != ""})
    return merged


_FILE_ENV: Dict[str, str] = _load_merged_env()


def _env(key: str, default: Any = None) -> Any:
    if key in _FILE_ENV and _FILE_ENV[key] != "":
        return _FILE_ENV[key]
    return os.environ.get(key, default)


def _as_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in ("true", "1", "yes", "on")


def _as_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def derive_imap_host(mail_server: str) -> str:
    host = (mail_server or "").strip()
    lower = host.lower()
    if not host:
        return ""
    if "gmail" in lower or "googlemail" in lower:
        return "imap.gmail.com"
    if lower.startswith("smtp."):
        return "imap." + host[5:]
    return ""


class Config:
    ROOT_DIR = ROOT_DIR
    DEVCORE_ROOT = DEVCORE_ROOT
    TEMPLATES_DIR = ROOT_DIR / "templates"
    CACHE_DIR = ROOT_DIR / "cache"

    BASE_URL = (_env("PUBLIC_BASE_URL") or "https://mikeymike.pythonanywhere.com").rstrip("/")

    MAIL_BACKEND = str(_env("MAIL_BACKEND", "smtp") or "smtp")
    MAIL_SERVER = str(_env("MAIL_SERVER", "smtp.gmail.com") or "smtp.gmail.com")
    MAIL_PORT = _as_int(_env("MAIL_PORT", 587), 587)
    MAIL_USE_TLS = _as_bool(_env("MAIL_USE_TLS", "True"), True)
    MAIL_USERNAME = str(_env("MAIL_USERNAME", "") or "")
    MAIL_PASSWORD = str(_env("MAIL_PASSWORD", "") or "")
    MAIL_DEFAULT_SENDER = str(_env("MAIL_DEFAULT_SENDER", "notifications@eprofile.local") or "notifications@eprofile.local")
    NEWSLETTER_SENDER = str(_env("NEWSLETTER_SENDER", "CyberBrief <cyberbrief@mikeytech.dev>") or "CyberBrief <cyberbrief@mikeytech.dev>")
    TICKET_ADMIN_EMAIL = str(_env("TICKET_ADMIN_EMAIL", "") or "")

    IMAP_SERVER = str(_env("IMAP_SERVER", "") or "")
    IMAP_PORT = _as_int(_env("IMAP_PORT", 993), 993)
    IMAP_USE_SSL = _as_bool(_env("IMAP_USE_SSL", "True"), True)
    IMAP_USERNAME = str(_env("IMAP_USERNAME", "") or "")
    IMAP_PASSWORD = str(_env("IMAP_PASSWORD", "") or "")

    MAILBOX_FILE = ROOT_DIR / "cache" / "mailbox.json"
    INBOX_CACHE_FILE = ROOT_DIR / "cache" / "inbox.json"

    @classmethod
    def reload(cls) -> None:
        global _FILE_ENV
        _FILE_ENV = _load_merged_env()
        cls.BASE_URL = (_env("PUBLIC_BASE_URL") or "https://mikeymike.pythonanywhere.com").rstrip("/")
        cls.MAIL_BACKEND = str(_env("MAIL_BACKEND", "smtp") or "smtp")
        cls.MAIL_SERVER = str(_env("MAIL_SERVER", "smtp.gmail.com") or "smtp.gmail.com")
        cls.MAIL_PORT = _as_int(_env("MAIL_PORT", 587), 587)
        cls.MAIL_USE_TLS = _as_bool(_env("MAIL_USE_TLS", "True"), True)
        cls.MAIL_USERNAME = str(_env("MAIL_USERNAME", "") or "")
        cls.MAIL_PASSWORD = str(_env("MAIL_PASSWORD", "") or "")
        cls.MAIL_DEFAULT_SENDER = str(_env("MAIL_DEFAULT_SENDER", "notifications@eprofile.local") or "notifications@eprofile.local")
        cls.NEWSLETTER_SENDER = str(_env("NEWSLETTER_SENDER", "CyberBrief <cyberbrief@mikeytech.dev>") or "CyberBrief <cyberbrief@mikeytech.dev>")
        cls.TICKET_ADMIN_EMAIL = str(_env("TICKET_ADMIN_EMAIL", "") or "")
        cls.IMAP_SERVER = str(_env("IMAP_SERVER", "") or "")
        cls.IMAP_PORT = _as_int(_env("IMAP_PORT", 993), 993)
        cls.IMAP_USE_SSL = _as_bool(_env("IMAP_USE_SSL", "True"), True)
        cls.IMAP_USERNAME = str(_env("IMAP_USERNAME", "") or "")
        cls.IMAP_PASSWORD = str(_env("IMAP_PASSWORD", "") or "")

    @classmethod
    def resolve_google_credentials_path(cls) -> Optional[Path]:
        for candidate in (
            cls.ROOT_DIR / ".google_credentials.json",
            EPROFILE_ROOT / ".google_credentials.json",
            CYBERBRIEF_ROOT / ".google_credentials.json",
        ):
            if candidate.is_file():
                return candidate
        return None


config = Config()


def sync_instance_from_class(instance: Config = config) -> None:
    """Refresh instance fields from Config class attributes and vice versa."""
    for attr in (
        "BASE_URL",
        "MAIL_BACKEND",
        "MAIL_SERVER",
        "MAIL_PORT",
        "MAIL_USE_TLS",
        "MAIL_USERNAME",
        "MAIL_PASSWORD",
        "MAIL_DEFAULT_SENDER",
        "NEWSLETTER_SENDER",
        "TICKET_ADMIN_EMAIL",
        "IMAP_SERVER",
        "IMAP_PORT",
        "IMAP_USE_SSL",
        "IMAP_USERNAME",
        "IMAP_PASSWORD",
        "MAILBOX_FILE",
        "INBOX_CACHE_FILE",
    ):
        setattr(instance, attr, getattr(Config, attr))


def legacy_mailbox_candidates() -> List[Path]:
    return [
        CYBERBRIEF_ROOT / "cache" / "mailbox.json",
        EPROFILE_ROOT / "cache" / "mailbox.json",
    ]
