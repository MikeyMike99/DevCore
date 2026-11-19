"""Tests for Siraugga course automation, CyberBrief course generation, and active learner protection."""
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core import course_automation as auto
from core import course_standards as std


@pytest.fixture
def temp_workspace(tmp_path):
    """Sets up an isolated test sandbox, courses directory, and backup directory."""
    courses_dir = tmp_path / "sandbox" / "static" / "courses"
    courses_dir.mkdir(parents=True, exist_ok=True)
    backups_dir = tmp_path / "core" / "backups"
    backups_dir.mkdir(parents=True, exist_ok=True)
    sandboxes_dir = tmp_path / "playground" / ".course_sandboxes"
    sandboxes_dir.mkdir(parents=True, exist_ok=True)
    cache_dir = tmp_path / "services" / "cyberbrief" / "cache"
    cache_dir.mkdir(parents=True, exist_ok=True)

    return {
        "root": str(tmp_path),
        "courses_dir": str(courses_dir),
        "backups_dir": str(backups_dir),
        "sandboxes_dir": str(sandboxes_dir),
        "cache_dir": str(cache_dir),
    }


def make_sample_course(cid="sample_sec_course", title="Sample Security Course"):
    return {
        "course_id": cid,
        "mode": "course",
        "title": title,
        "subtitle": "A practical security course.",
        "course_summary": "Learn to defend endpoints and network perimeters using verified controls and monitoring.",
        "objectives": [
            "Explain perimeter security boundaries.",
            "Identify indicators of compromise in audit logs.",
            "Deploy verified configuration lockfiles."
        ],
        "archetype": "revision_sprint",
        "theme": "indigo",
        "survey_topic": "Defending endpoints and networks",
        "modules": [
            {
                "module_number": 0,
                "title": "Module 0: Start here",
                "summary": "Take your time. You cannot break anything.",
                "objectives": ["Understand the course layout"],
                "closing_summary": "Ready to begin.",
                "summary_bullets": ["Overview", "Safe steps"],
                "sections": [
                    {
                        "id": f"{cid}_m0_s1",
                        "section_code": "Section 0.1",
                        "title": "Introduction",
                        "objectives": ["Understand objectives"],
                        "concept_summary": "This course covers perimeter defense and indicators of compromise.",
                        "concept_bullets": ["Defense in depth", "Log analysis"],
                        "word_breakdown": [{"term": "Defense", "meaning": "Protecting systems from attack."}],
                        "task_type": "multiple_choice",
                        "task_prompt": "What is the goal of defense in depth?",
                        "options": ["Layered security", "Single barrier", "No logging"],
                        "correct_index": 0,
                        "wrong_hint": "Layered security provides multiple protective barriers.",
                        "takeaway": "Multiple security layers protect systems better than a single barrier."
                    }
                ]
            },
            {
                "module_number": 1,
                "title": "Module 1: Threat Analysis",
                "summary": "Analyze attack vectors and indicators of compromise.",
                "objectives": ["Identify threat mechanisms", "Match controls to vectors"],
                "closing_summary": "Module 1 complete.",
                "summary_bullets": ["Attack vectors", "Matching controls"],
                "sections": [
                    {
                        "id": f"{cid}_m1_s1",
                        "section_code": "Section 1.1",
                        "title": "Attack Vectors",
                        "objectives": ["Analyze entry points"],
                        "concept_summary": "Attackers leverage unpatched interfaces to gain an initial foothold.",
                        "concept_bullets": ["Perimeter analysis", "Patching"],
                        "word_breakdown": [{"term": "Foothold", "meaning": "An initial access position inside a network."}],
                        "task_type": "multiple_choice",
                        "task_prompt": "How do attackers establish initial access?",
                        "options": ["Exploiting unpatched services", "Reading documentation", "Restarting routers"],
                        "correct_index": 0,
                        "wrong_hint": "Unpatched vulnerabilities leave external services exposed.",
                        "takeaway": "Prompt patching closes external exploit entry points."
                    },
                    {
                        "id": f"{cid}_m1_s2",
                        "section_code": "Section 1.2",
                        "title": "Module 1 Summary",
                        "concept_heading": "Summary",
                        "concept_summary": "Review the threat vectors covered in this module.",
                        "concept_bullets": ["Consolidate knowledge"],
                        "word_breakdown": [{"term": "Summary", "meaning": "A brief review of key ideas."}],
                        "task_type": "match_columns",
                        "task_prompt": "Match the threat vector to the countermeasure.",
                        "pairs": [
                            {"left": "Unpatched port", "right": "Apply vendor patch"},
                            {"left": "Weak password", "right": "Enforce multi-factor auth"},
                            {"left": "Plaintext traffic", "right": "Deploy TLS encryption"}
                        ],
                        "wrong_hint": "Pair each vulnerability with its direct mitigation.",
                        "takeaway": "Direct mitigation neutralizes specific exploit classes.",
                        "key_takeaways": [
                            "Patching prevents remote code execution.",
                            "MFA stops credential stuffing attacks."
                        ]
                    }
                ]
            }
        ]
    }


def test_find_active_learners(temp_workspace):
    root = temp_workspace["root"]
    box_dir = Path(temp_workspace["sandboxes_dir"]) / "student_alpha"
    box_dir.mkdir(parents=True)
    prog_file = box_dir / "course_progress_sample_sec_course.json"
    prog_file.write_text(json.dumps({
        "learner_name": "Alice",
        "current_step_index": 1,
        "completed_steps": ["sample_sec_course_m0_s1"],
        "certificate": None
    }), encoding="utf-8")

    learners = auto.find_active_learners(course_id="sample_sec_course", repo_root=root)
    assert len(learners) == 1
    L = learners[0]
    assert L["learner_name"] == "Alice"
    assert L["is_active"] is True
    assert L["completed_count"] == 1
    assert "sample_sec_course_m0_s1" in L["completed_steps"]


def test_verify_non_destructive_passes_for_inactive(temp_workspace):
    course = make_sample_course()
    # No active learners
    passed, violations = auto.verify_non_destructive_update(course, course, active_learners=[])
    assert passed is True
    assert len(violations) == 0


def test_verify_non_destructive_blocks_section_deletion(temp_workspace):
    old_course = make_sample_course()
    new_course = make_sample_course()
    # Remove completed section
    new_course["modules"][0]["sections"] = []

    active_learner = {
        "learner_name": "Alice",
        "is_active": True,
        "current_step_index": 1,
        "completed_steps": ["sample_sec_course_m0_s1"]
    }

    passed, violations = auto.verify_non_destructive_update(old_course, new_course, [active_learner])
    assert passed is False
    assert any("sample_sec_course_m0_s1" in v for v in violations)


def test_verify_non_destructive_blocks_reordering(temp_workspace):
    old_course = make_sample_course()
    new_course = make_sample_course()
    # Swap section order in module 1
    s1 = new_course["modules"][1]["sections"][0]
    s2 = new_course["modules"][1]["sections"][1]
    new_course["modules"][1]["sections"] = [s2, s1]

    active_learner = {
        "learner_name": "Alice",
        "is_active": True,
        "current_step_index": 2,
        "completed_steps": ["sample_sec_course_m0_s1", "sample_sec_course_m1_s1"]
    }

    passed, violations = auto.verify_non_destructive_update(old_course, new_course, [active_learner])
    assert passed is False
    assert any("order altered" in v for v in violations)


def test_verify_non_destructive_blocks_task_type_change(temp_workspace):
    old_course = make_sample_course()
    new_course = make_sample_course()
    # Change task_type from multiple_choice to dropdown_blank
    new_course["modules"][0]["sections"][0]["task_type"] = "dropdown_blank"
    new_course["modules"][0]["sections"][0]["task_prompt"] = "Select [BLANK]."
    new_course["modules"][0]["sections"][0]["correct_text"] = "Layered security"

    active_learner = {
        "learner_name": "Alice",
        "is_active": True,
        "current_step_index": 1,
        "completed_steps": ["sample_sec_course_m0_s1"]
    }

    passed, violations = auto.verify_non_destructive_update(old_course, new_course, [active_learner])
    assert passed is False
    assert any("task_type changed" in v for v in violations)


def test_safe_save_course_branches_on_destructive_update(temp_workspace):
    root = temp_workspace["root"]
    cdir = temp_workspace["courses_dir"]
    course = make_sample_course("active_branch_course")

    # 1. Save original course
    res1 = auto.safe_save_course(course, courses_dir=cdir, repo_root=root)
    assert res1["saved"] is True
    assert res1["course_id"] == "active_branch_course"

    # 2. Add an active learner
    box_dir = Path(temp_workspace["sandboxes_dir"]) / "student_active"
    box_dir.mkdir(parents=True)
    (box_dir / "course_progress_active_branch_course.json").write_text(json.dumps({
        "learner_name": "Bob",
        "current_step_index": 1,
        "completed_steps": ["active_branch_course_m0_s1"],
        "certificate": None
    }), encoding="utf-8")

    # 3. Create a breaking updated course (e.g. completely deletes Module 0)
    breaking_course = make_sample_course("active_branch_course")
    breaking_course["modules"] = [breaking_course["modules"][1]]  # remove mod 0

    res2 = auto.safe_save_course(breaking_course, courses_dir=cdir, overwrite=True, force_version_if_breaking=True, repo_root=root)
    assert res2["saved"] is True
    assert res2["versioned"] is True
    assert res2["course_id"] == "active_branch_course_v2"
    assert res2["original_id"] == "active_branch_course"

    # Original file is preserved untouched
    orig_path = Path(cdir) / "active_branch_course.json"
    assert orig_path.exists()
    with open(orig_path, "r", encoding="utf-8") as f:
        orig_data = json.load(f)
    assert len(orig_data["modules"]) == 2  # Still has both modules!


def test_safe_save_course_updates_in_place_when_safe(temp_workspace):
    root = temp_workspace["root"]
    cdir = temp_workspace["courses_dir"]
    course = make_sample_course("safe_update_course")

    # 1. Save initial
    res1 = auto.safe_save_course(course, courses_dir=cdir, repo_root=root)
    assert res1["saved"] is True

    # 2. Safe enhancement: add word breakdown definition
    course["modules"][0]["sections"][0]["word_breakdown"].append({
        "term": "Zero Trust", "meaning": "Trust no device or network by default."
    })
    res2 = auto.safe_save_course(course, courses_dir=cdir, overwrite=True, force_version_if_breaking=True, repo_root=root)
    assert res2["saved"] is True
    assert res2.get("versioned", False) is False
    assert res2["course_id"] == "safe_update_course"


def test_generate_course_from_story_strictly_passes_linter(temp_workspace):
    root = temp_workspace["root"]
    story = {
        "story_id": "test-cve-2026-9999-exploit",
        "title": "Critical Authentication Bypass in Microservice Gateways",
        "summary": "Attackers bypass bearer token verification by spoofing upstream proxy headers in microservice gateways.",
        "remediation": "Deploy immediate gateway patch, enforce mutual TLS, and validate JWT issuer signatures.",
        "score": 30,
        "cves": ["CVE-2026-9999"],
    }

    res = auto.generate_course_from_story(story, save=False, repo_root=root)
    assert res["passed"] is True, f"Lint errors: {res.get('errors')}"
    assert res["score"] >= 95
    assert len(res["errors"]) == 0

    c = res["course"]
    assert c["mode"] == "course"
    assert c["archetype"] == "revision_sprint"
    assert len(c["modules"]) == 3  # mod 0 + mod 1 + mod 2
    # Verify module 1 & 2 end with match_columns summary
    for m in c["modules"]:
        if m["module_number"] == 0:
            continue
        last_sec = m["sections"][-1]
        assert last_sec["task_type"] == "match_columns"
        assert len(last_sec.get("key_takeaways", [])) >= 2


def test_process_cyberbrief_digest_and_deduplication(temp_workspace):
    root = temp_workspace["root"]
    cdir = temp_workspace["courses_dir"]
    manifest_file = Path(temp_workspace["cache_dir"]) / "current_digest_manifest.json"

    manifest_data = {
        "dispatched_at": "2026-11-17 18:00 UTC",
        "items": [
            {
                "story_id": "supply-chain-trivy-hijack",
                "title": "Supply Chain Poisoning Discovered in Container Scanning Utilities",
                "summary": "Hackers planted malicious payloads into container scanning runners using modified workflow hashes.",
                "remediation": "Pin exact commit SHAs and restrict GitHub Actions execution privileges.",
                "score": 25,
            },
            {
                "story_id": "low-priority-note",
                "title": "Routine Maintenance Window Announced",
                "summary": "Standard routine maintenance scheduled for regional data centers.",
                "remediation": "No action required.",
                "score": 5,  # Below min_score threshold
            }
        ]
    }
    manifest_file.write_text(json.dumps(manifest_data), encoding="utf-8")

    # Run pass 1
    res1 = auto.process_cyberbrief_digest(
        manifest_path=str(manifest_file),
        min_score=15,
        max_new_courses=2,
        save=True,
        repo_root=root
    )
    assert res1["processed"] == 1  # Only 1 story meets score >= 15
    assert res1["generated"] == 1
    cid = res1["created_courses"][0]["course_id"]
    assert (Path(cdir) / f"{cid}.json").exists()

    # Run pass 2 (deduplication check)
    res2 = auto.process_cyberbrief_digest(
        manifest_path=str(manifest_file),
        min_score=15,
        max_new_courses=2,
        save=True,
        repo_root=root
    )
    assert res2["generated"] == 0  # Already generated, so skipped!
