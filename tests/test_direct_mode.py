"""Tests for Direct mode (agents/direct_session.py and the /direct, /api/direct/status and
/ws/direct routes in core/server.py). A fake `claude` stands in for the real CLI.

Run (WSL):  cd core && ~/.venvs/devcore/bin/python -m pytest -q ../tests/test_direct_mode.py
"""
import asyncio
import json
import os
import sys
import textwrap

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "core"))

FAKE_CLAUDE = textwrap.dedent(r'''
    import json, sys, threading, time, os
    log = os.environ["FAKE_CLAUDE_ARGS"]
    with open(log, "a") as f: f.write(json.dumps(sys.argv[1:]) + "\n")
    sid = "fake-session-1"
    if "--resume" in sys.argv: sid = sys.argv[sys.argv.index("--resume") + 1]
    stop = threading.Event()
    def out(o): sys.stdout.write(json.dumps(o) + "\n"); sys.stdout.flush()
    def turn(text):
        out({"type": "system", "subtype": "init", "session_id": sid})
        out({"type": "assistant", "session_id": sid, "message": {"content": [
            {"type": "tool_use", "name": "Bash", "input": {"command": "ls", "description": "List files"}}]}})
        if "slow" in text:
            stop.clear()
            if not stop.wait(20):
                pass
            out({"type": "result", "subtype": "error_during_execution", "is_error": True, "session_id": sid})
            return
        out({"type": "assistant", "session_id": sid, "message": {"content": [{"type": "text", "text": "echo: " + text}]}})
        out({"type": "result", "subtype": "success", "is_error": False, "session_id": sid, "result": "echo: " + text})
    for line in sys.stdin:
        m = json.loads(line)
        if m["type"] == "user":
            threading.Thread(target=turn, args=(m["message"]["content"][0]["text"],), daemon=True).start()
        elif m["type"] == "control_request":
            stop.set()
            out({"type": "control_response", "response": {"subtype": "success", "request_id": m["request_id"]}})
''')


@pytest.fixture
def fake(tmp_path, monkeypatch):
    from agents import direct_session as ds
    script = tmp_path / "fake_claude.py"
    script.write_text(FAKE_CLAUDE)
    args_log = tmp_path / "args.jsonl"
    monkeypatch.setenv("FAKE_CLAUDE_ARGS", str(args_log))
    monkeypatch.setattr(ds, "_claude_command", lambda: [sys.executable, str(script)])
    monkeypatch.setattr(ds, "STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setattr(ds, "AUDIT_FILE", str(tmp_path / "audit.jsonl"))
    monkeypatch.setattr(ds, "_SESSIONS", {})
    monkeypatch.setattr(ds, "_reaper", None)
    return ds, args_log, tmp_path


async def _until(q, pred, timeout=10):
    seen = []
    async def run():
        while True:
            ev = await q.get()
            seen.append(ev)
            if pred(ev):
                return ev
    await asyncio.wait_for(run(), timeout)
    return seen


def test_session_stays_alive_and_resumes(fake):
    ds, args_log, _ = fake

    async def go():
        s = ds.DirectSession("owner")
        q = s.subscribe()
        await s.send("hello")
        seen = await _until(q, lambda e: e.get("type") == "status" and e["state"] == "finished")
        texts = [e.get("text") for e in seen]
        assert "Running a command: List files" in texts
        assert "echo: hello" in texts
        pid = s.proc.pid
        await s.send("again")
        await _until(q, lambda e: e.get("type") == "reply" and e["text"] == "echo: again")
        assert s.proc.pid == pid, "one process for the whole conversation"
        assert s.session_id == "fake-session-1"
        await s._kill()
        # A new object (as after a server restart) resumes the saved session and history.
        s2 = ds.DirectSession("owner")
        assert s2.session_id == "fake-session-1"
        assert any(e.get("text") == "echo: hello" for e in s2.history)
        q2 = s2.subscribe()
        await s2.send("after restart")
        await _until(q2, lambda e: e.get("type") == "reply")
        await s2._kill()
        runs = [json.loads(l) for l in args_log.read_text().splitlines()]
        assert "--resume" not in runs[0] and "--dangerously-skip-permissions" in runs[0]
        assert runs[1][runs[1].index("--resume") + 1] == "fake-session-1"
    asyncio.run(go())


def test_stop_interrupts_but_keeps_session(fake):
    ds, _, _ = fake

    async def go():
        s = ds.DirectSession("owner")
        q = s.subscribe()
        await s.send("do something slow")
        await _until(q, lambda e: e.get("type") == "tool")
        assert s.working
        pid = s.proc.pid
        await s.stop()
        assert not s.working
        assert s.alive() and s.proc.pid == pid
        assert not any("ended with an error" in (e.get("text") or "") for e in s.history)
        await s.send("next")
        await _until(q, lambda e: e.get("type") == "reply" and e["text"] == "echo: next")
        await s.new_session()
        assert s.session_id is None and not s.alive()
    asyncio.run(go())


# ---- routes ---------------------------------------------------------------------------------
@pytest.fixture
def app(fake, monkeypatch):
    import server
    users = {"owner-token": {"username": "Michael (Admin)", "role": "super_admin", "key_id": "owner"},
             "admin-token": {"username": "projadmin", "role": "admin"},
             "tier3-token": {"username": "dev", "role": "developer"}}
    monkeypatch.setattr(server.security_mgr, "get_user_from_token",
                        lambda tok, remote_addr=None, headers=None: dict(users[tok]) if tok in users else None)
    monkeypatch.setattr(server.security_mgr, "check_master_signature", lambda: True)
    server._test_users = users
    return server


ORIGIN = {"Origin": "http://localhost", "Host": "localhost"}


def _status(server, tok):
    async def go():
        c = server.app.test_client()
        r = await c.get("/api/direct/status", headers={"Authorization": "Bearer " + tok} if tok else {})
        return r.status_code
    return asyncio.run(go())


def test_status_only_for_super_admin(app):
    assert _status(app, "owner-token") == 200
    for tok in ("admin-token", "tier3-token", "", "junk"):
        assert _status(app, tok) == 403


def test_page_has_no_data_and_is_noindex(app):
    async def go():
        r = await app.app.test_client().get("/direct")
        assert r.status_code == 200
        assert "noindex" in r.headers.get("X-Robots-Tag", "")
        body = await r.get_data(as_text=True)
        assert 'aria-live="polite"' in body and "<table" not in body
    asyncio.run(go())


async def _ws_frames(server, first, headers=ORIGIN, then=None, n=1):
    c = server.app.test_client()
    frames = []
    async with c.websocket("/ws/direct", headers=headers) as ws:
        await ws.send(json.dumps(first))
        try:
            frames.append(json.loads(await asyncio.wait_for(ws.receive(), 5)))
            for msg in (then or []):
                await ws.send(json.dumps(msg))
            while len(frames) < n:
                frames.append(json.loads(await asyncio.wait_for(ws.receive(), 10)))
        except Exception:
            pass
    return frames


@pytest.mark.parametrize("tok", ["admin-token", "tier3-token", "", "junk"])
def test_ws_refuses_everyone_but_owner(app, tok):
    frames = asyncio.run(_ws_frames(app, {"type": "auth", "token": tok}))
    assert frames and frames[0]["type"] == "denied"


def test_ws_refuses_other_websites(app):
    frames = asyncio.run(_ws_frames(app, {"type": "auth", "token": "owner-token"},
                                    headers={"Origin": "https://evil.example", "Host": "localhost"}))
    assert frames and frames[0]["type"] == "denied"


def test_ws_owner_chat_and_access_lost(app):
    async def go():
        c = app.app.test_client()
        async with c.websocket("/ws/direct", headers=ORIGIN) as ws:
            await ws.send(json.dumps({"type": "auth", "token": "owner-token"}))
            assert json.loads(await ws.receive())["type"] == "history"
            await ws.send(json.dumps({"type": "send", "text": "hi"}))
            got = []
            while not any(f.get("type") == "status" and f.get("state") == "finished" for f in got):
                got.append(json.loads(await asyncio.wait_for(ws.receive(), 10)))
            assert any(f.get("text") == "echo: hi" for f in got)
            # Owner rights removed while connected: the next frame is refused and the socket closed.
            app._test_users.pop("owner-token")
            await ws.send(json.dumps({"type": "send", "text": "should not run"}))
            f = json.loads(await asyncio.wait_for(ws.receive(), 5))
            assert f["type"] == "denied"
        from agents import direct_session as ds
        s = ds.get("owner")
        assert not any(e.get("text") == "should not run" for e in s.history)
        await s._kill()
        audit = [json.loads(l)["event"] for l in open(ds.AUDIT_FILE)]
        assert "connected" in audit and "message" in audit and "refused" in audit
    asyncio.run(go())
