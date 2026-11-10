"""CyberBrief automatic schedule: refresh the threat feed and send the newsletter.

Runs as one daemon thread inside the DevCore server (started by app.mount()).
Every CHECK_SECONDS it:
  1. refreshes the feed every THREAT_FEED_REFRESH_HOURS (the feed engine also has
     its own per-source cooldowns), which also queues story generation;
  2. at/after SEND_HOUR local time sends each cadence that is due today:
       daily   -> every day
       weekly  -> on WEEKLY_DAY (0 = Monday)
       monthly -> on the 1st
     A cadence is sent at most once per local day (remembered in
     cache/schedule_state.json), never a day late if the PC was off, and skipped when
     the digest has no new stories since that cadence's last send.

Settings (services/cyberbrief/.env or environment):
  CYBERBRIEF_SCHEDULE=on|off   CYBERBRIEF_SEND_HOUR=7   CYBERBRIEF_WEEKLY_DAY=0
  CYBERBRIEF_TZ=Africa/Johannesburg
The admin page can also pause/resume sending (stored in the state file).
"""
from __future__ import annotations

import json
import logging
import threading
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from .config import Config, _env

log = logging.getLogger("cyberbrief.scheduler")

CHECK_SECONDS = 300
STATE_FILE = Config.ROOT_DIR / "cache" / "schedule_state.json"
_lock = threading.Lock()
_thread: threading.Thread | None = None


def _settings() -> dict:
    def as_int(key, default, lo, hi):
        try:
            v = int(_env(key, default))
            return v if lo <= v <= hi else default
        except (TypeError, ValueError):
            return default
    return {
        "enabled": str(_env("CYBERBRIEF_SCHEDULE", "on")).lower() not in ("off", "0", "false", "no"),
        "send_hour": as_int("CYBERBRIEF_SEND_HOUR", 7, 0, 23),
        "weekly_day": as_int("CYBERBRIEF_WEEKLY_DAY", 0, 0, 6),
        "refresh_hours": as_int("THREAT_FEED_REFRESH_HOURS", 6, 1, 48),
        "tz": ZoneInfo(_env("CYBERBRIEF_TZ", "Africa/Johannesburg")),
    }


def load_state() -> dict:
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_state(state: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2), encoding="utf-8")
    tmp.replace(STATE_FILE)


def set_paused(paused: bool) -> None:
    with _lock:
        state = load_state()
        state["paused"] = bool(paused)
        save_state(state)


def due_cadences(now: datetime, s: dict) -> list:
    """Cadences scheduled for today's date (ignores the hour)."""
    due = ["daily"]
    if now.weekday() == s["weekly_day"]:
        due.append("weekly")
    if now.day == 1:
        due.append("monthly")
    return due


def next_send(now: datetime, s: dict, state: dict) -> datetime:
    """Next moment a send could happen (for display on the admin page)."""
    today = now.date().isoformat()
    at = now.replace(hour=s["send_hour"], minute=0, second=0, microsecond=0)
    if now >= at and state.get("sent", {}).get("daily") == today:
        at += timedelta(days=1)
    elif now >= at:
        return now
    return at


QUEUE_URL = (_env("JOSHY_API_URL", "https://api.mikeytech.dev") or "").rstrip("/")


def _queue_api(method: str, path: str, body=None):
    import urllib.request
    data = None if body is None else json.dumps(body).encode("utf-8")
    req = urllib.request.Request(f"{QUEUE_URL}{path}", data=data, method=method, headers={
        "Authorization": f"Bearer {_env('JOSHY_API_ADMIN_SECRET', '')}", "Content-Type": "application/json",
        "Accept": "application/json", "User-Agent": "cyberbrief-queue/1.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8", errors="replace"))


def process_newsletter_queue(api=None, subscribe=None, unsubscribe=None) -> dict:
    """Apply signups/unsubscribes the public site stored in Cloudflare D1 while this PC
    was offline (see the e-profile Pages Function). Returns counts."""
    if api is None:
        if not _env("JOSHY_API_ADMIN_SECRET"):
            return {"skipped": "no JOSHY_API_ADMIN_SECRET"}
        api = _queue_api
    if subscribe is None or unsubscribe is None:
        from .notify_mod import subscribe_newsletter, unsubscribe_by_token
        subscribe = subscribe or subscribe_newsletter
        unsubscribe = unsubscribe or unsubscribe_by_token
    items = api("GET", "/admin/newsletter-queue").get("items", [])
    done, counts = [], {"subscribed": 0, "unsubscribed": 0, "invalid": 0}
    for it in items:
        try:
            p = json.loads(it.get("payload") or "{}")
            if it.get("action") == "subscribe":
                topics = p.get("topics")
                if isinstance(topics, str):
                    topics = [t.strip() for t in topics.split(",") if t.strip()]
                subscribe(email=p.get("email", ""), delivery_format=p.get("format", "hybrid_brief"),
                          primary_appetite=p.get("appetite", "cyber_thriller"), topics=topics,
                          engagement_modules=p.get("engagement_modules"), send_welcome=True,
                          cadence=p.get("cadence") or p.get("sub_frequency") or p.get("frequency") or "daily")
                counts["subscribed"] += 1
            elif it.get("action") == "unsubscribe":
                unsubscribe(p.get("token", ""), purge=bool(p.get("purge")))
                counts["unsubscribed"] += 1
            else:
                counts["invalid"] += 1
            done.append(it["id"])
        except (ValueError, KeyError, TypeError):
            counts["invalid"] += 1
            done.append(it["id"])          # bad data: don't retry forever
        except Exception as exc:           # e.g. mail/network trouble: retry next pass
            log.warning("CyberBrief queue item %s failed: %s", it.get("id"), exc)
    if done:
        api("POST", "/admin/newsletter-queue/done", {"ids": done})
    return counts


def tick(now: datetime | None = None, *, refresh=None, send=None, manifest=None) -> dict:
    """One scheduler pass. Dependencies are injectable for tests. Returns what it did."""
    s = _settings()
    now = now or datetime.now(s["tz"])
    if refresh is None:
        from .newsletter_mod import threat_engine
        refresh = threat_engine.refresh_feed
    if send is None:
        from .notify_mod import notify_newsletter
        send = lambda cadence: notify_newsletter(base_url=Config.BASE_URL, cadence=cadence)
    if manifest is None:
        from .newsletter_mod import load_active_manifest
        manifest = load_active_manifest

    did = {"refreshed": False, "sent": {}, "skipped": {}}
    with _lock:
        state = load_state()
        state.setdefault("sent", {})
        state.setdefault("sent_digest", {})

        if not s["enabled"]:
            return did

        # 1. Feed refresh
        last_refresh = float(state.get("last_refresh_ts") or 0)
        if time.time() - last_refresh >= s["refresh_hours"] * 3600:
            try:
                result = refresh(force=False)
                state["last_refresh_ts"] = time.time()
                state["last_refresh_result"] = (result or {}).get("status") or (result or {}).get("note") or "ok"
                did["refreshed"] = True
            except Exception as exc:  # network down etc.: try again next pass
                log.warning("CyberBrief feed refresh failed: %s", exc)
                state["last_refresh_result"] = f"error: {exc}"

        # 2. Sends
        today = now.date().isoformat()
        if not state.get("initialized"):
            # First run ever: don't fire today's send just because the server started
            # after SEND_HOUR. The first automatic send is the next scheduled one.
            if now.hour >= s["send_hour"]:
                for cadence in due_cadences(now, s):
                    state["sent"].setdefault(cadence, today)
            state["initialized"] = True
        if not state.get("paused") and now.hour >= s["send_hour"]:
            digest = manifest() or {}
            digest_id = digest.get("dispatched_at") or ""
            for cadence in due_cadences(now, s):
                if state["sent"].get(cadence) == today:
                    continue
                if not digest.get("items"):
                    did["skipped"][cadence] = "digest is empty"
                    state["sent"][cadence] = today
                    continue
                if digest_id and state["sent_digest"].get(cadence) == digest_id:
                    did["skipped"][cadence] = "no new stories since last send"
                    state["sent"][cadence] = today
                    continue
                try:
                    result = send(cadence) or {}
                    did["sent"][cadence] = result.get("sent", 0)
                    state["sent"][cadence] = today
                    state["sent_digest"][cadence] = digest_id
                    state.setdefault("history", []).insert(0, {
                        "at": now.strftime("%Y-%m-%d %H:%M"), "cadence": cadence,
                        "sent": result.get("sent", 0), "message": result.get("message", ""),
                    })
                    state["history"] = state["history"][:20]
                except Exception as exc:
                    log.warning("CyberBrief %s send failed: %s", cadence, exc)
                    did["skipped"][cadence] = f"error: {exc}"

        state["last_tick"] = now.strftime("%Y-%m-%d %H:%M")
        save_state(state)
    return did


def status() -> dict:
    s = _settings()
    now = datetime.now(s["tz"])
    state = load_state()
    last_refresh = state.get("last_refresh_ts")
    return {
        "enabled": s["enabled"],
        "paused": bool(state.get("paused")),
        "send_hour": s["send_hour"],
        "weekly_day": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"][s["weekly_day"]],
        "timezone": str(s["tz"]),
        "next_send": next_send(now, s, state).strftime("%Y-%m-%d %H:%M"),
        "last_refresh": datetime.fromtimestamp(last_refresh, s["tz"]).strftime("%Y-%m-%d %H:%M") if last_refresh else None,
        "last_refresh_result": state.get("last_refresh_result"),
        "last_tick": state.get("last_tick"),
        "sent": state.get("sent", {}),
        "history": state.get("history", [])[:8],
        "running": bool(_thread and _thread.is_alive()),
    }


def _loop():
    time.sleep(30)  # let DevCore finish starting
    while True:
        try:  # always, even when the schedule is off or paused: these are user requests
            q = process_newsletter_queue()
            if any(q.get(k) for k in ("subscribed", "unsubscribed", "invalid")):
                log.info("CyberBrief offline queue applied: %s", q)
        except Exception as exc:
            log.warning("CyberBrief offline queue failed: %s", exc)
        try:
            tick()
        except Exception as exc:
            log.warning("CyberBrief scheduler pass failed: %s", exc)
        time.sleep(CHECK_SECONDS)


def start() -> bool:
    """Start the scheduler thread once per process."""
    global _thread
    if _thread and _thread.is_alive():
        return False
    _thread = threading.Thread(target=_loop, name="cyberbrief-scheduler", daemon=True)
    _thread.start()
    return True
