import importlib
from .mixins import comms_mixin as _cm_mod
from .mixins import execution_mixin as _em_mod
from .mixins import transcript_mixin as _tm_mod

from .mixins.comms_mixin import CommsMixin, _TASK_OWNER_CTX, _owners_match, _normalize_base_owner
from .mixins.execution_mixin import ExecutionMixin
from .mixins.transcript_mixin import TranscriptMixin
import logging
import asyncio
import json
import os
import time
import sys
import shutil
import random
import re
import traceback


def _find_existing_agent_mgr():
    for mod_name in ("__main__", "core.server"):
        mod = sys.modules.get(mod_name)
        if mod is not None:
            mgr = getattr(mod, "agent_mgr", None)
            if mgr is not None:
                return mgr
            app_obj = getattr(mod, "app", None)
            if app_obj is not None and getattr(app_obj, "agent_mgr", None) is not None:
                return app_obj.agent_mgr
    return None


def _normalize_slot_key(owner: str) -> str:
    if not owner:
        return "Michael (Admin)"
    raw = str(owner).strip()
    if "::" in raw:
        base, cid = raw.split("::", 1)
        norm_base = _normalize_base_owner(base) or base
        return f"{norm_base}::{cid}" if cid else norm_base
    return _normalize_base_owner(raw) or raw


def _make_slot(owner_key: str) -> dict:
    return {
        "active_task": None,
        "active_proc": None,
        "current_prompt": None,
        "current_model": "Gemini 3.8 Flash (Low)",
        "start_time": None,
        "output_buffer": [],
        "actions": [],
        "last_completed_task": None,
        "active_task_owner": owner_key,
        "current_conversation_id": None,
        "queued_prompts": [],
        "_steering_interrupt": False,
        "_steer_lock": asyncio.Lock(),
        "last_user": None,
        "last_admin_override": False,
        "_last_deep_insight": "",
        "_last_thought_step": None,
        "_pending_rollover": None,
        "last_cache_read_tokens": 0,
        "last_total_tokens": 0,
    }


_SLOT_KEYS = (
    "active_task",
    "active_proc",
    "current_prompt",
    "current_model",
    "start_time",
    "output_buffer",
    "actions",
    "last_completed_task",
    "active_task_owner",
    "current_conversation_id",
    "queued_prompts",
    "_steering_interrupt",
    "_steer_lock",
    "last_user",
    "last_admin_override",
    "_last_deep_insight",
    "_last_thought_step",
    "_pending_rollover",
    "last_cache_read_tokens",
    "last_total_tokens",
)


class _SlotAttr:
    """Data descriptor routing task attributes to the calling user's isolated runtime slot."""

    def __init__(self, name: str):
        self.name = name

    def __get__(self, instance, owner=None):
        if instance is None:
            return self
        slot = instance._get_slot()
        return slot.get(self.name)

    def __set__(self, instance, value):
        slot = instance._get_slot()
        slot[self.name] = value


def _migrate_legacy_dict(inst):
    d = inst.__dict__
    if "_user_slots" not in d or not isinstance(d["_user_slots"], dict):
        d["_user_slots"] = {}
        legacy_owner = _normalize_slot_key(d.get("active_task_owner") or "Michael (Admin)")
        d["_default_owner"] = legacy_owner
        slot = _make_slot(legacy_owner)
        for k in _SLOT_KEYS:
            if k in d and d[k] is not None:
                slot[k] = d[k]
        d["_user_slots"][legacy_owner] = slot


class AgentTaskManager(CommsMixin, ExecutionMixin, TranscriptMixin):
    """
    Manages Antigravity background tasks independently per user/connection slot.
    Uses an ACK-backed message queue and ContextVar-isolated task slots so multiple
    users and connections can run concurrent `agy` sessions without cross-talk.
    """

    active_task = _SlotAttr("active_task")
    active_proc = _SlotAttr("active_proc")
    current_prompt = _SlotAttr("current_prompt")
    current_model = _SlotAttr("current_model")
    start_time = _SlotAttr("start_time")
    output_buffer = _SlotAttr("output_buffer")
    actions = _SlotAttr("actions")
    last_completed_task = _SlotAttr("last_completed_task")
    active_task_owner = _SlotAttr("active_task_owner")
    current_conversation_id = _SlotAttr("current_conversation_id")
    queued_prompts = _SlotAttr("queued_prompts")
    _steering_interrupt = _SlotAttr("_steering_interrupt")
    _steer_lock = _SlotAttr("_steer_lock")
    last_user = _SlotAttr("last_user")
    last_admin_override = _SlotAttr("last_admin_override")
    _last_deep_insight = _SlotAttr("_last_deep_insight")
    _last_thought_step = _SlotAttr("_last_thought_step")
    _pending_rollover = _SlotAttr("_pending_rollover")
    last_cache_read_tokens = _SlotAttr("last_cache_read_tokens")
    last_total_tokens = _SlotAttr("last_total_tokens")

    def __new__(cls, *args, **kwargs):
        existing = _find_existing_agent_mgr()
        if existing is not None:
            _migrate_legacy_dict(existing)
            existing.__class__ = cls
            return existing
        return super().__new__(cls)

    def _get_slot(self, owner: str = None) -> dict:
        _migrate_legacy_dict(self)
        slots = self.__dict__["_user_slots"]
        raw_key = owner or _TASK_OWNER_CTX.get() or self.__dict__.get("_default_owner") or "Michael (Admin)"
        if "::" in str(raw_key):
            b_part, c_part = str(raw_key).split("::", 1)
            if b_part.strip().lower() in ("admin", "michael (admin)", "michael"):
                b_part = "Michael (Admin)"
            key = f"{b_part.strip()}::{c_part.strip()}"
        else:
            b_part = str(raw_key).strip()
            key = "Michael (Admin)" if b_part.lower() in ("admin", "michael (admin)", "michael") else b_part
        if key not in slots or slots[key].get("active_task_owner") != key:
            slots[key] = _make_slot(key)
        return slots[key]

    def __init__(self, project_manager=None):
        _migrate_legacy_dict(self)
        if getattr(self, "_initialized", False):
            if project_manager is not None:
                self.project_manager = project_manager
            return

        self._initialized = True
        self.project_manager = project_manager
        self.connected_clients: dict = {}
        self.current_seq: int = 0
        self.message_queue: list = []
        self.max_queue_size: int = 1000
        self._lock = asyncio.Lock()
        self._local_sec = None
        self.rate_limits = {}

    @property
    def active_task_id(self):
        return self.active_task

    @active_task_id.setter
    def active_task_id(self, val):
        self.active_task = val

    def reinit(self, project_manager=None):
        """Re-initializes state while preserving client connections and active user slots."""
        _migrate_legacy_dict(self)
        if project_manager:
            self.project_manager = project_manager

    def is_running(self, owner: str = None) -> bool:
        slot = self._get_slot(owner)
        proc = slot.get("active_proc")
        if proc is not None and proc.returncode is None:
            return True
        check_owner = owner or _TASK_OWNER_CTX.get() or "Michael (Admin)"
        slots = self.__dict__.get("_user_slots", {})
        for k, s in list(slots.items()):
            if _owners_match(check_owner, k):
                p = s.get("active_proc")
                if p is not None and p.returncode is None:
                    return True
        return False

    def get_user_conversation_id(self, owner: str = None):
        if not owner:
            return None
        slot = self._get_slot(owner)
        conv = slot.get("current_conversation_id")
        if conv:
            return conv
        if "::" not in str(owner):
            norm_base = _normalize_base_owner(owner)
            slots = self.__dict__.get("_user_slots", {})
            for k, s in list(slots.items()):
                if _normalize_base_owner(k) == norm_base and s.get("current_conversation_id"):
                    return s.get("current_conversation_id")
        return None


_live_mgr = _find_existing_agent_mgr()
if _live_mgr is not None:
    _migrate_legacy_dict(_live_mgr)
    _live_mgr.__class__ = AgentTaskManager
    _live_mgr._initialized = True
