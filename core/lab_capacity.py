"""Capacity manager for the live Linux terminals (core/lab_proxy.py).

One place that knows how many terminals are open, how many this machine can safely carry right now, and what to tell
learners when it is getting full. Nothing here starts or stops a lab computer; it only decides "may one more terminal
open?" and reports the level (ok / busy / full) with a plain-language message.

What it manages:
  * A hard safety ceiling (SIRAUGGA_LAB_MAX_TERMINALS, default 150).
  * A memory-aware ceiling: when the machine's free memory shrinks, the ceiling shrinks with it, so we say "full"
    before the machine starts failing (measured: failures begin when free memory runs out, not at a fixed count).
  * A per-learner limit (2), so one learner with many tabs cannot take other learners' places.
  * Idle terminals are closed by the proxy after SIRAUGGA_LAB_IDLE_SECONDS (default 5 minutes) to free their place.
"""
import base64
import json
import logging
import math
import os
import time

log = logging.getLogger("siraugga.lab_capacity")


def _env_int(name: str, default: int, lo: int, hi: int) -> int:
    try:
        return max(lo, min(hi, int(os.environ.get(name, default))))
    except (TypeError, ValueError):
        return default


MAX_TERMINALS = _env_int("SIRAUGGA_LAB_MAX_TERMINALS", 150, 1, 500)    # only a safety net: free memory is the real limit
PER_LEARNER = _env_int("SIRAUGGA_LAB_PER_LEARNER", 2, 1, 10)
IDLE_SECONDS = _env_int("SIRAUGGA_LAB_IDLE_SECONDS", 300, 60, 7200)
RESERVE_MB = _env_int("SIRAUGGA_LAB_RESERVE_MB", 800, 100, 64000)         # WSL memory always left free (containers failed at ~420)
HOST_RESERVE_MB = _env_int("SIRAUGGA_LAB_HOST_RESERVE_MB", 1000, 100, 64000)   # Windows memory always left free for Windows itself
PER_TERMINAL_MB = _env_int("SIRAUGGA_LAB_PER_TERMINAL_MB", 40, 10, 2000)  # measured 15-30 MB idle, so this has margin
BUSY_RATIO = 0.7                                                           # "busy" from 70% of what we can carry
HIGH_LOAD_PER_CPU = 1.5

MESSAGES = {
    "ok": "",
    "busy": "The practice terminals are busy right now. A Linux computer may start slowly and respond more slowly than usual. "
            "The simulated terminal is not affected and is the faster choice.",
    "full": "All the live Linux containers are in use right now, so we have switched you to the simulated terminal. "
            "You can keep practising and switch back to a Linux container later.",
}

_open = {}            # connection id -> learner key
_next_id = 0
_last_level = "ok"


def available_mb():
    """Free memory in MB (Linux/WSL), or None when it cannot be read."""
    try:
        with open("/proc/meminfo", encoding="ascii") as f:
            for line in f:
                if line.startswith("MemAvailable:"):
                    return int(line.split()[1]) // 1024
    except (OSError, ValueError, IndexError):
        pass
    return None


_HOST = {"mb": None, "at": 0.0, "running": False}


def _read_host_free_mb():
    """Free memory of the Windows machine that hosts WSL (None when not on WSL or unreadable)."""
    if not os.path.exists("/mnt/c/Windows"):
        return None
    try:
        import subprocess
        out = subprocess.run(["powershell.exe", "-NoProfile", "-Command",
                              "(Get-CimInstance Win32_OperatingSystem).FreePhysicalMemory"],
                             capture_output=True, text=True, timeout=20).stdout.strip()
        return int(out) // 1024
    except Exception:
        return None


def _refresh_host():
    try:
        _HOST["mb"] = _read_host_free_mb()
        _HOST["at"] = time.monotonic()
    finally:
        _HOST["running"] = False


def host_free_mb():
    """Windows' free memory, refreshed in the background every ~20 s (reading it takes about a second, so a request never
    waits for it). WSL only grows into what Windows can spare, so this is the other half of "how much room is there"."""
    import threading
    if not _HOST["running"] and time.monotonic() - _HOST["at"] > 20:
        _HOST["running"] = True
        threading.Thread(target=_refresh_host, daemon=True).start()
    return _HOST["mb"]


def idle_limit(level: str) -> int:
    """Seconds a terminal may sit idle before it is closed. Elastic: the fuller we are, the sooner abandoned terminals go."""
    return {"ok": IDLE_SECONDS, "busy": max(60, IDLE_SECONDS // 3), "full": max(60, IDLE_SECONDS // 8)}.get(level, IDLE_SECONDS)


def load_per_cpu():
    try:
        return os.getloadavg()[0] / (os.cpu_count() or 1)
    except (OSError, AttributeError):
        return None


def learner_of(token: str) -> str:
    """Who a terminal link belongs to, read from the link's payload. Only used to count places per learner: the lab
    itself checks the signature, so a forged name gains nothing (it still takes a place from the shared ceiling)."""
    try:
        payload = token.split(".", 1)[0]
        data = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
        return str(data.get("l") or token)[:80]
    except (ValueError, TypeError, AttributeError):
        return str(token)[:80]


def effective_max(avail=None, used=None, host=None) -> int:
    """How many terminals may be open right now. Elastic: the hard ceiling, limited by whichever is tighter - the room left
    in WSL or the room Windows can still spare - so the number grows and shrinks with what the machine can really carry."""
    used = len(_open) if used is None else used
    rooms = []
    if avail is not None:
        rooms.append(int((avail - RESERVE_MB) / PER_TERMINAL_MB))
    if host is not None:
        rooms.append(int((host - HOST_RESERVE_MB) / PER_TERMINAL_MB))
    if not rooms:
        return MAX_TERMINALS
    return max(0, min(MAX_TERMINALS, used + min(rooms)))


def snapshot(avail="auto", load="auto", host="auto") -> dict:
    """Where we stand: {level, message, terminals, limit}. level is 'ok', 'busy' or 'full'."""
    global _last_level
    avail = available_mb() if avail == "auto" else avail
    load = load_per_cpu() if load == "auto" else load
    host = host_free_mb() if host == "auto" else host
    used = len(_open)
    limit = effective_max(avail, used, host)
    if used >= limit:
        level = "full"
    elif (used >= math.ceil(BUSY_RATIO * limit)
          or (avail is not None and avail < RESERVE_MB * 1.5)
          or (host is not None and host < HOST_RESERVE_MB * 1.5)
          or (load is not None and load > HIGH_LOAD_PER_CPU)):
        level = "busy"
    else:
        level = "ok"
    if level != _last_level:
        (log.warning if level != "ok" else log.info)(
            "lab capacity %s -> %s (terminals %d/%d, free memory WSL %s MB, Windows %s MB)",
            _last_level, level, used, limit, avail, host)
        _last_level = level
    return {"level": level, "message": MESSAGES[level], "terminals": used, "limit": limit}


def current_idle_limit() -> int:
    return idle_limit(_last_level)


def acquire(token: str):
    """Reserve a place for one terminal. Returns (connection id, "") or (None, reason) with reason 'full' or 'per_learner'."""
    global _next_id
    who = learner_of(token)
    if sum(1 for w in _open.values() if w == who) >= PER_LEARNER:
        return None, "per_learner"
    if snapshot()["level"] == "full":
        return None, "full"
    _next_id += 1
    _open[_next_id] = who
    return _next_id, ""


def release(conn_id) -> None:
    _open.pop(conn_id, None)


def open_count() -> int:
    return len(_open)


def idle_for(last_activity: float) -> float:
    return time.monotonic() - last_activity
