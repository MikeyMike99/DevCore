"""Tier 1 release-readiness & zero-loss browser-exit card recording recovery tests."""
import asyncio
import json
import os
import re
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
def tier1_env(monkeypatch, tmp_path):
    # The learner sandbox must stay in the real folder (course_jail.sh refuses anything else), but the
    # verification codes and their per-email rate limit are kept in a temporary folder, so repeated runs
    # never hit "too many emails" and leave nothing behind.
    sandboxes_dir = ROOT / "playground" / ".course_sandboxes"
    sandboxes_dir.mkdir(parents=True, exist_ok=True)
    from core import course_enrolment as enrol
    enrol_root = tmp_path / "enrolment_state"
    enrol_root.mkdir(parents=True, exist_ok=True)
    real_load, real_save = enrol._load, enrol._save
    monkeypatch.setattr(enrol, "_load", lambda root, name: real_load(str(enrol_root), name))
    monkeypatch.setattr(enrol, "_save", lambda root, name, data: real_save(str(enrol_root), name, data))
    test_key = f"tier1test_{os.getpid()}"
    certs_dir = tmp_path / "course_certs"
    certs_dir.mkdir(parents=True, exist_ok=True)
    mailbox_file = tmp_path / "mailbox.json"
    logs_dir = tmp_path / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(proj_mod, "_course_learner_key", lambda: test_key)
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

    try:
        yield {
            "tmp_path": tmp_path,
            "mailbox_file": mailbox_file,
            "logs_dir": logs_dir,
            "box_dir": sandboxes_dir / test_key,
        }
    finally:
        import shutil
        shutil.rmtree(sandboxes_dir / test_key, ignore_errors=True)


def test_tier1_jailed_bicep_checkov_and_recorder_chunk_recovery(tier1_env):
    async def _run():
        client = app.test_client()

        r_out = await client.get("/api/course/data?course=alp_phase2_bicep_course")
        assert r_out.status_code == 200
        d_out = await r_out.get_json()
        assert d_out["limited"] is True
        assert d_out["super_admin"] is False

        r_terms = await client.post("/api/course/terms", json={
            "course_id": "alp_phase2_bicep_course",
            "agree": True,
            "version": proj_mod.COURSE_TERMS_VERSION,
        })
        assert r_terms.status_code == 200

        r_reg = await client.post("/api/course/register", json={
            "course_id": "alp_phase2_bicep_course",
            "full_name": "Thabo Mokoena",
            "email": "thabo@example.org",
            "organization": "SolarGrid SA",
            "confirm_certificate": True,
        })
        assert r_reg.status_code == 200
        reg_json = await r_reg.get_json()
        assert reg_json["verification"]["required"] is True

        mailbox = json.loads(tier1_env["mailbox_file"].read_text(encoding="utf-8"))
        m_code = re.search(r"\b(\d{6})\b", mailbox[0]["text"])
        assert m_code, f"No 6-digit verification code found in {mailbox[0]}"
        code = m_code.group(1)

        r_code = await client.post("/api/course/verification/code", json={
            "course_id": "alp_phase2_bicep_course",
            "code": code,
        })
        assert r_code.status_code == 200
        assert (await r_code.get_json())["verified"] is True

        r_full = await client.get("/api/course/data?course=alp_phase2_bicep_course")
        d_full = await r_full.get_json()
        assert not d_full.get("limited")
        assert len(d_full["course"]["modules"]) >= 7  # the course can grow

        # Sequential lock prevents jumping ahead; skip m0_t_bash and m0_t_python, then run m0_t_bicep in course_jail.sh
        r_early = await client.post("/api/course/execute", json={
            "course_id": "alp_phase2_bicep_course",
            "step_id": "m0_t_bicep",
            "recording_name": "mod0_setup",
            "command": "bicep --version",
            "prediction": "Bicep CLI prints its installed semantic version inside the jailed sandbox.",
        })
        assert r_early.status_code == 403

        for sid_skip in ("m0_t_bash", "m0_t_python"):
            r_sk = await client.post("/api/course/execute", json={
                "action": "skip",
                "course_id": "alp_phase2_bicep_course",
                "step_id": sid_skip,
            })
            assert r_sk.status_code == 200

        r_bicep = await client.post("/api/course/execute", json={
            "course_id": "alp_phase2_bicep_course",
            "step_id": "m0_t_bicep",
            "recording_name": "mod0_setup",
            "command": "bicep --version",
            "prediction": "Bicep CLI prints its installed semantic version inside the jailed sandbox.",
        })
        bicep_json = await r_bicep.get_json()
        assert r_bicep.status_code == 200, bicep_json
        assert bicep_json["ok"] is True, bicep_json["output"]
        assert "Bicep CLI version" in bicep_json["output"]

        # Test recorder chunk upload + beacon finalize + server recovery + download + discard
        sid = "rec_tier1_test_001"
        r_c0 = await client.post(
            f"/api/course/recorder-chunk?session_id={sid}&seq=0&mime_type=video/webm&card_id=course-response-card&course_id=alp_phase2_bicep_course",
            data=b"WEBM_HEADER_BYTES",
            headers={"Content-Type": "application/octet-stream"},
        )
        assert r_c0.status_code == 200
        assert (await r_c0.get_json())["byte_count"] == 17

        beacon_body = json.dumps({
            "session_id": sid,
            "status": "interrupted",
            "card_id": "course-response-card",
            "course_id": "alp_phase2_bicep_course",
            "title": "Azure Bicep Course",
            "learner": "Thabo Mokoena",
            "mime_type": "video/webm",
            "transcript": "Captured line 1",
            "logs": [{"state": "recording"}, {"state": "interrupted"}],
        })
        r_fin = await client.post(
            "/api/course/recorder-finalize",
            data=beacon_body,
            headers={"Content-Type": "text/plain;charset=UTF-8"},
        )
        assert r_fin.status_code == 200
        assert (await r_fin.get_json())["session"]["status"] == "interrupted"

        r_rec = await client.get("/api/course/recorder-recover?course_id=alp_phase2_bicep_course&card_id=course-response-card")
        assert r_rec.status_code == 200
        rec_data = await r_rec.get_json()
        assert rec_data["session"] and rec_data["session"]["session_id"] == sid

        r_dl = await client.get(rec_data["session"]["download_html_url"])
        assert r_dl.status_code == 200
        html_bytes = await r_dl.get_data()
        assert b"Standalone Offline Playback" in html_bytes
        assert b"Captured line 1" in html_bytes

        r_dis = await client.post("/api/course/recorder-discard", json={"session_id": sid, "remove": True})
        assert r_dis.status_code == 200
        r_rec2 = await client.get("/api/course/recorder-recover?course_id=alp_phase2_bicep_course&card_id=course-response-card")
        assert (await r_rec2.get_json())["session"] is None

    asyncio.run(_run())


def test_playwright_recording_survives_tab_close_without_stopping(rendering_browser, tier1_env):
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
    assert loop_ready.wait(timeout=10)
    base_url = f"http://127.0.0.1:{port}"

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(viewport={"width": 1280, "height": 900}, accept_downloads=True)
            page = context.new_page()

            # Tier 1 onboarding: Welcome -> Terms -> Register -> Verify Email Code
            page.goto(f"{base_url}/course", wait_until="domcontentloaded")
            page.wait_for_selector("#course-welcome-gate:not(.hidden)", timeout=10000)
            page.click("#welcome-start-btn")
            page.wait_for_selector("#course-terms-gate:not(.hidden)", timeout=10000)
            page.click("#terms-agree-checkbox")
            page.click("#accept-terms-btn")
            page.wait_for_selector("#course-registration-gate:not(.hidden)", timeout=10000)

            page.fill("#reg-full-name", "Nomsa Khumalo")
            page.fill("#reg-email", "nomsa@example.org")
            page.fill("#reg-org", "Cape Solar Grid")
            page.click("#reg-confirm-checkbox")
            page.click("#submit-registration-btn")
            page.wait_for_selector("#course-verify-gate:not(.hidden)", timeout=10000)

            mailbox = json.loads(tier1_env["mailbox_file"].read_text(encoding="utf-8"))
            code = re.search(r"\b(\d{6})\b", mailbox[0]["text"]).group(1)
            page.fill("#verify-code", code)
            page.click("#verify-code-btn")
            page.wait_for_function("() => !document.getElementById('verify-next-btn').disabled", timeout=10000)
            page.click("#verify-next-btn")
            page.wait_for_selector("#course-curriculum-stage:not(.hidden)", timeout=10000)

            # Start recording 1080p card, let chunks persist, then close tab abruptly WITHOUT clicking Stop
            page.wait_for_selector('#course-response-card [data-recorder-action="record"]', timeout=10000)
            page.click('#course-response-card [data-recorder-action="record"]')
            page.wait_for_function(
                "() => document.getElementById('course-response-card')?.getAttribute('data-recorder-state') === 'recording'",
                timeout=5000,
            )
            page.wait_for_timeout(1400)

            # Force-close the tab mid-recording without clicking Stop
            page.close(run_before_unload=False)

            # Reopen /course in a new tab: recovery must restore Preview & Standalone Download automatically
            page2 = context.new_page()
            page2.goto(f"{base_url}/course", wait_until="domcontentloaded")
            page2.wait_for_selector('[data-recorder-recovery-banner]:not(.hidden)', timeout=10000)
            assert page2.locator('#course-response-card').get_attribute('data-recorder-state') == 'recovered'

            page2.click('#course-response-card [data-recorder-action="preview"]')
            page2.wait_for_function(
                "() => { const v = document.querySelector('#course-response-card [data-recorder-preview-video]'); return v && v.videoWidth === 1920 && v.videoHeight === 1080; }",
                timeout=10000,
            )

            with page2.expect_download(timeout=10000) as dl_info:
                page2.click('#course-response-card [data-recorder-action="download"]')
            dl = dl_info.value
            saved_path = tier1_env["tmp_path"] / dl.suggested_filename
            dl.save_as(str(saved_path))
            html_txt = saved_path.read_text(encoding="utf-8")
            assert "Standalone Offline Recording" in html_txt
            assert "http://" not in html_txt and "https://" not in html_txt

            context.close()
            browser.close()
    finally:
        if "loop" in server_holder and "shutdown_ev" in server_holder:
            server_holder["loop"].call_soon_threadsafe(server_holder["shutdown_ev"].set)
        th.join(timeout=5)
