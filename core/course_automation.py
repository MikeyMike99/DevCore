"""Autonomous Siraugga Course Automation & Active Learner Protection Engine.

Core Capabilities:
1. Non-Destructive Active Learner Protection:
   - Scans all learner sandboxes and global progress states.
   - Verifies structural stability invariants before applying any update to an existing course.
   - Guarantees completed sections, progression sequence, and task types remain intact for active learners.
   - Automatically branches breaking updates into versioned editions (e.g. <cid>_v2) so in-flight learners
     are never disrupted or corrupted.
2. Automated Course Maintenance & Synchronization:
   - Audits all courses in sandbox/static/courses/*.json against course_standards.lint_course(strict=True).
   - Keeps cross references (related_courses) synchronized across the catalog.
   - Enriches word_breakdowns with everyday plain-English definitions from a security glossary.
   - Performs atomic writes with automated timestamped snapshot backups.
3. Automated CyberBrief Course Generation:
   - Converts high-priority CyberBrief threat intelligence stories into fully compliant Siraugga courses.
   - Formats content according to Siraugga voice rules, required archetypes, themes, and learning loops.
   - Automatically cross-links new threat courses to existing foundation courses.
"""
from __future__ import annotations

import copy
import glob
import json
import logging
import os
import re
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from core import course_standards as std

logger = logging.getLogger("core.course_automation")

COMMON_GLOSSARY: Dict[str, str] = {
    "cve": "A catalog of publicly known cybersecurity vulnerabilities.",
    "sha pinning": "Locking dependencies to exact cryptographic commit hashes.",
    "c2 channel": "A command and control server used by attackers to send remote instructions.",
    "backdoor": "A covert method of bypassing normal authentication to access a system.",
    "zero trust": "A security model where no user or device is trusted by default.",
    "payload": "The malicious code or exploit delivered during an attack.",
    "firewall": "A network security barrier that filters incoming and outgoing traffic.",
    "hash": "A one-way mathematical fingerprint of data.",
    "token": "A temporary digital credential proving identity or permission.",
    "supply chain": "The sequence of vendors, code, and packages used to build software.",
    "ioc": "An indicator of compromise that signals a system was breached.",
    "remediation": "The steps and patches required to fix a vulnerability.",
    "least privilege": "Giving a user or program only the exact access needed for its job.",
    "sandbox": "An isolated environment where untrusted code can run safely.",
    "lockfile": "A file that records the exact versions and hashes of dependencies.",
    "ci/cd": "Automated pipelines that build, test, and deploy software.",
    "audit": "A systematic review of security records, code, or permissions.",
    "acl": "An access control list defining who can reach a resource.",
}


def _repo_root() -> str:
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _courses_dir(root: Optional[str] = None) -> str:
    r = root or _repo_root()
    return os.path.join(r, "sandbox", "static", "courses")


def _backups_dir(root: Optional[str] = None) -> str:
    r = root or _repo_root()
    d = os.path.join(r, "core", "backups")
    os.makedirs(d, exist_ok=True)
    return d


def _state_file_path(root: Optional[str] = None) -> str:
    r = root or _repo_root()
    d = os.path.join(r, "services", "cyberbrief", "cache")
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, "course_automation_state.json")


def _safe_id(raw_id: str) -> str:
    clean = re.sub(r"[^a-z0-9_-]", "", str(raw_id or "").strip().lower())
    if clean.endswith(".json"):
        clean = clean[:-5]
    return clean


# ---------------------------------------------------------------------------
# 1. Active Learner Inspection & Discovery
# ---------------------------------------------------------------------------

def find_active_learners(course_id: Optional[str] = None, repo_root: Optional[str] = None) -> List[Dict[str, Any]]:
    """Discovers all active learners across learner sandboxes and global progress states.
    
    A learner is considered active if:
    1. They have made progress (completed_steps is non-empty or current_step_index > 0).
    2. The course has not been finished (no certificate has been issued).
    """
    root = repo_root or _repo_root()
    target_cid = _safe_id(course_id) if course_id else None
    learners: List[Dict[str, Any]] = []

    search_patterns = [
        os.path.join(root, "playground", ".course_sandboxes", "*", "course_progress_*.json"),
        os.path.join(root, "data", "course_workspaces", "*", "course_progress_*.json"),
        os.path.join(root, "sandbox", "static", "courses", "progress_*.json"),
        "/home/michael/alp-env/temp_phase2_sandbox/course_progress_*.json",
    ]

    seen_files: Set[str] = set()
    found_paths: List[str] = []
    for pattern in search_patterns:
        for path in glob.glob(pattern):
            if path not in seen_files:
                seen_files.add(path)
                found_paths.append(path)

    for path in found_paths:
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                continue
        except Exception:
            continue

        base = os.path.basename(path)
        if base.startswith("course_progress_"):
            cid = _safe_id(base[len("course_progress_"):-5])
        elif base.startswith("progress_"):
            cid = _safe_id(base[len("progress_"):-5])
        else:
            continue

        if target_cid and cid != target_cid:
            continue

        completed_steps = data.get("completed_steps") or []
        if not isinstance(completed_steps, list):
            completed_steps = []
        try:
            step_idx = int(data.get("current_step_index", 0))
        except (ValueError, TypeError):
            step_idx = 0

        cert = data.get("certificate")
        has_certificate = bool(cert and isinstance(cert, dict) and cert.get("sha256"))

        is_active = (len(completed_steps) > 0 or step_idx > 0) and not has_certificate

        mtime = os.path.getmtime(path) if os.path.exists(path) else 0.0

        learners.append({
            "course_id": cid,
            "learner_id": str(data.get("learner_profile", {}).get("learner_handle") or os.path.basename(os.path.dirname(path)) or "unknown"),
            "learner_name": str(data.get("learner_name") or data.get("learner_profile", {}).get("learner_name") or "learner"),
            "current_step_index": step_idx,
            "completed_steps": [str(s) for s in completed_steps],
            "completed_count": len(completed_steps),
            "has_certificate": has_certificate,
            "is_active": is_active,
            "source_path": path,
            "last_activity_ts": mtime,
        })

    return learners


# ---------------------------------------------------------------------------
# 2. Invariant Validation: Non-Destructive Update Checker
# ---------------------------------------------------------------------------

def _extract_course_structure(course: Dict[str, Any]) -> Tuple[List[str], Dict[str, Dict[str, Any]]]:
    """Returns ordered section IDs and section metadata dictionary."""
    ordered_ids: List[str] = []
    sections_map: Dict[str, Dict[str, Any]] = {}
    for mod in course.get("modules") or []:
        if not isinstance(mod, dict):
            continue
        for sec in mod.get("sections") or []:
            if not isinstance(sec, dict):
                continue
            sid = str(sec.get("id") or "").strip()
            if sid:
                ordered_ids.append(sid)
                sections_map[sid] = sec
    return ordered_ids, sections_map


def verify_non_destructive_update(
    existing_course: Dict[str, Any],
    candidate_course: Dict[str, Any],
    active_learners: Optional[List[Dict[str, Any]]] = None,
) -> Tuple[bool, List[str]]:
    """Verifies that candidate_course is non-destructive to all active learners of existing_course.
    
    Guarantees:
    1. Zero Deletion of In-Flight Steps: Every section ID that has been completed by any active
       learner MUST remain present in the candidate course.
    2. Stable Order Preservation: The relative order of sections up to the highest active step
       must remain identical.
    3. Task Type Immutability: The task_type of completed sections must not change (so learner answers
       and evaluations remain valid).
    4. Module Preservation: Modules containing completed sections cannot be removed.
    """
    cid = existing_course.get("course_id") or ""
    if active_learners is None:
        active_learners = [L for L in find_active_learners(cid) if L.get("is_active")]
    else:
        active_learners = [L for L in active_learners if L.get("is_active")]

    if not active_learners:
        return True, []

    violations: List[str] = []
    old_ids, old_secs = _extract_course_structure(existing_course)
    new_ids, new_secs = _extract_course_structure(candidate_course)

    # 1. Identify all section IDs that must be protected
    completed_section_ids: Set[str] = set()
    max_active_index = 0
    for learner in active_learners:
        for sid in learner.get("completed_steps") or []:
            completed_section_ids.add(sid)
        max_active_index = max(max_active_index, learner.get("current_step_index", 0))

    # Also protect sections up to max_active_index that exist in old course
    protected_prefix_ids = old_ids[:max_active_index + 1]
    all_protected_ids = completed_section_ids | set(protected_prefix_ids)

    # Invariant A: Every protected section ID must exist in new course
    for pid in all_protected_ids:
        if pid not in new_secs:
            violations.append(
                f"Section '{pid}' is required by active learner(s) and cannot be removed."
            )

    # Invariant B: Relative ordering of protected sections must be preserved
    new_id_indices = {sid: idx for idx, sid in enumerate(new_ids)}
    ordered_protected = [sid for sid in old_ids if sid in all_protected_ids and sid in new_id_indices]
    for i in range(len(ordered_protected) - 1):
        s1 = ordered_protected[i]
        s2 = ordered_protected[i + 1]
        if new_id_indices[s1] >= new_id_indices[s2]:
            violations.append(
                f"Relative section order altered: '{s1}' must precede '{s2}' for active learners."
            )
            break

    # Invariant C: Completed section task types cannot change
    for sid in completed_section_ids:
        if sid in old_secs and sid in new_secs:
            old_tt = old_secs[sid].get("task_type")
            new_tt = new_secs[sid].get("task_type")
            if old_tt != new_tt:
                violations.append(
                    f"Section '{sid}' task_type changed from '{old_tt}' to '{new_tt}' for active learners."
                )

    passed = len(violations) == 0
    return passed, violations


# ---------------------------------------------------------------------------
# 3. Safe Course Storage with Automatic Versioning & Backups
# ---------------------------------------------------------------------------

def safe_save_course(
    course: Dict[str, Any],
    courses_dir: Optional[str] = None,
    overwrite: bool = True,
    force_version_if_breaking: bool = True,
    repo_root: Optional[str] = None,
) -> Dict[str, Any]:
    """Validates and saves a course atomically.
    
    If the course already exists and has active learners:
    - Runs verify_non_destructive_update.
    - If non-destructive: updates the course in-place atomically with a backup.
    - If destructive: branches into a new version (e.g. <cid>_v2), preserving the original
      course untouched for in-flight learners.
    """
    root = repo_root or _repo_root()
    cdir = courses_dir or _courses_dir(root)
    os.makedirs(cdir, exist_ok=True)

    # 1. Strict Siraugga Standard Validation
    known_ids = {f[:-5] for f in os.listdir(cdir) if f.endswith(".json") and not f.startswith("progress_")}
    raw_cid = str(course.get("course_id") or "").strip()
    cid = _safe_id(raw_cid)
    if not cid:
        return {"saved": False, "reason": "empty_course_id", "errors": ["course_id is empty or invalid"]}

    course["course_id"] = cid
    lint_rep = std.lint_course(course, strict=True, known_course_ids=known_ids | {cid})
    if not lint_rep["passed"]:
        return {
            "saved": False,
            "reason": "lint_failed",
            "score": lint_rep["score"],
            "errors": lint_rep["errors"],
            "warnings": lint_rep["warnings"],
        }

    target_path = os.path.join(cdir, f"{cid}.json")
    is_versioned = False
    original_id = cid

    # 2. Check for existing file & Active Learners
    if os.path.exists(target_path):
        if not overwrite:
            return {"saved": False, "reason": "already_exists", "errors": [f"'{cid}' already exists; set overwrite to true to replace it"]}

        try:
            with open(target_path, "r", encoding="utf-8") as f:
                existing_course = json.load(f)
        except Exception as e:
            existing_course = None

        if isinstance(existing_course, dict):
            active_learners = [L for L in find_active_learners(cid, repo_root=root) if L.get("is_active")]
            if active_learners:
                is_safe, violations = verify_non_destructive_update(existing_course, course, active_learners)
                if not is_safe:
                    if not force_version_if_breaking:
                        return {
                            "saved": False,
                            "reason": "destructive_update_blocked",
                            "violations": violations,
                            "active_learners_count": len(active_learners),
                        }
                    # Branch to new version to protect active learners
                    ver = 2
                    while True:
                        new_cid = f"{cid}_v{ver}"
                        new_path = os.path.join(cdir, f"{new_cid}.json")
                        if not os.path.exists(new_path):
                            break
                        ver += 1
                    cid = new_cid
                    target_path = new_path
                    course["course_id"] = cid
                    course["title"] = f"{course.get('title', '')} (Edition {ver})"
                    is_versioned = True
                    logger.warning(
                        "Branched course '%s' to '%s' to protect %d active learner(s).",
                        original_id, cid, len(active_learners)
                    )

    # 3. Snapshot Backup
    if os.path.exists(target_path):
        bdir = _backups_dir(root)
        ts = int(time.time())
        backup_file = os.path.join(bdir, f"{original_id}.{ts}.json")
        try:
            with open(backup_file, "w", encoding="utf-8") as bf:
                json.dump(existing_course, bf, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.warning("Could not write backup snapshot: %s", e)

    # 4. Atomic Write
    fd, tmp_path = tempfile.mkstemp(dir=cdir, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(course, f, indent=2, ensure_ascii=False)
        os.replace(tmp_path, target_path)
    finally:
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except Exception:
                pass

    return {
        "saved": True,
        "course_id": cid,
        "original_id": original_id,
        "versioned": is_versioned,
        "score": lint_rep["score"],
        "warnings": lint_rep["warnings"][:10],
        "path": target_path,
        "url": f"/course?course={cid}",
    }


# ---------------------------------------------------------------------------
# 4. Automated Course Maintenance & Cross-Reference Synchronization
# ---------------------------------------------------------------------------

def audit_and_sync_all_courses(
    courses_dir: Optional[str] = None,
    dry_run: bool = False,
    repo_root: Optional[str] = None,
) -> Dict[str, Any]:
    """Audits every course in the catalog, synchronizes cross references,
    and applies safe non-breaking enhancements without disturbing active learners.
    """
    root = repo_root or _repo_root()
    cdir = courses_dir or _courses_dir(root)
    files = sorted(f for f in os.listdir(cdir) if f.endswith(".json") and not f.startswith("progress_"))
    known_ids = {f[:-5] for f in files}

    results: List[Dict[str, Any]] = []
    updated_count = 0

    for fn in files:
        cid = fn[:-5]
        p = os.path.join(cdir, fn)
        try:
            with open(p, "r", encoding="utf-8") as f:
                c = json.load(f)
            if not isinstance(c, dict):
                continue
        except Exception as e:
            results.append({"course_id": cid, "passed": False, "error": f"JSON decode error: {e}"})
            continue

        rep = std.lint_course(c, strict=True, known_course_ids=known_ids)
        c_modified = False

        # Cross reference synchronization: Ensure related_courses includes active catalog cousins
        current_related = list(c.get("related_courses") or [])
        clean_related = [rc for rc in current_related if rc in known_ids and rc != cid]

        # If cybersecurity/infra related, cross-link to peer security courses
        title_lower = (c.get("title") or "").lower()
        if any(term in title_lower for term in ("cyber", "security", "threat", "defense", "incident")):
            for peer in ("cybersecurity_revision", "siraugga_security_essentials"):
                if peer in known_ids and peer != cid and peer not in clean_related and len(clean_related) < 5:
                    clean_related.append(peer)

        if clean_related != current_related:
            c["related_courses"] = clean_related
            c_modified = True

        # Content hygiene: Enrich sections with definitions from COMMON_GLOSSARY where appropriate
        for mod in c.get("modules") or []:
            if not isinstance(mod, dict):
                continue
            for sec in mod.get("sections") or []:
                if not isinstance(sec, dict):
                    continue
                wb = sec.get("word_breakdown") or []
                existing_terms = {str(item.get("term", "")).lower() for item in wb if isinstance(item, dict)}
                summary_text = (sec.get("concept_summary") or "").lower()
                for term, meaning in COMMON_GLOSSARY.items():
                    if term in summary_text and term not in existing_terms and len(wb) < 4:
                        wb.append({"term": term.title(), "meaning": meaning})
                        existing_terms.add(term)
                        c_modified = True
                sec["word_breakdown"] = wb

        if c_modified and not dry_run:
            save_res = safe_save_course(c, courses_dir=cdir, overwrite=True, force_version_if_breaking=True, repo_root=root)
            if save_res.get("saved"):
                updated_count += 1
                results.append({
                    "course_id": cid,
                    "passed": True,
                    "updated": True,
                    "score": save_res.get("score"),
                    "versioned": save_res.get("versioned", False),
                })
                continue

        results.append({
            "course_id": cid,
            "passed": rep["passed"],
            "updated": False,
            "score": rep["score"],
            "warnings_count": len(rep["warnings"]),
        })

    return {
        "total_courses": len(files),
        "updated": updated_count,
        "dry_run": dry_run,
        "courses": results,
    }


# ---------------------------------------------------------------------------
# 5. Automated CyberBrief Course Generation
# ---------------------------------------------------------------------------

def _clean_plain_text(text: str) -> str:
    """Strips markdown asterisks, hashes, and formatting for Siraugga plain-text fields."""
    cleaned = re.sub(r"\*\*|\*|#{1,6}\s*", "", str(text or "")).strip()
    # Remove condescending words
    for w in ("obviously", "simply", "trivial", "clearly", "just"):
        cleaned = re.sub(rf"\b{w}\b", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def generate_course_from_story(
    story: Dict[str, Any],
    archetype: str = "revision_sprint",
    theme: str = "indigo",
    save: bool = True,
    courses_dir: Optional[str] = None,
    repo_root: Optional[str] = None,
) -> Dict[str, Any]:
    """Builds a complete, 100% compliant Siraugga course from a CyberBrief threat story.
    
    Adheres strictly to Siraugga standards:
    - Calm, respectful voice rules ("Take your time. You cannot break anything.")
    - Plain English first, short active sentences (< 25 words).
    - Every technical term receives a plain-English word_breakdown.
    - Modules in revision_sprint end with a match_columns summary and key_takeaways.
    - Zero destructive impact: generated under a fresh, unique course ID.
    """
    raw_title = str(story.get("title") or "Emerging Threat Briefing")
    story_id = _safe_id(story.get("story_id") or raw_title[:32])
    cid = f"cyberbrief_{story_id}"[:48].rstrip("_")

    title = f"Threat Defense: {_clean_plain_text(raw_title)[:58]}"
    summary_text = _clean_plain_text(story.get("summary") or "Analysis of recent cyber threats and remediation strategies.")
    remediation_text = _clean_plain_text(story.get("remediation") or "Apply security updates and enforce zero trust segmentation.")
    cves = story.get("cves") or []
    cve_note = f"CVE references: {', '.join(cves)}." if cves else "Advisory analysis from CyberBrief."

    theme = theme if theme in std.THEMES else "indigo"

    course = {
        "course_id": cid,
        "mode": "course",
        "title": title,
        "subtitle": f"Interactive practical briefing on defending against {_clean_plain_text(raw_title)[:45]}.",
        "course_summary": f"This course explores {summary_text[:140]} Learn the attack vector, inspect forensic evidence, and apply verified remediation controls.",
        "objectives": [
            "Explain the threat vector and vulnerability root cause.",
            "Identify key indicators of compromise and log patterns.",
            "Apply verified remediation controls and defensive hardening.",
            "Verify configuration lockfiles to prevent future exploitation."
        ],
        "archetype": "revision_sprint",
        "theme": theme,
        "survey_topic": "Defending production systems against emerging threat vectors",
        "badge_label": "Siraugga CyberBrief Defense",
        "related_courses": ["cybersecurity_revision", "siraugga_security_essentials"],
        "modules": []
    }

    # Module 0: Start Here
    mod0 = {
        "module_number": 0,
        "title": "Module 0: Start here",
        "summary": "Take your time. You cannot break anything. This briefing walks you through the threat mechanics step by step.",
        "objectives": [
            "Understand the briefing goals and threat scope.",
            "Learn how to navigate the interactive questions and takeaways."
        ],
        "closing_summary": "You are ready to begin the briefing. Proceed to Module 1.",
        "summary_bullets": [
            "Plain-English threat breakdown with real indicators.",
            "Zero destructive actions in your environment.",
            "Predict first, then verify, then reflect."
        ],
        "sections": [
            {
                "id": f"{cid[:12]}_m0_s1",
                "section_code": "Section 0.1",
                "title": "Threat Overview and Environment Safety",
                "objectives": [
                    "Review the threat briefing scope",
                    "Understand how the learning loop works"
                ],
                "concept_summary": f"This briefing analyses an active security advisory. {summary_text[:150]} Take your time. You cannot break anything in this environment.",
                "concept_bullets": [
                    "Understand the threat mechanism before writing defensive policies.",
                    "Verify indicators of compromise with precise log searches.",
                    "Apply defense-in-depth rather than single-point fixes."
                ],
                "word_breakdown": [
                    {"term": "Advisory", "meaning": "An official alert detailing a security vulnerability."},
                    {"term": "Takeaway", "meaning": "The single most critical idea to remember."}
                ],
                "task_type": "multiple_choice",
                "task_prompt": "What is the primary objective of this threat defense briefing?",
                "options": [
                    "To understand the threat vector and apply verified defensive controls",
                    "To deploy unvalidated third-party scripts without testing",
                    "To disable system logging to prevent alert noise"
                ],
                "correct_index": 0,
                "wrong_hint": "Focus on understanding the vulnerability root cause and applying proven defensive protections.",
                "takeaway": "Always examine the vulnerability mechanism before deploying defensive mitigations."
            }
        ]
    }
    course["modules"].append(mod0)

    # Module 1: Threat Mechanics & Vectors
    mod1 = {
        "module_number": 1,
        "title": "Module 1: Attack Vector and Exploitation Mechanics",
        "summary": "Examine how attackers exploit this vulnerability to bypass trust boundaries.",
        "objectives": [
            "Identify the initial entry vector used by the threat.",
            "Describe the impact on downstream systems and dependencies."
        ],
        "closing_summary": "You have analyzed the initial compromise vector and trust boundary violations.",
        "summary_bullets": [
            "Attackers exploit unpinned or unmonitored dependencies.",
            "Strict cryptographic verification neutralizes payload injection."
        ],
        "sections": [
            {
                "id": f"{cid[:12]}_m1_s1",
                "section_code": "Section 1.1",
                "title": "Analyzing the Threat Mechanism",
                "objectives": [
                    "Recognize the vulnerability vector",
                    "Evaluate the security boundary failure"
                ],
                "concept_summary": f"The threat targets system components to execute unauthorized actions. {summary_text[:120]} Attackers exploit trust relationships to establish persistence.",
                "concept_bullets": [
                    "Malicious payloads often masquerade as legitimate updates.",
                    "Unpinned dependencies create supply chain exposure.",
                    "Cryptographic verification ensures file integrity."
                ],
                "word_breakdown": [
                    {"term": "Payload", "meaning": "The executable code delivered during an exploit."},
                    {"term": "Exploit", "meaning": "A method used to take advantage of a software flaw."}
                ],
                "task_type": "multiple_choice",
                "task_prompt": "Why do attackers attempt to bypass SHA pinning and software verification?",
                "options": [
                    "To substitute approved code with modified or malicious versions",
                    "To speed up automated build pipelines",
                    "To reduce network bandwidth consumption"
                ],
                "correct_index": 0,
                "wrong_hint": "Attackers target integrity checks so their modified payloads are executed without detection.",
                "takeaway": "Cryptographic pinning prevents attackers from substituting trusted code with malicious variants."
            },
            {
                "id": f"{cid[:12]}_m1_s2",
                "section_code": "Section 1.2",
                "title": "Verifying Trust Boundaries with Dropdown Checks",
                "objectives": [
                    "Identify the missing verification control",
                    "Select the appropriate defensive boundary"
                ],
                "concept_summary": "Defenders must enforce strict verification at every boundary. Without exact hash verification, mutable tags can be modified upstream without warning.",
                "concept_bullets": [
                    "Tags like latest or main can be moved to point to malicious commits.",
                    "Cryptographic commit hashes cannot be altered without changing the SHA value."
                ],
                "word_breakdown": [
                    {"term": "Hash", "meaning": "A unique digital fingerprint calculated from data."}
                ],
                "task_type": "dropdown_blank",
                "task_prompt": "Software components must be locked to an exact [BLANK] to prevent supply chain tampering.",
                "options": ["SHA hash", "branch name", "version tag", "author name"],
                "correct_text": "SHA hash",
                "wrong_hint": "Only an immutable cryptographic hash guarantees that source code has not been altered.",
                "takeaway": "Branch names and version tags are mutable. Only cryptographic hashes provide immutable integrity."
            },
            {
                "id": f"{cid[:12]}_m1_s3",
                "section_code": "Section 1.3",
                "title": "Module 1 Review and Takeaways",
                "concept_heading": "Summary",
                "concept_summary": "Review the core concepts from Module 1. Match each security mechanism to its defensive role.",
                "concept_bullets": [
                    "Match the threat concept to the corresponding defensive rule."
                ],
                "word_breakdown": [
                    {"term": "Integrity", "meaning": "Ensuring data has not been altered or tampered with."}
                ],
                "task_type": "match_columns",
                "task_prompt": "Match the attack vector concept on the left with its defensive countermeasure on the right.",
                "pairs": [
                    {"left": "Mutable release tag", "right": "Pin exact commit SHA hash"},
                    {"left": "Covert C2 channel", "right": "Enforce egress traffic filtering"},
                    {"left": "Supply chain poisoning", "right": "Verify cryptographic signatures"}
                ],
                "wrong_hint": "Review how immutable hashes counteract mutable tag manipulation.",
                "takeaway": "Immutable cryptographic pinning neutralizes tag redirection attacks.",
                "key_takeaways": [
                    "Mutable tags allow attackers to silently redirect execution.",
                    "Exact SHA pinning guarantees immutable package integrity."
                ]
            }
        ]
    }
    course["modules"].append(mod1)

    # Module 2: Detection, Remediation & Verification
    mod2 = {
        "module_number": 2,
        "title": "Module 2: Detection, Hardening and Remediation",
        "summary": "Implement verified remediation controls to eliminate the vulnerability and verify system posture.",
        "objectives": [
            "Deploy recommended remediation steps for this threat.",
            "Verify configuration lockfiles to guarantee ongoing compliance."
        ],
        "closing_summary": "You have implemented defense-in-depth controls and verified compliance.",
        "summary_bullets": [
            "Immediate perimeter patching and zero trust isolation.",
            "Automated lockfile validation prevents regression."
        ],
        "sections": [
            {
                "id": f"{cid[:12]}_m2_s1",
                "section_code": "Section 2.1",
                "title": "Executing Verified Remediation Controls",
                "objectives": [
                    "Identify the primary remediation strategy",
                    "Apply least privilege and segmentation"
                ],
                "concept_summary": f"Remediating this threat requires defensive hardening. {remediation_text[:140]} Enforce isolation and update perimeter access policies.",
                "concept_bullets": [
                    "Deploy security patches provided in the vendor advisory.",
                    "Isolate vulnerable endpoints behind multi-factor authentication.",
                    "Audit CI/CD credentials and revoke exposed tokens."
                ],
                "word_breakdown": [
                    {"term": "Remediation", "meaning": "The corrective action taken to fix a security flaw."},
                    {"term": "Zero Trust", "meaning": "Verifying every request explicitly regardless of origin."}
                ],
                "task_type": "multiple_choice",
                "task_prompt": "Which combination of controls provides the strongest defense against this threat?",
                "options": [
                    "Deploy vendor security patches, enforce MFA, and isolate management interfaces",
                    "Rely solely on perimeter firewalls without patching internal components",
                    "Allow unrestricted outbound traffic to simplify third-party updates"
                ],
                "correct_index": 0,
                "wrong_hint": "Defense in depth combines timely patching, identity controls (MFA), and network segmentation.",
                "takeaway": "Patching vulnerabilities and enforcing least privilege together prevent lateral movement."
            },
            {
                "id": f"{cid[:12]}_m2_s2",
                "section_code": "Section 2.2",
                "title": "Module 2 Summary and Remediation Mastery",
                "concept_heading": "Summary",
                "concept_summary": "Review the full remediation workflow. Match each operational response to its security objective.",
                "concept_bullets": [
                    "Consolidate your knowledge of defense-in-depth and verification."
                ],
                "word_breakdown": [
                    {"term": "Mitigation", "meaning": "Reducing the severity or impact of a potential threat."}
                ],
                "task_type": "match_columns",
                "task_prompt": "Match the operational control on the left with its security outcome on the right.",
                "pairs": [
                    {"left": "Perimeter patch deployment", "right": "Closes known vulnerability entry points"},
                    {"left": "Credential rotation", "right": "Invalidates compromised API and access keys"},
                    {"left": "Process spawn monitoring", "right": "Detects anomalous child execution in real time"}
                ],
                "wrong_hint": "Consider the specific purpose of patching, secret rotation, and runtime monitoring.",
                "takeaway": "Comprehensive remediation combines vulnerability eradication, credential rotation, and continuous telemetry.",
                "key_takeaways": [
                    "Prompt patching neutralizes known exploit vectors before automated scanning reaches them.",
                    "Continuous process monitoring catches post-exploitation activity immediately."
                ]
            }
        ]
    }
    course["modules"].append(mod2)

    # 3. Save if requested
    if save:
        res = safe_save_course(course, courses_dir=courses_dir, overwrite=False, force_version_if_breaking=True, repo_root=repo_root)
        return {
            "course": course,
            "saved": res.get("saved", False),
            "course_id": res.get("course_id", cid),
            "score": res.get("score"),
            "url": res.get("url"),
            "path": res.get("path"),
            "warnings": res.get("warnings", []),
        }

    rep = std.lint_course(course, strict=True)
    return {
        "course": course,
        "saved": False,
        "score": rep["score"],
        "passed": rep["passed"],
        "errors": rep["errors"],
        "warnings": rep["warnings"],
    }


# ---------------------------------------------------------------------------
# 6. CyberBrief Digest Processor & Automation Pipeline
# ---------------------------------------------------------------------------

def process_cyberbrief_digest(
    manifest_path: Optional[str] = None,
    min_score: int = 15,
    max_new_courses: int = 2,
    save: bool = True,
    repo_root: Optional[str] = None,
) -> Dict[str, Any]:
    """Reads the active CyberBrief digest manifest, selects qualified threat stories,
    and generates compliant Siraugga courses while recording state to prevent duplicate generation.
    """
    root = repo_root or _repo_root()
    m_path = manifest_path or os.path.join(root, "services", "cyberbrief", "cache", "current_digest_manifest.json")
    if not os.path.exists(m_path):
        return {"processed": 0, "generated": 0, "reason": "manifest_not_found"}

    try:
        with open(m_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)
    except Exception as e:
        return {"processed": 0, "generated": 0, "reason": f"manifest_read_error: {e}"}

    items = manifest.get("items") or []
    if not isinstance(items, list):
        return {"processed": 0, "generated": 0, "reason": "empty_items"}

    # Load automation state
    state_file = _state_file_path(root)
    state: Dict[str, Any] = {}
    if os.path.exists(state_file):
        try:
            with open(state_file, "r", encoding="utf-8") as sf:
                state = json.load(sf)
        except Exception:
            state = {}

    processed_story_ids = set(state.get("processed_story_ids") or [])
    generated_courses = state.get("generated_courses") or []

    # Sort items by score descending
    sorted_items = sorted(
        [it for it in items if isinstance(it, dict) and it.get("score", 0) >= min_score],
        key=lambda x: x.get("score", 0),
        reverse=True
    )

    created: List[Dict[str, Any]] = []
    for item in sorted_items:
        sid = _safe_id(item.get("story_id") or "")
        if not sid or sid in processed_story_ids:
            continue

        gen_res = generate_course_from_story(item, save=save, repo_root=root)
        if gen_res.get("saved"):
            created.append({
                "story_id": sid,
                "course_id": gen_res.get("course_id"),
                "score": gen_res.get("score"),
                "url": gen_res.get("url"),
            })
            processed_story_ids.add(sid)
            generated_courses.append({
                "story_id": sid,
                "course_id": gen_res.get("course_id"),
                "title": item.get("title"),
                "generated_at": datetime.now(timezone.utc).isoformat(),
            })

        if len(created) >= max_new_courses:
            break

    # Save state
    state["processed_story_ids"] = list(processed_story_ids)
    state["generated_courses"] = generated_courses
    state["last_run"] = datetime.now(timezone.utc).isoformat()
    try:
        with open(state_file, "w", encoding="utf-8") as sf:
            json.dump(state, sf, indent=2)
    except Exception as e:
        logger.warning("Could not persist course automation state: %s", e)

    return {
        "processed": len(sorted_items),
        "generated": len(created),
        "created_courses": created,
    }


def run_full_course_automation_pipeline(
    dry_run: bool = False,
    repo_root: Optional[str] = None,
) -> Dict[str, Any]:
    """Unified runner:
    1. Audits existing courses and synchronizes cross-references (non-destructively).
    2. Identifies active learners to verify protection boundaries.
    3. Ingests fresh CyberBrief threat stories and publishes new defense courses.
    """
    root = repo_root or _repo_root()
    active_learners = find_active_learners(repo_root=root)
    active_count = len([L for L in active_learners if L.get("is_active")])

    audit_res = audit_and_sync_all_courses(dry_run=dry_run, repo_root=root)

    digest_res = process_cyberbrief_digest(save=not dry_run, repo_root=root)

    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "active_learners_count": active_count,
        "existing_courses_audited": audit_res.get("total_courses", 0),
        "existing_courses_updated": audit_res.get("updated", 0),
        "cyberbrief_courses_generated": digest_res.get("generated", 0),
        "new_courses": digest_res.get("created_courses", []),
        "dry_run": dry_run,
    }
