"""Thin compatibility shim forwarding CyberBrief email calls to `services.mail`."""

from __future__ import annotations

import importlib
from typing import Any, Callable, Dict, Tuple

from . import config as cb_cfg_mod
from .config import Config
unified_cfg_mod = importlib.import_module("services.mail.config")
unified_engine = importlib.import_module("services.mail.engine")
from services.mail.cli import main

config = Config()

_IMPORT_DEFAULTS: Dict[str, Any] = {
    "BASE_URL": Config.BASE_URL,
    "MAIL_BACKEND": Config.MAIL_BACKEND,
    "MAIL_SERVER": Config.MAIL_SERVER,
    "MAIL_PORT": Config.MAIL_PORT,
    "MAIL_USE_TLS": Config.MAIL_USE_TLS,
    "MAIL_USERNAME": Config.MAIL_USERNAME,
    "MAIL_PASSWORD": Config.MAIL_PASSWORD,
    "MAIL_DEFAULT_SENDER": Config.MAIL_DEFAULT_SENDER,
    "NEWSLETTER_SENDER": Config.NEWSLETTER_SENDER,
    "MAILBOX_FILE": Config.MAILBOX_FILE,
}


def _call_unified(fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
    saved: Dict[str, Tuple[Any, Any]] = {}
    for attr, import_default in _IMPORT_DEFAULTS.items():
        saved[attr] = (
            getattr(unified_cfg_mod.Config, attr),
            getattr(unified_cfg_mod.config, attr),
        )
        cls_val = getattr(Config, attr)
        inst_val = getattr(config, attr)
        override = inst_val if inst_val != import_default else cls_val
        if override != import_default:
            setattr(unified_cfg_mod.Config, attr, override)
            setattr(unified_cfg_mod.config, attr, override)
    try:
        return fn(*args, **kwargs)
    finally:
        for attr, (old_cls, old_inst) in saved.items():
            setattr(unified_cfg_mod.Config, attr, old_cls)
            setattr(unified_cfg_mod.config, attr, old_inst)


def load_local_mailbox(limit: int = 100):
    return _call_unified(unified_engine.load_local_mailbox, limit=limit)


def get_email_by_id(email_id: str):
    return _call_unified(unified_engine.get_email_by_id, email_id)


def clear_local_mailbox() -> bool:
    return _call_unified(unified_engine.clear_local_mailbox)


def build_email_template(title: str, body_html: str, action_url=None, action_label=None) -> str:
    return _call_unified(unified_engine.build_email_template, title, body_html, action_url, action_label)


def send_email(to_address: str, subject: str, html_content: str, text_content=None, sender=None, headers=None):
    return _call_unified(
        unified_engine.send_email,
        to_address,
        subject,
        html_content,
        text_content=text_content,
        sender=sender,
        headers=headers,
    )


def test_smtp_connection():
    return _call_unified(unified_engine.test_smtp_connection)


def update_env_file(key_values: Dict[str, str]) -> bool:
    return unified_engine.update_env_file(key_values)


def apply_gateway_settings(*args: Any, **kwargs: Any):
    return _call_unified(unified_engine.apply_gateway_settings, *args, **kwargs)


def apply_google_service_json(raw_json: str):
    return _call_unified(unified_engine.apply_google_service_json, raw_json)


def build_devcore_engineering_news_section(base_url: str = "", token: str = ""):
    return _call_unified(unified_engine.build_devcore_engineering_news_section, base_url=base_url, token=token)


def build_personalized_newsletter_email(*args: Any, **kwargs: Any):
    return _call_unified(unified_engine.build_personalized_newsletter_email, *args, **kwargs)


def build_welcome_subscription_email(*args: Any, **kwargs: Any):
    return _call_unified(unified_engine.build_welcome_subscription_email, *args, **kwargs)


def build_ready_appetite_email(*args: Any, **kwargs: Any):
    return _call_unified(unified_engine.build_ready_appetite_email, *args, **kwargs)


def send_ready_appetite_email(*args: Any, **kwargs: Any):
    return _call_unified(unified_engine.send_ready_appetite_email, *args, **kwargs)


def send_welcome_email(*args: Any, **kwargs: Any):
    return _call_unified(unified_engine.send_welcome_email, *args, **kwargs)


if __name__ == "__main__":
    raise SystemExit(main())
