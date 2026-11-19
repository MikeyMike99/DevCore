"""Structure checks for the original 'Linux Essentials: Step by Step' course, loaded through the real course engine."""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core import response_cards  # noqa: E402
from core.routes import projects as proj_mod  # noqa: E402

CID = "linux_essentials_step_by_step"


@pytest.fixture()
def course(monkeypatch, tmp_path):
    monkeypatch.setattr(proj_mod, "COURSE_SANDBOXES_ROOT", str(tmp_path / "boxes"))
    monkeypatch.setattr(proj_mod, "_course_learner_key", lambda: "linuxtest01")
    obj, _ = proj_mod._load_course_and_progress(CID)
    assert obj and obj["course_id"] == CID
    return obj


def sections(course):
    return [s for m in course["modules"] for s in m["sections"]]


def test_course_is_discovered_and_numbered(course):
    assert any(c["id"] == CID for c in response_cards.list_courses())
    ids = [s["id"] for s in sections(course)]
    assert len(ids) == len(set(ids)) >= 40
    for m in course["modules"]:
        n = m["module_number"]
        assert [s["section_code"] for s in m["sections"]] == [f"Section {n}.{i}" for i in range(1, len(m["sections"]) + 1)]


def test_every_section_has_what_the_engine_needs(course):
    for s in sections(course):
        for key in ("title", "recording_name", "concept_summary", "concept_bullets", "code_snippet", "task_type", "task_prompt", "takeaway"):
            assert s.get(key), (s["id"], key)
        t = s["task_type"]
        if t == "multiple_choice":
            assert len(s["options"]) >= 2 and 0 <= s["correct_index"] < len(s["options"]), s["id"]
        elif t == "dropdown_blank":
            assert "[BLANK]" in s["task_prompt"] and s["correct_text"] in s["options"], s["id"]
        elif t == "match_columns":
            assert len(s["pairs"]) >= 3 and all(p["left"] and p["right"] for p in s["pairs"]), s["id"]
        elif t == "terminal_command":
            assert s["expected_command"] == s["code_snippet"], s["id"]
            assert s["predict_prompt"] and s["reflection_prompt"], s["id"]
        else:
            pytest.fail(f"unexpected task type {t} in {s['id']}")


def test_practice_commands_are_safe_and_stay_in_the_sandbox(course):
    import re
    banned_words = ("sudo", "chown", "mkfs", "curl", "wget", "scp", "rsync", "uname -a", "$HOME", "$USER")
    for s in sections(course):
        if s["task_type"] != "terminal_command":
            continue
        cmd = s["expected_command"]
        assert not any(b in cmd for b in banned_words), cmd
        assert not re.search(r"(^|[^A-Za-z])(rm|dd)([^A-Za-z]|$)|> /etc|> /usr|> /bin", cmd), cmd
        # ssh is only ever asked for its version or to make a throw-away key, never to connect anywhere
        for m in re.finditer(r"(?<![a-z-])ssh(?![a-z-])\s*(\S*)", cmd):
            assert m.group(1) == "-V", cmd
        if "chmod" in cmd:
            # permissions only behave like Linux on the sandbox's private /tmp, not on the shared drive
            assert "/tmp/" in cmd, cmd


def test_course_covers_all_modules(course):
    assert [m["module_number"] for m in course["modules"]] == list(range(1, 27))
    assert len(sections(course)) >= 190
    for m in course["modules"]:
        kinds = {s["task_type"] for s in m["sections"]}
        assert "multiple_choice" in kinds, m["title"]
        assert kinds & {"match_columns", "dropdown_blank"}, m["title"]


def test_quiz_answers_are_not_always_the_same_slot(course):
    slots = [s["correct_index"] for s in sections(course) if s["task_type"] == "multiple_choice"]
    assert len(set(slots)) >= 2
