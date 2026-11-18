"""End-to-end: the REAL Siraugga app + the REAL Lab Cloud (Worker + Docker containers) + a real browser.

Needs the lab stack running and the private settings file (created by `bash labcloud/setup.sh env`):
    bash labcloud/dev.sh                       # terminal 1 (WSL)
    python3 -m pytest tests/test_lab_cloud_course.py -v    # terminal 2 (WSL venv)
Skips itself (with a reason) when the stack is not running, so the normal test suite is unaffected.
"""
import os
import time
import urllib.error
import urllib.request
import json

import pytest

from core import lab_cloud
from core.routes import projects as proj_mod
from test_playwright_a11y_recording import live_test_server  # noqa: F401  (fixture: real app on a free port)

COURSE = "linux_essentials_step_by_step"
ENV_FILE = os.path.expanduser("~/.config/siraugga/lab_cloud.env")


def _settings():
    cfg = {}
    try:
        with open(ENV_FILE, encoding="utf-8") as f:
            for line in f:
                k, sep, v = line.strip().partition("=")
                if sep:
                    cfg[k] = v
    except OSError:
        pass
    return (os.environ.get("SIRAUGGA_LAB_URL") or cfg.get("SIRAUGGA_LAB_URL") or "http://127.0.0.1:8788",
            os.environ.get("SIRAUGGA_LAB_SECRET") or cfg.get("SIRAUGGA_LAB_SECRET") or "")


def _stack_up(url):
    try:
        urllib.request.urlopen(url + "/lab/info/x", timeout=3)
    except urllib.error.HTTPError as e:
        return e.code == 401
    except OSError:
        return False
    return False


LAB_URL, LAB_SECRET = _settings()
pytestmark = pytest.mark.skipif(not LAB_SECRET or not _stack_up(LAB_URL),
                                reason="Lab Cloud not running or no settings file (bash labcloud/setup.sh env; bash labcloud/dev.sh)")


@pytest.fixture(autouse=True)
def stay_the_test_learner(live_test_server):
    """The server re-imports core.routes.projects on its first request (core/session_manager.py hot-bind), which
    resets the test learner setup and would serve later requests as the OWNER (touching real owner data).
    Re-apply the setup continuously, exactly like tests/serve_course_for_browser.py."""
    import threading
    from core import course_certificate
    keep = {
        "COURSE_SANDBOXES_ROOT": proj_mod.COURSE_SANDBOXES_ROOT,
        "_course_learner_key": proj_mod._course_learner_key,
        "_course_repo_root": proj_mod._course_repo_root,
    }
    certs = course_certificate.certs_root
    stop = threading.Event()

    def loop():
        while not stop.is_set():
            for name, value in keep.items():
                setattr(proj_mod, name, value)
            course_certificate.certs_root = certs
            stop.wait(0.1)
    t = threading.Thread(target=loop, daemon=True)
    t.start()
    yield
    stop.set()
    t.join(timeout=2)


@pytest.fixture()
def lab_env(monkeypatch):
    monkeypatch.setenv("SIRAUGGA_LAB_URL", LAB_URL)
    monkeypatch.setenv("SIRAUGGA_LAB_SECRET", LAB_SECRET)


def _post(base, body):
    req = urllib.request.Request(base + "/api/course/execute", data=json.dumps(body).encode(), method="POST",
                                 headers={"Content-Type": "application/json"})
    deadline = time.time() + 20                       # the test server may need a moment before it listens
    while True:
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                return r.status, json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read().decode() or "{}")
        except urllib.error.URLError:
            if time.time() > deadline:
                raise
            time.sleep(0.5)


def _prepare_learner(target_step, accept=True):
    """Terms accepted, registered, and every section before `target_step` finished (so the step is unlocked)."""
    course_obj, prog = proj_mod._load_course_and_progress(COURSE)
    sections = [s for _, s in proj_mod._ordered_sections(course_obj)]
    ids = [s["id"] for s in sections]
    before = ids[:ids.index(target_step)]
    if accept:
        prog["terms_accepted"] = {"accepted": True, "version": proj_mod.COURSE_TERMS_VERSION}
        prog["registration"] = {"registered": True, "verified": True, "full_name": "Test Learner", "email": "t@example.com"}
    prog["completed_steps"] = before
    prog["reflections"] = {i: {"reflection_done": True, "explain": "Done in the test, with a reflection long enough."} for i in before}
    proj_mod._save_progress_sync(COURSE, prog)
    return next(s for s in sections if s["id"] == target_step)


def test_course_step_runs_in_the_learners_container(live_test_server, lab_env):
    sec = _prepare_learner("lx1_6")
    base = live_test_server["url"]
    status, res = _post(base, {
        "course_id": COURSE, "step_id": "lx1_6", "command": sec["expected_command"], "recording_name": sec["recording_name"],
        "prediction": "I expect the first lines to describe the Linux distribution name and version."})
    assert status == 200 and res["ok"], res
    assert res["progress"]["learner_name"] == "learner", "served as the OWNER, not the isolated test learner"
    # The old sandbox is the host's; a container shows Debian 12 from the lab image.
    assert "Debian" in res["output"], res["output"]
    assert "lx1_6" in res["progress"]["completed_steps"]


def test_live_terminal_endpoints(live_test_server, lab_env):
    _prepare_learner("lx1_6")
    base = live_test_server["url"]
    st, res = _post(base, {"action": "lab_status", "course_id": COURSE})
    assert st == 200 and res["available"] is True
    st, res = _post(base, {"action": "lab_status", "course_id": "alp_phase2_bicep_course"})
    assert res["available"] is False                              # only mapped courses get a terminal
    st, res = _post(base, {"action": "lab_terminal", "course_id": COURSE})
    assert st == 200 and res["ok"], res
    assert res["terminal_url"].startswith(LAB_URL + "/t/") and res["terminal_url"].endswith("/")
    assert "secret" not in json.dumps(res).lower()
    with urllib.request.urlopen(res["terminal_url"], timeout=60) as page:
        assert page.status == 200 and b"ttyd" in page.read().lower()
    st, res = _post(base, {"action": "lab_terminal", "course_id": "alp_phase2_bicep_course"})
    assert st == 404                                              # not offered for other courses


def test_live_terminal_needs_terms_and_registration(live_test_server, lab_env):
    _prepare_learner("lx1_6", accept=False)
    st, res = _post(live_test_server["url"], {"action": "lab_terminal", "course_id": COURSE})
    assert st == 403 and res["code"] in ("TERMS_REQUIRED", "REGISTRATION_REQUIRED")


def test_without_settings_nothing_changes(live_test_server, monkeypatch):
    monkeypatch.delenv("SIRAUGGA_LAB_URL", raising=False)
    monkeypatch.delenv("SIRAUGGA_LAB_SECRET", raising=False)
    _prepare_learner("lx1_6")
    base = live_test_server["url"]
    assert _post(base, {"action": "lab_status", "course_id": COURSE})[1]["available"] is False
    assert _post(base, {"action": "lab_terminal", "course_id": COURSE})[0] == 404


def test_browser_opens_the_live_terminal_and_types_into_it(rendering_browser, live_test_server, lab_env):
    from playwright.sync_api import sync_playwright
    _prepare_learner("lx1_6")
    learner = lab_cloud.learner_id(proj_mod._course_sandbox_dir(), True)
    base = live_test_server["url"]
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            page = browser.new_context().new_page()
            csp_problems = []
            page.on("console", lambda m: csp_problems.append(m.text) if "Content Security Policy" in m.text else None)
            page.goto(f"{base}/course?course={COURSE}", wait_until="domcontentloaded")
            btn = page.locator("#live-term-btn")
            btn.wait_for(state="visible", timeout=30000)
            assert btn.get_attribute("aria-expanded") == "false"
            btn.click()
            frame_el = page.locator("#live-term-frame")
            frame_el.wait_for(state="visible", timeout=90000)
            assert frame_el.get_attribute("src").startswith(LAB_URL + "/t/")
            term = page.frame_locator("#live-term-frame")
            term.locator(".xterm-helper-textarea").wait_for(state="attached", timeout=60000)
            term.locator(".xterm").click()
            page.keyboard.type("echo browser-typed-this > bt.txt\n", delay=30)
            deadline, seen = time.time() + 30, ""
            while time.time() < deadline and "browser-typed-this" not in seen:
                time.sleep(1)
                seen = lab_cloud.run_command(learner, "linux-essentials", "cat bt.txt 2>&1")[1]
            assert "browser-typed-this" in seen, "what the learner typed in the browser terminal never reached their container"
            assert not csp_problems, f"the page's security policy blocked something: {csp_problems[:2]}"
            btn.click()                                           # closes it again
            assert btn.get_attribute("aria-expanded") == "false"
            assert page.locator("#live-term-frame").count() == 0
        finally:
            browser.close()
