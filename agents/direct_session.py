"""Direct mode: one live Claude Code session for the Super Admin (Tier 5 owner only).

The /direct page talks to it over the /ws/direct websocket (core/server.py). Unlike the normal
chat, which starts a new one-shot CLI run per message, this keeps ONE `claude` process running
in stream-json mode for the whole conversation, so tools, shell, files and background work carry
on between messages. The session id is saved, so a page reload or a server restart resumes the
same conversation.

Security: only ever started from the /ws/direct handler after security_mgr.is_super_admin().
It runs with full access (--dangerously-skip-permissions), the same as admin agent runs today.
Nothing here is reachable by Tier 1-4 users or guests.
"""
import asyncio
import json
import logging
import os
import shutil
import sys
import time
from datetime import datetime, timedelta, timezone

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATE_DIR = os.path.join(BASE_DIR, "data", "direct_mode")
AUDIT_FILE = os.path.join(BASE_DIR, "logs", "direct_mode_audit.jsonl")
SAST = timezone(timedelta(hours=2))
IDLE_LIMIT = 2 * 3600       # close the process after 2 hours with nothing happening
HISTORY_LIMIT = 400         # events kept for replay after a page reload
STOP_GRACE = 10             # seconds to wait for a polite interrupt before killing the process

SYSTEM_NOTE = (
    "You are in Siraugga Direct mode: the Siraugga owner (Tier 5 Super Admin) is talking to you "
    "through a web chat page with a screen reader (NVDA or JAWS). Write plain, simple, linear "
    "text: short paragraphs and simple lists, no tables, no ASCII art, no decorative symbols. "
    "Give times in SAST (UTC+2). The DevCore folder is your working folder."
)


def now_sast() -> str:
    return datetime.now(SAST).strftime("%Y-%m-%d %H:%M:%S SAST")


def audit(event: str, user: str = "", ip: str = "", detail=None) -> None:
    """Append one line to the Direct mode audit trail. Never raises."""
    try:
        os.makedirs(os.path.dirname(AUDIT_FILE), exist_ok=True)
        row = {"time": now_sast(), "ts": round(time.time(), 3), "event": event, "user": user, "ip": ip}
        if detail is not None:
            row["detail"] = detail
        with open(AUDIT_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    except Exception as e:
        logging.error(f"[DirectMode] audit write failed: {e}")


def _claude_command():
    """The claude CLI, run directly on Linux/WSL or through wsl.exe on Windows."""
    if sys.platform == "win32":
        return ["wsl.exe", "-e", "bash", "-lc", 'exec ~/.local/bin/claude "$@"', "_"]
    found = shutil.which("claude") or os.path.expanduser("~/.local/bin/claude")
    return [found]


def _short(value, limit=160) -> str:
    s = " ".join(str(value or "").split())
    return s if len(s) <= limit else s[: limit - 1] + "…"


def describe_tool(name: str, inp: dict) -> str:
    """One plain sentence for a tool call, for the screen reader activity line."""
    inp = inp or {}
    path = inp.get("file_path") or inp.get("path") or inp.get("notebook_path") or ""
    if name == "Bash":
        return "Running a command: " + _short(inp.get("description") or inp.get("command"))
    if name == "Read":
        return "Reading a file: " + _short(path)
    if name in ("Edit", "MultiEdit", "NotebookEdit"):
        return "Editing a file: " + _short(path)
    if name == "Write":
        return "Writing a file: " + _short(path)
    if name in ("Grep", "Glob"):
        return "Searching files for: " + _short(inp.get("pattern"))
    if name == "WebSearch":
        return "Searching the web for: " + _short(inp.get("query"))
    if name == "WebFetch":
        return "Reading a web page: " + _short(inp.get("url"))
    if name in ("Task", "Agent"):
        return "Starting a helper agent: " + _short(inp.get("description"))
    if name == "TodoWrite":
        return "Updating its task list"
    return "Using the tool " + _short(name, 60)


class DirectSession:
    def __init__(self, key: str):
        self.key = key
        self.proc = None
        self.reader_task = None
        self.session_id = None
        self.working = False
        self.history = []
        self.listeners = set()
        self.last_activity = time.time()
        self.lock = asyncio.Lock()
        self._stopping = False
        self._load()

    # ---- saved state ---------------------------------------------------------------------
    def _state_path(self):
        safe = "".join(c for c in self.key if c.isalnum() or c in "-_") or "owner"
        return os.path.join(STATE_DIR, f"{safe}.json")

    def _load(self):
        try:
            with open(self._state_path(), encoding="utf-8") as f:
                d = json.load(f)
            self.session_id = d.get("session_id")
            self.history = list(d.get("history") or [])[-HISTORY_LIMIT:]
        except Exception:
            pass

    def _save(self):
        try:
            os.makedirs(STATE_DIR, exist_ok=True)
            tmp = self._state_path() + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump({"session_id": self.session_id, "history": self.history[-HISTORY_LIMIT:]}, f)
            os.replace(tmp, self._state_path())
        except Exception as e:
            logging.error(f"[DirectMode] save failed: {e}")

    # ---- events to the page --------------------------------------------------------------
    def subscribe(self) -> asyncio.Queue:
        q = asyncio.Queue()
        self.listeners.add(q)
        return q

    def unsubscribe(self, q):
        self.listeners.discard(q)

    def snapshot(self) -> dict:
        return {"type": "history", "events": self.history[-HISTORY_LIMIT:], "working": self.working,
                "running": self.alive(), "has_session": bool(self.session_id)}

    def _emit(self, event: dict, keep=True):
        event = dict(event)
        event.setdefault("time", now_sast())
        if keep:
            self.history.append(event)
            if len(self.history) > HISTORY_LIMIT:
                self.history = self.history[-HISTORY_LIMIT:]
        for q in list(self.listeners):
            q.put_nowait(event)

    def _set_working(self, value: bool):
        if self.working != value:
            self.working = value
            self._emit({"type": "status", "state": "working" if value else "finished"}, keep=False)

    # ---- process -------------------------------------------------------------------------
    def alive(self) -> bool:
        return self.proc is not None and self.proc.returncode is None

    async def _start(self):
        args = ["-p", "--input-format", "stream-json", "--output-format", "stream-json", "--verbose",
                "--dangerously-skip-permissions", "--append-system-prompt", SYSTEM_NOTE]
        if self.session_id:
            args += ["--resume", self.session_id]
        env = dict(os.environ)
        for k in ("DEVCORE_RESEARCH_MODE", "CLAUDECODE", "CLAUDE_CODE_ENTRYPOINT"):
            env.pop(k, None)
        env["DEVCORE_AGENT_IS_ADMIN"] = "1"
        self.proc = await asyncio.create_subprocess_exec(
            *_claude_command(), *args, cwd=BASE_DIR, env=env,
            stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            limit=64 * 1024 * 1024)
        self.reader_task = asyncio.create_task(self._read(self.proc))
        asyncio.create_task(self._drain_stderr(self.proc))
        audit("process_started", self.key, detail={"resumed": bool(self.session_id), "pid": self.proc.pid})

    async def _drain_stderr(self, proc):
        try:
            async for line in proc.stderr:
                text = line.decode("utf-8", "replace").strip()
                if text:
                    logging.warning(f"[DirectMode] claude stderr: {text[:500]}")
        except Exception:
            pass

    async def _write(self, obj: dict):
        self.proc.stdin.write((json.dumps(obj) + "\n").encode("utf-8"))
        await self.proc.stdin.drain()

    async def _read(self, proc):
        try:
            async for raw in proc.stdout:
                try:
                    msg = json.loads(raw)
                except Exception:
                    continue
                self.last_activity = time.time()
                self._handle(msg)
        except Exception as e:
            logging.error(f"[DirectMode] reader error: {e}")
        finally:
            await proc.wait()
            if self.proc is proc:
                self.proc = None
                was_working = self.working
                self._set_working(False)
                self._emit({"type": "notice", "text": "The Claude Code session closed. "
                            + ("Your next message resumes it." if self.session_id else "Your next message starts a new one.")},
                           keep=was_working)
                self._save()

    def _handle(self, msg: dict):
        t = msg.get("type")
        if msg.get("session_id") and msg.get("session_id") != self.session_id:
            self.session_id = msg["session_id"]
            self._save()
        if t == "system" and msg.get("subtype") == "init":
            self._set_working(True)   # a turn is starting (also when background work wakes it up)
        elif t == "assistant":
            for block in (msg.get("message") or {}).get("content") or []:
                bt = block.get("type")
                if bt == "text" and (block.get("text") or "").strip():
                    self._emit({"type": "reply", "text": block["text"]})
                elif bt == "tool_use":
                    self._emit({"type": "tool", "text": describe_tool(block.get("name"), block.get("input"))})
        elif t == "user":
            for block in (msg.get("message") or {}).get("content") or []:
                if isinstance(block, dict) and block.get("type") == "tool_result" and block.get("is_error"):
                    content = block.get("content")
                    if isinstance(content, list):
                        content = " ".join(c.get("text", "") for c in content if isinstance(c, dict))
                    self._emit({"type": "tool", "text": "That step failed: " + _short(content, 200)})
        elif t == "result":
            if not self._stopping and (msg.get("is_error") or msg.get("subtype") not in (None, "success")):
                self._emit({"type": "notice", "text": "The turn ended with an error: "
                            + _short(msg.get("result") or msg.get("subtype"), 300)})
            self._set_working(False)
            self._save()

    # ---- actions from the page -----------------------------------------------------------
    async def send(self, text: str):
        async with self.lock:
            self.last_activity = time.time()
            if not self.alive():
                await self._start()
            self._emit({"type": "you", "text": text})
            self._set_working(True)
            await self._write({"type": "user", "message": {"role": "user", "content": [{"type": "text", "text": text}]}})
            self._save()

    async def stop(self):
        """Interrupt the current turn. The session stays; if it does not stop in time, the
        process is closed and the next message resumes the conversation."""
        if not self.alive():
            self._set_working(False)
            return
        self._stopping = True
        try:
            await self._write({"type": "control_request", "request_id": f"stop-{int(time.time()*1000)}",
                               "request": {"subtype": "interrupt"}})
        except Exception:
            pass
        for _ in range(STOP_GRACE * 4):
            if not self.working or not self.alive():
                break
            await asyncio.sleep(0.25)
        if self.working and self.alive():
            await self._kill()
        self._stopping = False
        self._set_working(False)
        self._emit({"type": "notice", "text": "Stopped."})
        self._save()

    async def new_session(self):
        await self._kill()
        self.session_id = None
        self.history = []
        self._set_working(False)
        self._save()
        self._emit({"type": "notice", "text": "Started a new, empty session."})

    async def _kill(self):
        proc = self.proc
        if not proc or proc.returncode is not None:
            return
        try:
            proc.stdin.close()
        except Exception:
            pass
        try:
            await asyncio.wait_for(proc.wait(), 3)
        except asyncio.TimeoutError:
            try:
                proc.kill()
            except ProcessLookupError:
                pass
            await proc.wait()

    async def close_if_idle(self):
        if self.alive() and not self.working and not self.listeners and time.time() - self.last_activity > IDLE_LIMIT:
            audit("process_idle_closed", self.key)
            await self._kill()


_SESSIONS = {}
_reaper = None


def get(key: str = "owner") -> DirectSession:
    global _reaper
    if key not in _SESSIONS:
        _SESSIONS[key] = DirectSession(key)
    if _reaper is None or _reaper.done():
        _reaper = asyncio.create_task(_reap())
    return _SESSIONS[key]


async def _reap():
    while True:
        await asyncio.sleep(300)
        for s in list(_SESSIONS.values()):
            try:
                await s.close_if_idle()
            except Exception:
                pass
