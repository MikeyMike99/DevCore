"""End-to-end Playwright accessibility, MediaRecorder (1080p/30fps), offline HTML, and certificate tests."""
import asyncio
import json
import os
import socket
import sys
import threading
from pathlib import Path

import pytest
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core import course_certificate  # noqa: E402
from core.routes import projects as proj_mod  # noqa: E402
from core.server import app  # noqa: E402


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture()
def live_test_server(monkeypatch, tmp_path):
    sandboxes_dir = tmp_path / "course_sandboxes"
    certs_dir = tmp_path / "course_certs"
    certs_dir.mkdir(parents=True, exist_ok=True)
    mailbox_file = tmp_path / "mailbox.json"
    logs_dir = tmp_path / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(proj_mod, "COURSE_SANDBOXES_ROOT", str(sandboxes_dir))
    monkeypatch.setattr(proj_mod, "_course_learner_key", lambda: "pwlearner001")
    monkeypatch.setattr(proj_mod, "_course_repo_root", lambda: str(tmp_path))

    tmp_sandbox = tmp_path / "sandbox"
    tmp_sandbox.mkdir(parents=True, exist_ok=True)
    os.symlink(str(ROOT / "sandbox" / "static"), str(tmp_sandbox / "static"))
    os.symlink(str(ROOT / "sandbox" / "templates"), str(tmp_sandbox / "templates"))

    monkeypatch.setattr(course_certificate, "certs_root", lambda: str(certs_dir))

    from services.mail import config as mail_cfg_mod
    monkeypatch.setattr(mail_cfg_mod.config, "MAILBOX_FILE", mailbox_file)
    monkeypatch.setattr(mail_cfg_mod.config, "MAIL_BACKEND", "local")
    app.config["TESTING"] = True

    port = _free_port()
    loop_ready = threading.Event()
    server_holder = {}

    def _run_server():
        from hypercorn.asyncio import serve
        from hypercorn.config import Config

        cfg = Config()
        cfg.bind = [f"127.0.0.1:{port}"]
        cfg.loglevel = "WARNING"

        async def _runner():
            shutdown_ev = asyncio.Event()
            server_holder["loop"] = asyncio.get_running_loop()
            server_holder["shutdown_ev"] = shutdown_ev
            loop_ready.set()
            await serve(app, cfg, shutdown_trigger=shutdown_ev.wait)

        asyncio.run(_runner())

    th = threading.Thread(target=_run_server, daemon=True)
    th.start()
    assert loop_ready.wait(timeout=10), "Test server failed to start"

    try:
        yield {
            "url": f"http://127.0.0.1:{port}",
            "tmp_path": tmp_path,
            "mailbox_file": mailbox_file,
            "logs_dir": logs_dir,
        }
    finally:
        if "loop" in server_holder and "shutdown_ev" in server_holder:
            server_holder["loop"].call_soon_threadsafe(server_holder["shutdown_ev"].set)
        th.join(timeout=5)


def test_playwright_accessibility_isolation_1080p_offline_and_certificate(rendering_browser, live_test_server):
    base_url = live_test_server["url"]
    tmp_path = live_test_server["tmp_path"]

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1280, "height": 900}, accept_downloads=True)
        page = context.new_page()

        # ------------------------------------------------------------------
        # Part 1: Main UI (index.html) Response Card Isolation + 1080p Recording + In-Card Preview
        # ------------------------------------------------------------------
        page.goto(f"{base_url}/", wait_until="domcontentloaded")
        page.wait_for_selector("#terms-dialog[open]", timeout=10000)

        ax_site_terms = page.locator("#terms-dialog").aria_snapshot()
        assert "Before you start" in ax_site_terms
        page.check("#terms-agree")
        with page.expect_navigation():
            page.click("#terms-continue")
        page.wait_for_selector("#prompt", timeout=10000)
        page.wait_for_function("() => Boolean(window.SirauggaCardRecorder)", timeout=10000)

        # Open Course response card + second card so multiple cards exist in feed before isolation
        page.evaluate("""async () => {
            await openBackendCard({ topic: 'privacy' });
            await openBackendCard({ topic: 'course' });
        }""")
        page.wait_for_selector('article[data-backend-card="course"]', timeout=10000)
        course_card = page.locator('article[data-backend-card="course"]')
        course_card.locator('[data-recorder-action="isolate"]').wait_for(state="visible", timeout=5000)

        # Isolate active response card and audit Accessibility Tree via CDP & aria_snapshot
        course_card.locator('[data-recorder-action="isolate"]').click()
        assert page.locator('article[data-card-isolated="true"]').count() == 1
        assert page.locator('#chat-form').evaluate("el => Boolean(el.closest('[aria-hidden=\"true\"]'))") is True
        assert page.locator('#prompt').is_visible() is False

        cdp = context.new_cdp_session(page)
        ax_tree = cdp.send("Accessibility.getFullAXTree")
        cdp.detach()
        ax_names = [
            str((n.get("name") or {}).get("value") or "")
            for n in ax_tree.get("nodes", [])
            if not n.get("ignored")
        ]
        assert any("Isolate" in nm or "Exit Isolation" in nm for nm in ax_names)
        assert not any(nm == "Send prompt" for nm in ax_names), "Background prompt form leaked into isolated accessibility tree"

        # Record isolated card at 1080p @ 30fps via MediaRecorder
        course_card.locator('[data-recorder-action="record"]').click()
        page.wait_for_function(
            "() => document.querySelector('article[data-backend-card=\"course\"]')?.getAttribute('data-recorder-state') === 'recording'",
            timeout=5000,
        )
        page.wait_for_timeout(1600)
        course_card.locator('[data-recorder-action="stop"]').click()
        page.wait_for_function(
            "() => document.querySelector('article[data-backend-card=\"course\"]')?.getAttribute('data-recorder-state') === 'preview_ready'",
            timeout=10000,
        )

        # Verify in-card preview BEFORE downloading
        course_card.locator('[data-recorder-action="preview"]').click()
        preview_vid = course_card.locator('[data-recorder-preview-video]')
        preview_vid.wait_for(state="visible", timeout=5000)
        try:
            page.wait_for_function(
                "() => { const v = document.querySelector('article[data-backend-card=\"course\"] [data-recorder-preview-video]'); return v && v.videoWidth === 1920 && v.videoHeight === 1080; }",
                timeout=10000,
            )
        except Exception:
            diag = page.evaluate("""() => {
                const v = document.querySelector('article[data-backend-card="course"] [data-recorder-preview-video]');
                return { src: v?.src, w: v?.videoWidth, h: v?.videoHeight, rs: v?.readyState, err: v?.error?.message, logs: window.SirauggaCardRecorder.getLogs() };
            }""")
            raise AssertionError(f"Preview video did not reach 1920x1080: {diag}")
        dims = preview_vid.evaluate("v => ({ w: v.videoWidth, h: v.videoHeight })")
        assert dims == {"w": 1920, "h": 1080}

        # Download standalone offline HTML recording and verify offline playback with network disabled
        with page.expect_download() as dl_info:
            course_card.locator('[data-recorder-action="download"]').click()
        dl = dl_info.value
        standalone_path = tmp_path / dl.suggested_filename
        dl.save_as(str(standalone_path))
        standalone_html = standalone_path.read_text(encoding="utf-8")
        assert "http://" not in standalone_html and "https://" not in standalone_html

        logs_now = page.evaluate("() => window.SirauggaCardRecorder.getLogs().map(l => l.state)")
        for required_state in ("recording", "rendering", "preview_ready", "saving", "saved"):
            assert required_state in logs_now

        # Open downloaded standalone HTML offline with zero network connectivity
        offline_ctx = browser.new_context(offline=True)
        offline_page = offline_ctx.new_page()
        offline_requests = []
        offline_page.on("request", lambda req: offline_requests.append(req.url) if not req.url.startswith(("file://", "blob:", "data:")) else None)
        offline_page.goto(standalone_path.as_uri(), wait_until="domcontentloaded")
        offline_page.wait_for_function(
            "() => { const v = document.getElementById('offline-video'); return v && v.videoWidth === 1920 && v.videoHeight === 1080; }",
            timeout=10000,
        )
        assert offline_requests == [], f"Standalone HTML attempted external requests: {offline_requests}"
        ax_offline = offline_page.locator("main").aria_snapshot()
        assert "MediaRecorder State Transition Log" in ax_offline
        offline_ctx.close()

        # ------------------------------------------------------------------
        # Part 2: /course Gate Flow (Terms -> Registration -> Survey -> Certificate + Auto-Download)
        # ------------------------------------------------------------------
        course_page = context.new_page()
        course_page.goto(f"{base_url}/course", wait_until="domcontentloaded")
        course_page.wait_for_selector("#course-welcome-gate:not(.hidden)", timeout=10000)
        course_page.click("#welcome-start-btn")
        course_page.wait_for_selector("#course-terms-gate:not(.hidden)", timeout=10000)

        # Accessibility check: only Terms gate visible, Registration & Curriculum hidden from AXTree
        ax_terms = course_page.locator("#course-terms-gate").aria_snapshot()
        assert "Mandatory Terms & Privacy Agreement" in ax_terms
        assert course_page.locator("#course-registration-gate").get_attribute("aria-hidden") == "true"
        assert course_page.locator("#course-curriculum-stage").get_attribute("aria-hidden") == "true"

        # Validation error announced on unchecked terms
        course_page.click("#accept-terms-btn")
        assert "alert" in course_page.locator("#terms-gate-error").get_attribute("role")

        course_page.check("#terms-agree-checkbox")
        course_page.click("#accept-terms-btn")
        course_page.wait_for_selector("#course-registration-gate:not(.hidden)", timeout=10000)

        # User Registration accessibility & submission
        ax_reg = course_page.locator("#course-registration-gate").aria_snapshot()
        assert "Full Name" in ax_reg
        assert "Email Address" in ax_reg

        course_page.fill("#reg-full-name", "Grace Hopper")
        course_page.fill("#reg-email", "grace.hopper@example.org")
        course_page.fill("#reg-org", "Compiler Security Lab")
        course_page.check("#reg-confirm-checkbox")
        course_page.click("#submit-registration-btn")
        # Learners confirm their email: read the 6-digit code from the verification email and type it in.
        course_page.wait_for_selector("#course-verify-gate:not(.hidden)", timeout=10000)
        import re as _re
        mail_path = live_test_server["mailbox_file"]
        code = None
        for _ in range(40):
            if mail_path.is_file():
                try:
                    box = json.loads(mail_path.read_text(encoding="utf-8"))
                except Exception:
                    box = []
                for m in box:
                    found = _re.search(r"\b(\d{6})\b", str(m.get("text", "")))
                    if found and m.get("to") == "grace.hopper@example.org":
                        code = found.group(1)
            if code:
                break
            course_page.wait_for_timeout(250)
        assert code, "Verification email with a 6-digit code was not delivered"
        course_page.fill("#verify-code", code)
        course_page.click("#verify-code-btn")
        course_page.wait_for_function("() => !document.getElementById('verify-next-btn').disabled", timeout=10000)
        course_page.click("#verify-next-btn")
        course_page.wait_for_selector("#course-curriculum-stage:not(.hidden)", timeout=10000)

        # Verify course sections finished unlock End-of-Course Survey
        course_obj, prog = proj_mod._load_course_and_progress("alp_phase2_bicep_course")
        sections = proj_mod._ordered_sections(course_obj)
        prog["completed_steps"] = [sec["id"] for _, sec in sections]
        prog["reflections"] = {
            sec["id"]: {"reflection_done": True, "explain": "Verified section reflection in Playwright E2E."}
            for _, sec in sections
        }
        proj_mod._save_progress_sync("alp_phase2_bicep_course", prog)

        course_page.reload(wait_until="domcontentloaded")
        course_page.wait_for_selector("#course-survey-section:not(.hidden)", timeout=10000)
        ax_survey = course_page.locator("#course-survey-section").aria_snapshot()
        assert "End-of-Course Survey & Certificate Issuance" in ax_survey

        # Start recording on the course card, then complete survey -> auto-triggers standalone download & certificate
        course_page.click('#course-response-card [data-recorder-action="record"]')
        course_page.wait_for_function(
            "() => document.getElementById('course-response-card')?.getAttribute('data-recorder-state') === 'recording'",
            timeout=5000,
        )
        course_page.wait_for_timeout(1200)
        course_page.fill("#survey-feedback", "Verified accessibility and automated 1080p recording export.")

        with course_page.expect_download(timeout=15000) as auto_dl_info:
            course_page.click("#submit-survey-btn")
        auto_dl = auto_dl_info.value
        assert auto_dl.suggested_filename.endswith(".html")

        course_page.wait_for_selector("#certificate-issued-panel:not(.hidden)", timeout=10000)
        course_page.click("#verify-cert-btn")
        course_page.wait_for_function(
            "() => (document.getElementById('verify-cert-status')?.textContent || '').includes('Verified')",
            timeout=10000,
        )
        assert "PDF PKCS#7 ByteRange Valid: true" in course_page.locator("#verify-cert-status").inner_text()

        # Verify backend recorded MediaRecorder logs & emailed certificate
        event_log = live_test_server["logs_dir"] / "media_recorder_events.jsonl"
        assert event_log.is_file()
        states_on_disk = {json.loads(ln)["state"] for ln in event_log.read_text(encoding="utf-8").splitlines() if ln.strip()}
        assert {"recording", "rendering", "saving", "saved"}.issubset(states_on_disk)

        mailbox = json.loads(live_test_server["mailbox_file"].read_text(encoding="utf-8"))
        assert len(mailbox) == 2  # one verification email, one signed certificate email
        assert all(m["to"] == "grace.hopper@example.org" for m in mailbox)
        assert len([m for m in mailbox if m.get("attachments")]) == 1

        context.close()
        browser.close()


def test_playwright_course_preview_flag_is_ignored(live_test_server):
    """There is no preview mode: ?preview=1 shows the normal Welcome step and no preview banner."""
    base_url = live_test_server["url"]

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1280, "height": 900})
        page = context.new_page()
        page.goto(f"{base_url}/course?preview=1", wait_until="domcontentloaded")
        page.wait_for_selector("#course-welcome-gate:not(.hidden)", timeout=10000)
        assert page.locator("#course-preview-banner").is_visible() is False
        assert page.locator("#course-response-card").get_attribute("data-preview-mode") != "true"
        assert page.locator("#course-curriculum-stage").get_attribute("aria-hidden") == "true"
        context.close()
        browser.close()


def test_playwright_cross_references_and_cyberbrief_advert_render(live_test_server):
    """Feeds sample data to the real course page (no clicks needed) and checks what it draws:
    plain-text cross references, the end-of-course lists, and a CyberBrief advert that is not shown on every module."""
    base_url = live_test_server["url"]
    setup = """
    () => {
      const mk = (n) => ({ module_number: n, title: 'Module ' + n, closing_summary: 'Done ' + n, summary_bullets: ['a'],
                           see_also: n === 2 ? [{course_id: 'cybersecurity_revision', note: 'Module 3: hardening'}] : [] });
      const mods = [1, 2, 3, 4, 5, 6].map(mk);
      courseData = { course_id: 'x', modules: mods, theme: 'teal',
        _extras: {
          related_titles: ['Cybersecurity Fundamentals Revision Course', 'Networking Fundamentals Revision Course'],
          catalog_titles: { cybersecurity_revision: 'Cybersecurity Fundamentals Revision Course' },
          cyberbrief: { name: 'CyberBrief', blurb: 'CyberBrief is a free cyber threat-intelligence newsletter.', url: 'https://example.org/subscribe' } } };
      applyCourseBranding();
      const out = { adShown: [] };
      const end = document.getElementById('course-end-extras');
      out.related = Array.from(end.querySelectorAll('li')).map(l => l.textContent);
      out.links = Array.from(end.querySelectorAll('a')).map(a => [a.getAttribute('href'), a.target, a.rel]);
      out.endText = end.textContent;
      mods.forEach((m) => {
        flatSteps = [{ section: { id: 's', section_code: 'S', title: 't' }, moduleObj: m, isLastInModule: true,
                       moduleNumber: m.module_number, sectionIndex: 0, recordingName: 'r' }];
        currentStepIndex = 0;
        showStepOutput(true, 'ok', 'take', 'out', '', false);
        out.adShown.push(!document.getElementById('module-cyberbrief-line').classList.contains('hidden'));
        const sa = document.getElementById('see-also-box');
        if (m.module_number === 1) out.noteHiddenWhenNone = sa.classList.contains('hidden');
        if (m.module_number === 2) out.note = sa.textContent;
      });
      return out;
    }
    """
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_context().new_page()
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(f"{base_url}/course", wait_until="domcontentloaded")
        page.wait_for_selector("#course-end-extras", state="attached", timeout=10000)
        out = page.evaluate(setup)
        browser.close()

    assert errors == []
    assert out["related"] == ["Cybersecurity Fundamentals Revision Course", "Networking Fundamentals Revision Course"]
    assert "Check out these courses next" in out["endText"] and "Nothing is subscribed for you" in out["endText"]
    assert out["links"] and all(href == "https://example.org/subscribe" and target == "_blank" and "noopener" in rel
                                for href, target, rel in out["links"])
    # advert after the first module and then every fourth one, never on the last module
    assert out["adShown"] == [True, False, False, True, False, False]
    assert out["noteHiddenWhenNone"] is True
    assert out["note"] == "You will meet this again in: Cybersecurity Fundamentals Revision Course (Module 3: hardening)."
