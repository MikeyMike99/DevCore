"""
Hybrid model router.

Nothing about the models is hardcoded:
  * The models are discovered from the CLIs: the Antigravity CLI (`agy models`, Google
    subscription; offers Gemini and Claude/GPT models) and the Claude CLI's model catalog
    (Claude subscription). Refreshed in the background and saved, so they survive restarts.
  * Quotas come from each CLI's own `/usage` report, so a pool that is already empty is
    skipped before any request is wasted on it. Quota errors seen during a run are remembered
    too, until their reset time.
  * The order of preference for each kind of work lives in core/model_routing.json as match
    rules ("antigravity: Argon (Medium)", ...), applied to whatever the CLIs currently offer.

When a model runs out mid-task, the next best available model takes over and is handed what
the previous model already produced, so it finishes the task instead of starting again.
"""
import datetime
import json
import os
import re
import shutil
import subprocess
import threading
import time

DEVCORE_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_FILE = os.path.join(DEVCORE_ROOT, "core", "model_routing.json")
STATE_DIR = os.path.expanduser("~/.config/devcore")
QUOTA_FILE = os.path.join(STATE_DIR, "model_quota.json")          # quota errors seen during runs
MODELS_FILE = os.path.join(STATE_DIR, "discovered_models.json")   # last model discovery
AGY_BIN = os.path.expanduser("~/.local/bin/agy_real")


def _owner_only(path: str) -> None:
    """State files in ~/.config/devcore are owner-only (0600), as the vault audit requires."""
    try:
        os.chmod(path, 0o600)
    except Exception:
        pass

GOOGLE_SUFFIX = " · via Google"   # display marker for Claude/GPT models served by the Google subscription
MODELS_TTL = 3600                 # rediscover models hourly
USAGE_TTL = 300                   # re-read /usage every 5 minutes
DEFAULT_COOLDOWN = 3600           # quota error without a reset time: retry after 1 hour
LAST_RESORT = "Gemini 3.8 Flash (High)"

_QUOTA_PATTERNS = (
    "quota reached", "quota exceeded", "resource_exhausted", "resource exhausted",
    "rate limit", "rate_limit", "usage limit", "limit reached", "hit your limit",
    "too many requests", "429", "out of credits", "credit balance",
)

_lock = threading.Lock()
_cache = {
    "config": {"mtime": None, "data": None},
    "models": {"at": 0.0, "data": None},          # {label: {backend, cli_model, quota_group}}
    "usage": {"at": 0.0, "google": [], "claude": {}},
    "refreshing": set(),
}


# ---------------- discovery ----------------

def _google_quota_group(label: str) -> str:
    """Matches the pools the Antigravity CLI's /usage reports."""
    l = label.lower()
    if "argon" in l:
        return "google:argon"          # "Gemini 4 Argon" has its own weekly limit
    if l.startswith("gemini"):
        return "google:gemini"         # "Gemini Models"
    return "google:claude_gpt"         # "Claude and GPT models"


def _discover_antigravity() -> dict:
    out = {}
    try:
        r = subprocess.run([AGY_BIN, "models"], capture_output=True, text=True, timeout=40, cwd="/tmp")
        for line in (r.stdout or "").splitlines():
            parts = line.split("\t")
            if len(parts) < 2 or not parts[1].strip():
                continue
            name = parts[1].strip()
            is_gemini = name.lower().startswith("gemini")
            label = name if is_gemini else name + GOOGLE_SUFFIX
            out[label] = {"backend": "antigravity", "cli_model": name, "quota_group": _google_quota_group(name)}
    except Exception:
        pass
    return out


def _discover_claude_cli() -> dict:
    out = {}
    try:
        from core.local_model_service import get_claude_models
        for m in get_claude_models() or []:
            mid, text = (m.get("value") or "").strip(), (m.get("text") or "").strip()
            if not mid.startswith("claude-"):
                continue
            label = f"Claude {text}" if not text.lower().startswith("claude") else text
            out[label] = {"backend": "claude_cli", "cli_model": mid, "quota_group": "claude_sub"}
    except Exception:
        pass
    return out


def _refresh_models() -> None:
    found = {}
    found.update(_discover_antigravity())
    found.update(_discover_claude_cli())
    if found:
        _cache["models"].update(at=time.time(), data=found)
        try:
            os.makedirs(STATE_DIR, mode=0o700, exist_ok=True)
            with open(MODELS_FILE + ".tmp", "w", encoding="utf-8") as f:
                json.dump(found, f)
            _owner_only(MODELS_FILE + ".tmp")
            os.replace(MODELS_FILE + ".tmp", MODELS_FILE)
        except Exception:
            pass


def _refresh_usage() -> None:
    google, claude = [], {}
    try:
        r = subprocess.run([AGY_BIN, "-p", "/usage", "--print-timeout", "40s"],
                           capture_output=True, text=True, timeout=50, cwd="/tmp")
        for line in (r.stdout or "").splitlines():
            p = [x.strip() for x in line.split("\t")]
            if len(p) < 4 or not p[2].endswith("%"):
                continue
            try:
                left = int(float(p[2].rstrip("%")))
                reset = datetime.datetime.fromisoformat(p[3].replace("Z", "+00:00")).timestamp()
            except Exception:
                continue
            period = "5-hour" if "five hour" in p[1].lower() else ("Weekly" if "weekly" in p[1].lower() else p[1])
            google.append({"group": p[0], "period": period, "remaining_pct": left, "reset_ts": reset})
    except Exception:
        pass
    try:
        cb = shutil.which("claude") or os.path.expanduser("~/.local/bin/claude")
        r = subprocess.run([cb, "-p", "/usage"], capture_output=True, text=True, timeout=45, cwd="/tmp")
        out = r.stdout or ""
        m = re.search(r"Current session:\s*(\d+)%\s*used\s*[·\-]\s*resets\s*([^\n]+)", out)
        w = re.search(r"Current week[^:]*:\s*(\d+)%\s*used\s*[·\-]\s*resets\s*([^\n]+)", out)
        if m:
            claude.update(session_pct=int(m.group(1)), session_resets=re.sub(r"\s*\([^)]*\)\s*$", "", m.group(2)).strip())
        if w:
            claude.update(week_pct=int(w.group(1)), week_resets=re.sub(r"\s*\([^)]*\)\s*$", "", w.group(2)).strip())
    except Exception:
        pass
    prev = _cache["usage"]
    # A failed read (CLI busy at startup) keeps the last good data and retries within ~30s
    at = time.time() if google else time.time() - USAGE_TTL + 30
    _cache["usage"].update(at=at, google=google or prev.get("google", []), claude=claude or prev.get("claude", {}))


def _in_background(name: str, fn) -> None:
    with _lock:
        if name in _cache["refreshing"]:
            return
        _cache["refreshing"].add(name)

    def run():
        try:
            fn()
        finally:
            _cache["refreshing"].discard(name)
    threading.Thread(target=run, daemon=True).start()


def discovered_models() -> dict:
    """{label: {backend, cli_model, quota_group}} from the CLIs (never blocks for long)."""
    data = _cache["models"]["data"]
    if data is None:
        try:
            with open(MODELS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            _cache["models"].update(data=data, at=os.path.getmtime(MODELS_FILE))
        except Exception:
            _refresh_models()   # first run ever: discover once, synchronously
            data = _cache["models"]["data"] or {}
    if time.time() - _cache["models"]["at"] > MODELS_TTL:
        _in_background("models", _refresh_models)
    return data or {}


def usage_snapshot(wait: bool = False) -> dict:
    """Latest /usage readings from both CLIs. `wait` refreshes synchronously when stale."""
    if time.time() - _cache["usage"]["at"] > USAGE_TTL:
        if wait or _cache["usage"]["at"] == 0:
            _refresh_usage()
        else:
            _in_background("usage", _refresh_usage)
    return _cache["usage"]


# ---------------- configuration ----------------

def load_config() -> dict:
    c = _cache["config"]
    try:
        mtime = os.path.getmtime(CONFIG_FILE)
        if c["data"] is None or c["mtime"] != mtime:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                c.update(data=json.load(f), mtime=mtime)
    except Exception:
        pass
    return c["data"] or {"chains": {}}


def chain(kind: str) -> list:
    """The preference rules for `kind`, resolved against the models the CLIs currently offer."""
    models = discovered_models()
    resolved = []
    for rule in load_config().get("chains", {}).get(kind, []):
        if isinstance(rule, str):
            rule = {"match": rule}
        want_backend = rule.get("backend")
        raw = rule.get("match", "")
        words = [str(w).lower() for w in (raw if isinstance(raw, list) else [raw]) if str(w)]
        for label, info in models.items():
            if want_backend and info.get("backend") != want_backend:
                continue
            hay = (info.get("cli_model", "") + " " + label).lower()
            if not all(w in hay for w in words):   # every word in 'match' must appear
                continue
            if label not in resolved:
                resolved.append(label)
            break
    return resolved


def configured_models() -> list:
    """Every model any chain can currently use (for display)."""
    seen = []
    for kind in ("heavy", "light", "analyst"):
        for m in chain(kind):
            if m not in seen:
                seen.append(m)
    return seen


def _entry(model: str) -> dict:
    return discovered_models().get(model or "", {})


def backend(model: str) -> str:
    """'claude_cli' (Claude subscription) or 'antigravity' (Google subscription)."""
    b = _entry(model).get("backend")
    if b:
        return b
    m = model or ""
    if m.endswith(GOOGLE_SUFFIX):
        return "antigravity"
    return "claude_cli" if "claude" in m.lower() else "antigravity"


def cli_model_name(model: str) -> str:
    """The model name the backend CLI expects."""
    e = _entry(model)
    if e.get("cli_model"):
        return e["cli_model"]
    m = model or ""
    return m[: -len(GOOGLE_SUFFIX)] if m.endswith(GOOGLE_SUFFIX) else m


def family(model: str) -> str:
    """Quota group: models in one group share a quota."""
    g = _entry(model).get("quota_group")
    if g:
        return g
    if backend(model) == "claude_cli":
        return "claude_sub"
    return _google_quota_group(cli_model_name(model))


def is_google_claude(model: str) -> bool:
    return backend(model) == "antigravity" and "claude" in cli_model_name(model).lower()


def __getattr__(name):
    # Read live each time, so config edits and newly discovered models apply without a restart
    if name == "HEAVY_CHAIN":
        return chain("heavy")
    if name == "LIGHT_CHAIN":
        return chain("light")
    if name == "ANALYST_CHAIN":
        return chain("analyst")
    if name == "FLASH":  # last resort
        heavy = chain("heavy")
        return heavy[-1] if heavy else LAST_RESORT
    raise AttributeError(name)


# ---------------- quota ----------------

def _load_quota() -> dict:
    try:
        with open(QUOTA_FILE, "r", encoding="utf-8") as f:
            d = json.load(f)
            return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def _save_quota(data: dict) -> None:
    try:
        os.makedirs(STATE_DIR, mode=0o700, exist_ok=True)
        with open(QUOTA_FILE + ".tmp", "w", encoding="utf-8") as f:
            json.dump(data, f)
        _owner_only(QUOTA_FILE + ".tmp")
        os.replace(QUOTA_FILE + ".tmp", QUOTA_FILE)
    except Exception:
        pass


def is_quota_error(text: str) -> bool:
    t = (text or "").lower()
    return any(p in t for p in _QUOTA_PATTERNS)


def _parse_reset_seconds(text: str) -> int:
    t = text or ""
    m = re.search(r"(?:reset|try again)[^0-9]{0,20}((?:\d+\s*[dhms]\s*)+)", t, re.IGNORECASE)
    if m:
        total = sum(int(n) * {"d": 86400, "h": 3600, "m": 60, "s": 1}[u]
                    for n, u in re.findall(r"(\d+)\s*([dhms])", m.group(1).lower()))
        if total > 0:
            return total
    m = re.search(r"\|(\d{10})\b", t)
    if m:
        return max(60, int(m.group(1)) - int(time.time()))
    return DEFAULT_COOLDOWN


def mark_exhausted(model: str, error_text: str = "") -> int:
    secs = _parse_reset_seconds(error_text)
    with _lock:
        data = _load_quota()
        data[family(model)] = {"until": time.time() + secs, "reason": (error_text or "")[:200]}
        _save_quota(data)
    return secs


_USAGE_GROUP_TO_QUOTA = {"gemini 4 argon": "google:argon", "gemini models": "google:gemini",
                         "claude and gpt models": "google:claude_gpt"}


def _usage_exhausted() -> dict:
    """Quota groups the CLIs' own /usage reports as empty: {group: reset_ts}."""
    snap = usage_snapshot()
    out = {}
    for row in snap.get("google", []):
        g = _USAGE_GROUP_TO_QUOTA.get(row["group"].lower())
        if g and row["remaining_pct"] <= 0:
            out[g] = max(out.get(g, 0), row["reset_ts"])
    if "gemini models" in [r["group"].lower() for r in snap.get("google", []) if r["remaining_pct"] <= 0]:
        out.setdefault("google:argon", out.get("google:gemini", 0))   # Argon is a Gemini model too
    c = snap.get("claude", {})
    if c.get("session_pct", 0) >= 100 or c.get("week_pct", 0) >= 100:
        out["claude_sub"] = time.time() + DEFAULT_COOLDOWN
    return out


def is_available(model: str) -> bool:
    g = family(model)
    if g in _usage_exhausted():
        return False
    with _lock:
        data = _load_quota()
        entry = data.get(g)
        if not entry:
            return True
        if time.time() >= float(entry.get("until", 0)):
            data.pop(g, None)
            _save_quota(data)
            return True
        return False


def pick(models: list, exclude: tuple = ()) -> str:
    skip = {family(x) for x in exclude}
    for m in models:
        if family(m) not in skip and is_available(m):
            return m
    return None


def next_after(model: str, tried: tuple = ()) -> str:
    return pick(chain("heavy"), exclude=tuple(tried) + (model,))


def status() -> dict:
    """{quota_group: {available_in_s}} for groups that are out (from /usage and from errors seen)."""
    now = time.time()
    out = {g: {"available_in_s": int(ts - now)} for g, ts in _usage_exhausted().items() if ts > now}
    for g, v in _load_quota().items():
        if v.get("until", 0) > now and g not in out:
            out[g] = {"available_in_s": int(v["until"] - now)}
    return out


def handoff_prompt(original_prompt: str, partial_output: str, from_model: str) -> str:
    partial = (partial_output or "").strip()
    if not partial:
        return original_prompt
    return (
        f"{original_prompt}\n\n"
        f"<PREVIOUS_WORK model=\"{from_model}\" status=\"stopped: out of quota\">\n{partial[-6000:]}\n</PREVIOUS_WORK>\n"
        "Another model started this task and ran out of quota. Continue from where it stopped and finish "
        "the task. Don't repeat work that's already done; give the user the complete final answer."
    )


# Warm the caches in the background when the server imports this module
_in_background("models_warm", lambda: discovered_models())
_in_background("usage_warm", lambda: usage_snapshot(wait=True))
