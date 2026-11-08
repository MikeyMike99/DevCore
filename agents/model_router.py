"""
Hybrid model router.

One ranked list of models across both subscriptions (Google: Argon/Flash via the
Antigravity CLI; Claude via the Claude CLI). When a model runs out of quota it is
remembered as exhausted until its reset time, so later requests skip it straight away
instead of failing on it first. The next best available model takes over, and it is
handed what the previous model already produced so it finishes the task rather than
starting again.
"""
import json
import os
import re
import threading
import time

STATE_FILE = os.path.expanduser("~/.config/devcore/model_quota.json")

ARGON = "Gemini 4 Argon (Medium)"
CLAUDE = "Claude Sonnet 5.5 (Medium)"
FLASH = "Gemini 3.8 Flash (High)"

# Best first, for each kind of work
HEAVY_CHAIN = [ARGON, CLAUDE, FLASH]   # doing real work: exams, code, documents
LIGHT_CHAIN = [CLAUDE, FLASH, ARGON]   # everyday questions and chat
ANALYST_CHAIN = [CLAUDE]               # planning stage (no tools; Claude CLI only)

DEFAULT_COOLDOWN = 60 * 60             # when the error gives no reset time: retry after 1 hour

_QUOTA_PATTERNS = (
    "quota reached", "quota exceeded", "resource_exhausted", "resource exhausted",
    "rate limit", "rate_limit", "usage limit", "limit reached", "hit your limit",
    "too many requests", "429", "out of credits", "credit balance",
)

_lock = threading.Lock()


def _load() -> dict:
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save(data: dict) -> None:
    try:
        os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
        tmp = STATE_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f)
        os.replace(tmp, STATE_FILE)
    except Exception:
        pass


def family(model: str) -> str:
    m = (model or "").lower()
    if "claude" in m:
        return "claude"
    if "argon" in m:
        return "argon"
    if "flash" in m:
        return "flash"
    return m


def is_quota_error(text: str) -> bool:
    t = (text or "").lower()
    return any(p in t for p in _QUOTA_PATTERNS)


def _parse_reset_seconds(text: str) -> int:
    """'Resets in 155h32m13s' / 'resets in 4h' / 'try again in 20m' / a unix time after '|'."""
    t = text or ""
    m = re.search(r"(?:reset|try again)[^0-9]{0,20}((?:\d+\s*[dhms]\s*)+)", t, re.IGNORECASE)
    if m:
        total = 0
        for num, unit in re.findall(r"(\d+)\s*([dhms])", m.group(1).lower()):
            total += int(num) * {"d": 86400, "h": 3600, "m": 60, "s": 1}[unit]
        if total > 0:
            return total
    m = re.search(r"\|(\d{10})\b", t)  # e.g. "Claude AI usage limit reached|1794200000"
    if m:
        return max(60, int(m.group(1)) - int(time.time()))
    return DEFAULT_COOLDOWN


def mark_exhausted(model: str, error_text: str = "") -> int:
    """Remember this model's family as out of quota until it resets. Returns seconds until reset."""
    secs = _parse_reset_seconds(error_text)
    with _lock:
        data = _load()
        data[family(model)] = {"until": time.time() + secs, "reason": (error_text or "")[:200]}
        _save(data)
    return secs


def is_available(model: str) -> bool:
    with _lock:
        data = _load()
        entry = data.get(family(model))
        if not entry:
            return True
        if time.time() >= float(entry.get("until", 0)):
            data.pop(family(model), None)
            _save(data)
            return True
        return False


def pick(chain: list, exclude: tuple = ()) -> str:
    """First available model in the chain, skipping excluded families. None if all are out."""
    skip = {family(x) for x in exclude}
    for m in chain:
        if family(m) not in skip and is_available(m):
            return m
    return None


def next_after(model: str, tried: tuple = ()) -> str:
    """The next best available model after `model` (and anything already tried) for heavy work."""
    return pick(HEAVY_CHAIN, exclude=tuple(tried) + (model,))


def status() -> dict:
    """For display: which models are out and when they come back."""
    data = _load()
    now = time.time()
    return {k: {"available_in_s": int(v.get("until", 0) - now)} for k, v in data.items() if v.get("until", 0) > now}


def handoff_prompt(original_prompt: str, partial_output: str, from_model: str) -> str:
    """Prompt for the model taking over: the original request plus what was already done."""
    partial = (partial_output or "").strip()
    if not partial:
        return original_prompt
    return (
        f"{original_prompt}\n\n"
        f"<PREVIOUS_WORK model=\"{from_model}\" status=\"stopped: out of quota\">\n{partial[-6000:]}\n</PREVIOUS_WORK>\n"
        "Another model started this task and ran out of quota. Continue from where it stopped and finish "
        "the task. Don't repeat work that's already done; give the user the complete final answer."
    )
