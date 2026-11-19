"""Siraugga Course Standard: linter, course-studio MCP tools, SAVE_COURSE gate, code_editor alias, catalog."""
import asyncio
import copy
import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core import course_standards as std  # noqa: E402
from core.routes import projects as proj_mod  # noqa: E402


def _section(i, tt="multiple_choice", **extra):
    s = {
        "id": f"s{i}", "section_code": f"Section 1.{i}", "title": f"Part {i}",
        "objectives": ["Say what a file is"], "concept_summary": "A file holds data. You can open it.",
        "concept_bullets": ["Files have names"], "word_breakdown": [{"term": "file", "meaning": "a named place for data"}],
        "task_type": tt, "task_prompt": "Pick the right answer.", "takeaway": "Files hold data.",
        "options": ["a", "b", "c"], "correct_index": i % 3, "wrong_hint": "Think about what a file stores.",
    }
    s.update(extra)
    return s


def _summary():
    return {
        "id": "sum", "section_code": "Section 1.9", "title": "Summary", "concept_heading": "Summary",
        "concept_summary": "You met files.", "concept_bullets": ["Files"], "task_type": "match_columns",
        "task_prompt": "Match them.", "takeaway": "Well done.", "key_takeaways": ["Files hold data", "Names matter"],
        "pairs": [{"left": "a", "right": "1"}, {"left": "b", "right": "2"}, {"left": "c", "right": "3"}],
    }


def good_course():
    return {
        "course_id": "sample_course", "mode": "course", "title": "Sample", "subtitle": "A sample",
        "course_summary": "Learn files.", "objectives": ["One", "Two", "Three"],
        "archetype": "revision_sprint", "theme": "amber", "survey_topic": "files",
        "modules": [{
            "module_number": 1, "title": "Files", "summary": "About files", "objectives": ["Know files", "Open files"],
            "closing_summary": "You did it", "summary_bullets": ["Files", "Names"],
            "sections": [_section(1), _section(2), _summary()],
        }],
    }


def test_good_course_passes():
    rep = std.lint_course(good_course())
    assert rep["passed"], rep["errors"]
    assert rep["score"] >= 90


@pytest.mark.parametrize("mutate,needle", [
    (lambda c: c.pop("course_summary"), "course_summary"),
    (lambda c: c["modules"][0].pop("closing_summary"), "closing_summary"),
    (lambda c: c["modules"][0]["sections"][0].update(correct_index=9), "correct_index"),
    (lambda c: c["modules"][0]["sections"][0].update(concept_summary="This is **bold**."), "markdown"),
    (lambda c: c["modules"][0]["sections"][0].update(takeaway="Nice \U0001F600"), "emoji"),
    (lambda c: c["modules"][0]["sections"][1].update(id="s1"), "duplicate"),
    (lambda c: c["modules"][0]["sections"][0].update(wrong_hint=""), "wrong_hint"),
    (lambda c: c.update(theme="pink"), "theme"),
    (lambda c: c["modules"][0]["sections"].pop(), "match_columns summary"),
])
def test_linter_catches_problems(mutate, needle):
    c = good_course()
    mutate(c)
    rep = std.lint_course(c)
    assert not rep["passed"]
    assert any(needle in e for e in rep["errors"]), rep["errors"]


def test_terminal_command_must_be_safe_and_match_snippet():
    c = good_course()
    c["modules"][0]["sections"][0] = _section(1, "terminal_command", expected_command="sudo ls", code_snippet="ls",
                                              predict_prompt="p", common_errors=[{"error": "e", "cause": "c", "fix": "f"}])
    errs = " ".join(std.lint_course(c)["errors"])
    assert "differs from code_snippet" in errs and "banned" in errs


def test_monotony_warns_and_non_strict_softens_framing():
    c = good_course()
    c["modules"][0]["sections"] = [_section(i) for i in range(1, 7)] + [_summary()]
    assert any("in a row" in w for w in std.lint_course(c)["warnings"])
    c.pop("course_summary")
    assert not std.lint_course(c, strict=True)["passed"]
    assert std.lint_course(c, strict=False)["passed"]


def test_code_editor_alias_runs_as_legacy_editor():
    c = {"modules": [{"sections": [{"task_type": "code_editor", "file_path": "a.py", "code_checks": [{"x": 1}]}]}]}
    sec = proj_mod._normalize_editor_aliases(copy.deepcopy(c))["modules"][0]["sections"][0]
    assert sec["task_type"] == "bicep_editor" and sec["bicep_file"] == "a.py" and sec["bicep_checks"] == [{"x": 1}]
    hidden = proj_mod._sanitize_course_for_client({"modules": [{"sections": [{"code_checks": 1, "bicep_checks": 1}]}]})
    assert "code_checks" not in hidden["modules"][0]["sections"][0]


def test_save_exam_blocks_rejects_course_below_standard(monkeypatch, tmp_path):
    from agents import exam_store
    monkeypatch.setattr(exam_store, "COURSES_DIR", str(tmp_path / "courses"))
    monkeypatch.setattr(exam_store, "DEVCORE_ROOT", str(tmp_path))
    (tmp_path / "sandbox" / "static").mkdir(parents=True)
    bad = good_course()
    bad["modules"][0]["sections"][0]["correct_index"] = 9
    res = exam_store.save_exam_blocks(f"[SAVE_COURSE]{json.dumps(bad)}[/SAVE_COURSE]", {}, True)
    assert res and not res[0]["ok"] and "Siraugga Course Standard" in res[0]["message"]
    ok = exam_store.save_exam_blocks(f"[SAVE_COURSE]{json.dumps(good_course())}[/SAVE_COURSE]", {}, True)
    assert ok and ok[0]["ok"]


def _load_server(monkeypatch, tmp_path):
    pytest.importorskip("mcp.server.mcpserver")
    spec = importlib.util.spec_from_file_location("course_studio_server", ROOT / ".agents/plugins/course_studio/server.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    monkeypatch.setattr(mod, "COURSES_DIR", str(tmp_path / "courses"))
    return mod


def test_mcp_tools_round_trip(monkeypatch, tmp_path):
    srv = _load_server(monkeypatch, tmp_path)
    assert json.loads(srv.get_course_standard())["name"] == "Siraugga Course Standard"
    plan = json.loads(srv.plan_course_blueprint("Sample", "files", "hands_on_lab", source_outline="- A\n- B", module_count=2,
                                                blend_with="communication_studio"))
    assert [m["title"] for m in plan["modules"]] == ["A", "B"] and plan["course"]["blend_with"]
    assert "error" in json.loads(srv.plan_course_blueprint("x", "y", "nope"))

    assert json.loads(srv.validate_course(json.dumps(good_course())))["passed"]
    assert not json.loads(srv.validate_course("{not json"))["passed"]

    saved = json.loads(srv.save_course(json.dumps(good_course())))
    assert saved["saved"] and saved["url"] == "/course?course=sample_course"
    again = json.loads(srv.save_course(json.dumps(good_course())))
    assert not again["saved"] and "overwrite" in again["errors"][0]
    assert json.loads(srv.save_course(json.dumps(good_course()), overwrite=True))["saved"]

    evil = good_course()
    evil["course_id"] = "../../evil"
    out = json.loads(srv.save_course(json.dumps(evil)))
    assert out["saved"] and out["course_id"] == "evil"  # traversal characters are stripped
    assert not (tmp_path / "evil.json").exists()
    assert {r["course_id"] for r in json.loads(srv.list_courses())} == {"sample_course", "evil"}
    assert json.loads(srv.audit_existing_courses("sample_course"))[0]["passed"]
    assert not json.loads(srv.save_course(json.dumps({"mode": "course"})))["saved"]


def test_catalog_lists_shipped_courses():
    from core.server import app

    async def _run():
        r = await app.test_client().get("/courses")
        assert r.status_code == 200
        html = (await r.get_data()).decode("utf-8")
        assert "Siraugga Courses" in html and "alp_phase2_bicep_course" in html

    asyncio.run(_run())


# ---------------------------------------------------------------- cross references and CyberBrief advert

COURSES_DIR = ROOT / "sandbox" / "static" / "courses"


def _shipped_courses():
    out = {}
    for f in sorted(COURSES_DIR.glob("*.json")):
        if f.name.startswith("progress_"):
            continue
        c = json.loads(f.read_text(encoding="utf-8"))
        out[c["course_id"]] = c
    return out


def test_cross_references_are_plain_text_lists():
    c = good_course()
    c["related_courses"] = ["other_course"]
    c["modules"][0]["see_also"] = [{"course_id": "other_course", "note": "Module 2: access control"}]
    assert std.lint_course(c, known_course_ids={"demo_ok", "other_course", "sample_course"})["passed"]

    unknown = std.lint_course(c, known_course_ids={"sample_course"})
    assert any("unknown course" in w for w in unknown["warnings"])

    bad = good_course()
    bad["related_courses"] = "other_course"
    assert any("related_courses must be a list" in e for e in std.lint_course(bad)["errors"])

    for note in ("see https://example.org", "use **bold**"):
        worse = good_course()
        worse["modules"][0]["see_also"] = [{"course_id": "x", "note": note}]
        assert any("plain text" in e for e in std.lint_course(worse)["errors"]), note

    selfref = good_course()
    selfref["related_courses"] = [selfref["course_id"]]
    assert any("itself" in w for w in std.lint_course(selfref)["warnings"])


def test_shipped_courses_have_valid_related_courses_and_see_also():
    courses = _shipped_courses()
    ids = set(courses)
    for cid, c in courses.items():
        related = c.get("related_courses")
        assert related and 1 <= len(related) <= 5, cid
        assert cid not in related and set(related) <= ids, (cid, related)
        for m in c["modules"]:
            for e in m.get("see_also", []):
                assert e["course_id"] in ids and e["course_id"] != cid, (cid, e)
                assert "http" not in e.get("note", "").lower(), (cid, e)
        rep = std.lint_course(c, known_course_ids=ids)
        assert rep["passed"], (cid, rep["errors"][:3])
        assert not [w for w in rep["warnings"] if "unknown course" in w or "itself" in w], cid


def test_course_data_carries_related_titles_and_cyberbrief_advert():
    from core.server import app

    async def _run():
        r = await app.test_client().get("/api/course/data?course=alp_phase2_bicep_course")
        assert r.status_code == 200
        data = await r.get_json()
        extras = data["course"]["_extras"]
        assert extras["related_titles"] and all(isinstance(x, str) and "http" not in x for x in extras["related_titles"])
        assert "alp_phase2_bicep_course" in extras["catalog_titles"]
        cb = extras.get("cyberbrief")
        if cb:  # shown only when a public https address is configured
            assert cb["url"].startswith("https://") and cb["name"] == "CyberBrief"

    asyncio.run(_run())


def test_course_page_has_cross_reference_and_cyberbrief_spots(monkeypatch):
    html = (ROOT / "sandbox" / "templates" / "course_application.html").read_text(encoding="utf-8")
    for needle in ("see-also-box", "module-cyberbrief-line", "course-end-extras", "Check out these courses next",
                   "Nothing is subscribed for you", "noopener noreferrer"):
        assert needle in html, needle


def test_cyberbrief_url_needs_https_and_can_be_overridden(monkeypatch):
    monkeypatch.setitem(proj_mod._CYBERBRIEF_URL_CACHE, "done", False)
    monkeypatch.setenv("CYBERBRIEF_SUBSCRIBE_URL", "http://insecure.example/subscribe")
    assert proj_mod._cyberbrief_subscribe_url() is None
    monkeypatch.setitem(proj_mod._CYBERBRIEF_URL_CACHE, "done", False)
    monkeypatch.setenv("CYBERBRIEF_SUBSCRIBE_URL", "https://cyberbrief.example/subscribe")
    assert proj_mod._cyberbrief_subscribe_url() == "https://cyberbrief.example/subscribe"
    monkeypatch.setitem(proj_mod._CYBERBRIEF_URL_CACHE, "done", False)  # do not leak the override into other tests


def test_courses_without_a_related_list_get_suggestions_and_copy_is_accurate():
    extras = proj_mod._course_extras({"course_id": "brand_new", "archetype": "revision_sprint"})
    assert 1 <= len(extras["related_titles"]) <= 3
    assert "brand_new" not in extras["catalog_titles"]
    cb = extras.get("cyberbrief")
    if cb:
        text = cb["blurb"].lower()
        assert "free" in text and "newsletter" in text
        assert "siraugga" not in text  # CyberBrief is its own newsletter; do not claim otherwise


def test_dynamic_course_stats_and_formatting():
    assert std.format_estimated_duration(12) == "About 10 minutes"
    assert std.format_estimated_duration(42) == "About 40 minutes"
    assert std.format_estimated_duration(60) == "About 1 hour"
    assert std.format_estimated_duration(92) == "About 1.5 hours"
    assert std.format_estimated_duration(120) == "About 2 hours"

    c = good_course()
    stats = std.compute_course_stats(c)
    assert stats["modules"] == 1
    assert stats["sections"] == 3
    assert stats["estimated_minutes"] == 9  # 3 mc/match_columns @ 3m each
    assert "minutes" in stats["estimated_duration"]

    c["modules"][0]["sections"][0]["estimated_minutes"] = 15
    stats_override = std.compute_course_stats(c)
    assert stats_override["estimated_minutes"] == 21  # 15 + 3 + 3


def test_linter_warns_on_module_count_drift():
    c = good_course()
    c["subtitle"] = "In this 7-module course, you learn all about files."
    rep = std.lint_course(c)
    assert any("avoid count drift" in w and "{{module_count}}" in w for w in rep["warnings"])


def test_mcp_blueprint_and_listing_dynamic_stats(monkeypatch, tmp_path):
    srv = _load_server(monkeypatch, tmp_path)
    std_info = json.loads(srv.get_course_standard())
    assert "dynamic_stats" in std_info
    assert "{{module_count}}" in std_info["dynamic_stats"]["placeholders"]

    plan = json.loads(srv.plan_course_blueprint("Sample Course", "Python testing", "coding_workshop", module_count=3))
    assert "stats" in plan
    assert plan["stats"]["modules"] == 3
    assert plan["stats"]["estimated_minutes"] > 0
    assert "{{module_count}}" in plan["course"]["subtitle"]
    assert any("count drift" in item for item in plan["checklist"])

    srv.save_course(json.dumps(good_course()))
    listed = json.loads(srv.list_courses())
    assert any("estimated_duration" in entry and entry["estimated_minutes"] > 0 for entry in listed)
