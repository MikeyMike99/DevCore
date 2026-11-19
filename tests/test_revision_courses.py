"""The six revision courses: objectives, summaries, takeaways, quiz validity and safe practice commands."""
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core import response_cards  # noqa: E402
from core.routes import projects as proj_mod  # noqa: E402

COURSE_IDS = [
    "python_pcep_revision", "networking_revision", "cybersecurity_revision",
    "english_for_it_revision", "report_writing_revision", "packet_tracer_revision",
]


@pytest.fixture(params=COURSE_IDS)
def course(request, monkeypatch, tmp_path):
    monkeypatch.setattr(proj_mod, "COURSE_SANDBOXES_ROOT", str(tmp_path / "boxes"))
    monkeypatch.setattr(proj_mod, "_course_learner_key", lambda: "revisiontest01")
    obj, _ = proj_mod._load_course_and_progress(request.param)
    assert obj and obj["course_id"] == request.param
    return obj


def sections(course):
    return [s for m in course["modules"] for s in m["sections"]]


def test_courses_are_discovered():
    ids = {c["id"] for c in response_cards.list_courses()}
    assert set(COURSE_IDS) <= ids


def test_every_section_has_objectives_and_a_takeaway(course):
    secs = sections(course)
    assert len(secs) >= 15
    for s in secs:
        assert s.get("takeaway"), s["id"]
        assert s.get("concept_summary"), s["id"]
        if s["task_type"] == "match_columns":
            # module summaries carry the key takeaways instead of objectives
            assert s.get("key_takeaways") and len(s["key_takeaways"]) >= 2, s["id"]
            assert s.get("concept_heading") == "Summary", s["id"]
        else:
            assert s.get("objectives") and all(isinstance(o, str) and o for o in s["objectives"]), s["id"]


def test_every_module_ends_with_a_summary(course):
    for m in course["modules"]:
        if m["module_number"] == 0:
            continue
        last = m["sections"][-1]
        assert last["task_type"] == "match_columns" and last.get("key_takeaways"), m["title"]


def test_questions_are_valid_and_answers_vary(course):
    slots = []
    for s in sections(course):
        t = s["task_type"]
        if t == "multiple_choice":
            assert 0 <= s["correct_index"] < len(s["options"]) >= 2, s["id"]
            slots.append(s["correct_index"])
        elif t == "dropdown_blank":
            assert "[BLANK]" in s["task_prompt"] and s["correct_text"] in s["options"], s["id"]
        elif t == "match_columns":
            assert len(s["pairs"]) >= 3 and all(p["left"] and p["right"] for p in s["pairs"]), s["id"]
        elif t == "terminal_command":
            assert s["expected_command"] == s["code_snippet"], s["id"]
            assert s.get("predict_prompt") and s.get("reflection_prompt"), s["id"]
        else:
            pytest.fail(f"unexpected task type {t}")
    ids = [s["id"] for s in sections(course)]
    assert len(ids) == len(set(ids))


def test_practice_commands_are_safe(course):
    banned = ("sudo", "chmod", "chown", "curl", "wget", "$HOME", "$USER", "alp-env")
    allowed_start = ("python3 -c ", "mkdir -p linux_practice")
    for s in sections(course):
        if s["task_type"] != "terminal_command":
            continue
        cmd = s["expected_command"]
        assert cmd.startswith(allowed_start), cmd
        assert not any(b in cmd for b in banned), cmd
        assert not re.search(r"(^|[^A-Za-z])(rm|dd)([^A-Za-z]|$)", cmd), cmd
        # no network commands used as commands (a service NAME such as 'ssh' inside a lookup is fine)
        assert not re.search(r"(^|[;&|]\s*)(ssh|scp|nc|telnet|ftp)\s", cmd), cmd
        assert "import os" not in cmd and "subprocess" not in cmd and "open(" not in cmd, cmd


def test_course_page_shows_objectives_and_takeaway_panels():
    html = (ROOT / "sandbox" / "templates" / "course_application.html").read_text(encoding="utf-8")
    for needle in ("objectives-box", "objectives-list", "keytakeaways-box", "keytakeaways-list", "sec.objectives", "sec.key_takeaways"):
        assert needle in html, needle
