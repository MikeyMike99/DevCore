"""
Daily prompt limits per tier for users running on the host subscription.
Persists daily usage by client machine/device to ~/.config/devcore/tier_usage.json.
Tier 5 (super admin) is never limited. Users with their own BYOS subscription are not counted.
"""
import json
import os
import time

from core.roles import tier_for_role

LIMITS_FILE = os.path.expanduser("~/.config/devcore/tier_limits.json")
USAGE_FILE = os.path.expanduser("~/.config/devcore/tier_usage.json")
TIER_NAMES = {1: "Guest", 2: "Modder", 3: "Developer", 4: "Tier 4"}
DEFAULT_LIMITS = {1: 10, 2: 30, 3: 100, 4: 300}

_USAGE = {"day": "", "by_user": {}}


def get_tier_for_user(user: dict) -> int:
    if (user or {}).get("token_scope") == "demo":
        return 1
    role = (user or {}).get("role")
    return tier_for_role(role)


def get_client_tracking_key(user: dict) -> str:
    tier = get_tier_for_user(user)
    if tier == 1:
        ip = str((user or {}).get("_client_ip") or (user or {}).get("remote_addr") or "").strip()
        cid = str((user or {}).get("_client_id") or (user or {}).get("_device_id") or "").strip()
        slot = str((user or {}).get("_slot_key") or "").strip()
        clean_ip = ip if ip and ip not in ("127.0.0.1", "localhost", "::1", "anon") else ""
        if clean_ip and cid:
            return f"machine:{clean_ip}:{cid}"
        if cid:
            return f"device:{cid}"
        if clean_ip:
            return f"ip:{clean_ip}"
        if slot and slot != "guest":
            return f"slot:{slot}"
        uname = str((user or {}).get("username") or "").strip()
        if uname and uname != "guest":
            return f"user:{uname}"
        return "guest:anonymous"
    return str((user or {}).get("username") or (user or {}).get("name") or "unknown").strip()


def load_limits() -> dict:
    limits = dict(DEFAULT_LIMITS)
    try:
        with open(LIMITS_FILE, "r", encoding="utf-8") as f:
            saved = json.load(f)
        for k, v in (saved or {}).items():
            t = int(k)
            if t in TIER_NAMES:
                limits[t] = None if v is None else max(0, int(v))
    except Exception:
        pass
    return limits


def save_limits(new_limits: dict) -> dict:
    limits = load_limits()
    for k, v in (new_limits or {}).items():
        t = int(k)
        if t in TIER_NAMES:
            limits[t] = None if v is None else max(0, min(100000, int(v)))
    os.makedirs(os.path.dirname(LIMITS_FILE), mode=0o700, exist_ok=True)
    tmp = LIMITS_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({str(k): v for k, v in limits.items()}, f)
    os.replace(tmp, LIMITS_FILE)
    return limits


def _load_usage_from_disk(today: str) -> dict:
    if os.path.exists(USAGE_FILE):
        try:
            with open(USAGE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict) and data.get("day") == today:
                return data.get("by_user", {})
        except Exception:
            pass
    return {}


def _save_usage_to_disk(day: str, by_user: dict) -> None:
    try:
        os.makedirs(os.path.dirname(USAGE_FILE), mode=0o700, exist_ok=True)
        tmp = USAGE_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"day": day, "by_user": by_user}, f)
        os.replace(tmp, USAGE_FILE)
    except Exception:
        pass


def _today_usage() -> dict:
    today = time.strftime("%Y-%m-%d")
    if _USAGE["day"] != today:
        _USAGE["day"] = today
        _USAGE["by_user"] = _load_usage_from_disk(today)
    return _USAGE["by_user"]


def take_prompt(user: dict):
    tier = get_tier_for_user(user if isinstance(user, dict) else {})
    if tier >= 5:
        return True, 0, None, tier
    limit = load_limits().get(tier, DEFAULT_LIMITS[1])
    tracking_key = get_client_tracking_key(user if isinstance(user, dict) else {})
    usage = _today_usage()
    used = usage.get(tracking_key, 0)
    if limit is not None and used >= limit:
        return False, used, limit, tier
    usage[tracking_key] = used + 1
    _save_usage_to_disk(_USAGE["day"], usage)
    return True, used + 1, limit, tier


def check_prompt(user: dict):
    tier = get_tier_for_user(user if isinstance(user, dict) else {})
    if tier >= 5:
        return True, 0, None, tier
    limit = load_limits().get(tier, DEFAULT_LIMITS[1])
    tracking_key = get_client_tracking_key(user if isinstance(user, dict) else {})
    usage = _today_usage()
    used = usage.get(tracking_key, 0)
    if limit is not None and used >= limit:
        return False, used, limit, tier
    return True, used, limit, tier


def usage_summary() -> dict:
    usage = _today_usage()
    return {"users": len(usage), "prompts": sum(usage.values())}
