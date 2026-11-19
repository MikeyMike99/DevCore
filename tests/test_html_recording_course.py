"""API, cryptographic signing, and accessibility structure tests for the HTML recording & course flow."""
import asyncio
import hashlib
import io
import json
import os
import sys
from pathlib import Path

import pytest
from pypdf import PdfReader

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core import course_certificate  # noqa: E402
from core.routes import projects as proj_mod  # noqa: E402
from core.server import app  # noqa: E402
from scripts import build_siraugga_pages  # noqa: E402


@pytest.fixture()
def isolated_env(monkeypatch, tmp_path):
    sandboxes_dir = tmp_path / "course_sandboxes"
    certs_dir = tmp_path / "course_certs"
    certs_dir.mkdir(parents=True, exist_ok=True)
    mailbox_file = tmp_path / "mailbox.json"
    logs_dir = tmp_path / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(proj_mod, "COURSE_SANDBOXES_ROOT", str(sandboxes_dir))
    monkeypatch.setattr(proj_mod, "_course_learner_key", lambda: "testlearner001")
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
    return {
        "tmp_path": tmp_path,
        "sandboxes_dir": sandboxes_dir,
        "certs_dir": certs_dir,
        "mailbox_file": mailbox_file,
        "logs_dir": logs_dir,
    }


def test_full_course_gates_recording_logs_survey_and_signed_certificate(isolated_env):
    async def _run():
        client = app.test_client()

        conn_resp = await client.get("/api/course/connection-status")
        assert conn_resp.status_code == 200
        conn_data = await conn_resp.get_json()
        assert conn_data["ok"] is True
        assert conn_data["csp_enforced"] is True

        reg_blocked = await client.post("/api/course/register", json={
            "course_id": "alp_phase2_bicep_course",
            "full_name": "Ada Lovelace",
            "email": "ada@example.org",
            "organization": "Analytical Labs",
            "confirm_certificate": True,
        })
        assert reg_blocked.status_code == 403
        assert (await reg_blocked.get_json())["code"] == "TERMS_REQUIRED"

        terms_bad = await client.post("/api/course/terms", json={
            "course_id": "alp_phase2_bicep_course",
            "agree": False,
            "version": proj_mod.COURSE_TERMS_VERSION,
        })
        assert terms_bad.status_code == 400

        terms_ok = await client.post("/api/course/terms", json={
            "course_id": "alp_phase2_bicep_course",
            "agree": True,
            "version": proj_mod.COURSE_TERMS_VERSION,
        })
        assert terms_ok.status_code == 200
        assert (await terms_ok.get_json())["terms_accepted"]["accepted"] is True

        verify_blocked = await client.post("/api/course/execute", json={
            "action": "verify",
            "course_id": "alp_phase2_bicep_course",
            "step_id": "m0_s1",
            "selected_index": 1,
        })
        assert verify_blocked.status_code == 403
        assert (await verify_blocked.get_json())["code"] == "REGISTRATION_REQUIRED"

        reg_bad_email = await client.post("/api/course/register", json={
            "course_id": "alp_phase2_bicep_course",
            "full_name": "Ada Lovelace",
            "email": "not-an-email",
            "organization": "Analytical Labs",
            "confirm_certificate": True,
        })
        assert reg_bad_email.status_code == 400

        reg_ok = await client.post("/api/course/register", json={
            "course_id": "alp_phase2_bicep_course",
            "full_name": "Ada Lovelace",
            "email": "ada@example.org",
            "organization": "Analytical Labs",
            "role": "Principal Cloud Architect",
            "azure_location": "westeurope",
            "compliance_framework": "GDPR Article 32",
            "confirm_certificate": True,
        })
        assert reg_ok.status_code == 200
        reg_payload = await reg_ok.get_json()
        assert reg_payload["registration"]["full_name"] == "Ada Lovelace"
        assert reg_payload["registration"]["email"] == "ada@example.org"
        # Learners must confirm their email before registration counts: read the 6-digit code from the
        # verification email and send it to the verification route, exactly as the course page does.
        import re as _re
        mailbox_now = json.loads(isolated_env["mailbox_file"].read_text(encoding="utf-8"))
        codes = [_re.search(r"\b(\d{6})\b", str(m.get("text", ""))) for m in mailbox_now if m.get("to") == "ada@example.org"]
        codes = [c.group(1) for c in codes if c]
        assert codes, "verification email with a 6-digit code was not delivered"
        ver_code = await client.post("/api/course/verification/code", json={
            "course_id": "alp_phase2_bicep_course",
            "code": codes[-1],
        })
        assert ver_code.status_code == 200, await ver_code.get_json()

        for st in ("isolated", "recording", "rendering", "preview_ready", "saving", "saved"):
            lr = await client.post("/api/course/recorder-log", json={
                "course_id": "alp_phase2_bicep_course",
                "state": st,
                "native_state": "recording" if st == "recording" else "inactive",
                "card_id": "course-response-card",
                "resolution": "1920x1080",
                "fps": 30,
                "mime_type": "video/webm;codecs=vp9",
                "bytes": 102400 if st in ("preview_ready", "saving", "saved") else 0,
                "detail": f"Test transition {st}",
            })
            assert lr.status_code == 200
            lr_body = await lr.get_json()
            assert "logged" in lr_body, lr_body
            assert lr_body["logged"]["state"] == st

        log_file = isolated_env["logs_dir"] / "media_recorder_events.jsonl"
        assert log_file.is_file()
        logged_states = [json.loads(line)["state"] for line in log_file.read_text(encoding="utf-8").splitlines() if line.strip()]
        assert logged_states == ["isolated", "recording", "rendering", "preview_ready", "saving", "saved"]

        survey_early = await client.post("/api/course/survey", json={
            "course_id": "alp_phase2_bicep_course",
            "overall_rating": 5,
            "clarity_rating": 5,
            "accessibility_rating": 5,
            "confidence_rating": 5,
            "feedback": "Great course",
        })
        assert survey_early.status_code == 400, await survey_early.get_json()

        course_obj, prog = proj_mod._load_course_and_progress("alp_phase2_bicep_course")
        sections = proj_mod._ordered_sections(course_obj)
        prog["completed_steps"] = [sec["id"] for _, sec in sections]
        prog["reflections"] = {
            sec["id"]: {"reflection_done": True, "explain": "Verified section reflection in test."}
            for _, sec in sections
        }
        proj_mod._save_progress_sync("alp_phase2_bicep_course", prog)

        survey_ok = await client.post("/api/course/survey", json={
            "course_id": "alp_phase2_bicep_course",
            "overall_rating": 5,
            "clarity_rating": 5,
            "accessibility_rating": 5,
            "confidence_rating": 5,
            "feedback": "Excellent accessibility and 1080p standalone recording workflow.",
        })
        assert survey_ok.status_code == 200
        s_data = await survey_ok.get_json()
        assert s_data["ok"] is True
        cert = s_data["certificate"]
        cert_id = cert["certificate_id"]
        assert cert["full_name"] == "Ada Lovelace"
        assert cert["email"] == "ada@example.org"
        assert s_data["email_delivery"]["ok"] is True
        assert s_data["email_delivery"]["recipient"] == "ada@example.org"

        mailbox = json.loads(isolated_env["mailbox_file"].read_text(encoding="utf-8"))
        # One email confirms the address (verification), one delivers the signed certificate.
        assert len(mailbox) == 2
        assert all(m["to"] == "ada@example.org" for m in mailbox)
        cert_mails = [m for m in mailbox if m.get("attachments")]
        assert len(cert_mails) == 1
        att_names = [a["filename"] for a in cert_mails[0]["attachments"]]
        assert f"Certificate_of_Completion_{cert_id}.pdf" in att_names
        assert f"Certificate_Verification_{cert_id}.sig.json" in att_names

        ver_resp = await client.get(f"/api/course/certificate/verify?cert_id={cert_id}")
        assert ver_resp.status_code == 200
        ver_data = await ver_resp.get_json()
        assert ver_data["valid"] is True
        assert ver_data["pdf_pkcs7_valid"] is True
        assert ver_data["credential_ecdsa_valid"] is True
        assert ver_data["pdf_hash_match"] is True

        dl_resp = await client.get(f"/api/course/certificate/download?cert_id={cert_id}")
        assert dl_resp.status_code == 200
        pdf_bytes = await dl_resp.get_data()
        assert hashlib.sha256(pdf_bytes).hexdigest() == cert["pdf_sha256"]
        reader = PdfReader(io.BytesIO(pdf_bytes))
        extracted = reader.pages[0].extract_text()
        assert "Ada Lovelace" in extracted
        assert "ada@example.org" in extracted
        assert cert_id in extracted

    asyncio.run(_run())


def test_course_page_card_recorder_asset_and_static_bundle(tmp_path):
    async def _run():
        client = app.test_client()
        r_course = await client.get("/course")
        assert r_course.status_code == 200
        html = (await r_course.get_data()).decode("utf-8")
        assert 'id="course-terms-gate"' in html
        assert 'id="course-registration-gate"' in html
        assert 'id="course-survey-section"' in html
        assert '/static/card-recorder.js' in html

        r_js = await client.get("/static/card-recorder.js")
        assert r_js.status_code == 200
        js = (await r_js.get_data()).decode("utf-8")
        assert "captureStream(30)" in js
        assert "1920" in js and "1080" in js
        assert "MediaRecorder" in js

    asyncio.run(_run())
    out_dir = tmp_path / "dist_test"
    rc = build_siraugga_pages.main(out_dir=out_dir)
    assert rc == 0
    assert (out_dir / "static" / "card-recorder.js").is_file()
    assert (out_dir / "index.html").is_file()
    assert "card-recorder.js" in (out_dir / "index.html").read_text(encoding="utf-8")


def test_course_preview_mode_is_removed_and_never_leaks_answers(isolated_env):
    """There is no preview mode: ?preview=1 is ignored everywhere and access follows the tier limits."""
    async def _run():
        client = app.test_client()

        r_page = await client.get("/course?preview=1")
        assert r_page.status_code == 200
        html = (await r_page.get_data()).decode("utf-8")
        assert "const initialPreviewMode = false;" in html

        r_data = await client.get("/api/course/data?course=alp_phase2_bicep_course&preview=1")
        assert r_data.status_code == 200
        data = await r_data.get_json()
        assert data["ok"] is True
        assert not data.get("preview_mode")
        assert not data.get("progress", {}).get("preview_mode")
        # Answer keys, solutions and checks never reach a visitor through the preview flag
        for mod in data["course"]["modules"]:
            for sec in mod["sections"]:
                for hidden in ("correct_index", "correct_text", "solution_code", "bicep_checks", "code_checks"):
                    assert hidden not in sec, (sec.get("id"), hidden)

        # The preview flag must never write recorder logs
        assert not (isolated_env["logs_dir"] / "media_recorder_events.jsonl").exists()

        from core import response_cards
        status, card_payload = response_cards.resolve_card({"prompt": "full preview"})
        assert status == 200
        assert card_payload["matched"] is True
        card = card_payload["card"]
        assert card["iframes"] and "/plugin/course?course=alp_phase2_bicep_course" in card["iframes"][0]["src"]
        assert "preview=1" not in card["iframes"][0]["src"]
        assert "](/plugin/course" not in card["markdown"]

    asyncio.run(_run())
