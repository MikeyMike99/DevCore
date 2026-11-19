"""The Siraugga Course Standard: voice, archetypes, themes and a deterministic linter.

One source of truth used by the course-studio MCP server, exam_store ([SAVE_COURSE])
and the tests. Pure Python, no third-party imports.
"""
from __future__ import annotations

import re
from typing import Any

THEMES = ("teal", "cyan", "emerald", "amber", "indigo")

TASK_TYPES = {
    "multiple_choice", "dropdown_blank", "match_columns", "terminal_command",
    "code_editor", "bicep_editor", "agent_card", "org_question", "course_setup", "exam_app",
}
QUIZ_TYPES = {"multiple_choice", "dropdown_blank", "match_columns"}
EDITOR_TYPES = {"code_editor", "bicep_editor"}

SECTION_MINUTES_BY_TYPE: dict[str, int] = {
    "multiple_choice": 3,
    "dropdown_blank": 3,
    "match_columns": 3,
    "org_question": 3,
    "course_setup": 5,
    "terminal_command": 6,
    "code_editor": 10,
    "bicep_editor": 10,
    "agent_card": 10,
    "exam_app": 25,
}
DEFAULT_SECTION_MINUTES: int = 4

ARCHETYPES: dict[str, dict[str, Any]] = {
    "hands_on_lab": {
        "best_for": "Cloud, Linux, DevOps and security labs",
        "rhythm": "concept -> predict -> terminal/editor task -> observe -> multiple_choice checkpoint",
        "task_mix": ["terminal_command", "code_editor", "agent_card", "multiple_choice"],
        "modules": "4-8 modules, 5-10 sections each",
        "optional": ["org_question", "course_setup"],
    },
    "coding_workshop": {
        "best_for": "Python, scripting and APIs",
        "rhythm": "short concept -> predict the output -> code_editor + terminal_command -> match_columns",
        "task_mix": ["code_editor", "terminal_command", "match_columns", "multiple_choice"],
        "modules": "4-7 modules, 4-8 sections each",
        "optional": [],
    },
    "revision_sprint": {
        "best_for": "Exam preparation",
        "rhythm": "crisp refresher -> scenario multiple_choice -> dropdown_blank -> module match_columns summary",
        "task_mix": ["multiple_choice", "dropdown_blank", "match_columns", "terminal_command"],
        "modules": "5-9 modules, 3-5 sections each; every module ends with a match_columns summary",
        "optional": [],
    },
    "communication_studio": {
        "best_for": "English for IT, report writing, architecture documents",
        "rhythm": "workplace scenario -> dropdown_blank/multiple_choice -> agent_card drafting and critique -> match_columns",
        "task_mix": ["dropdown_blank", "multiple_choice", "agent_card", "match_columns"],
        "modules": "4-8 modules, 3-5 sections each",
        "optional": [],
    },
    "guided_simulation": {
        "best_for": "Packet Tracer and GUI or diagram workflows",
        "rhythm": "mental model -> scenario multiple_choice -> config snippet check -> match_columns",
        "task_mix": ["multiple_choice", "terminal_command", "match_columns", "dropdown_blank"],
        "modules": "4-6 modules, 3-5 sections each",
        "optional": [],
    },
}

VOICE_RULES = [
    "Calm and respectful. Open with reassurance such as 'Take your time. You cannot break anything.'",
    "Plain English first. Explain the real-world why before any syntax or acronym.",
    "Speak to 'you' in short, active sentences (aim for 25 words or fewer).",
    "Never use condescending filler: obviously, simply, just, trivial, easy, clearly.",
    "No emoji and no ASCII art inside course content (screen readers read them aloud).",
    "Plain text only in concept_summary, objectives, word_breakdown, wrong_hint and takeaway: no ** or ###.",
    "Every technical term gets a word_breakdown entry (term, meaning) in everyday words.",
    "Learning loop: predict, do, observe, reflect, takeaway. Wrong answers get a wrong_hint that teaches.",
    "Safe by default: no sudo, curl, wget, rm, dd or host paths in practice commands.",
]

SECTION_REQUIRED = ["id", "section_code", "title", "objectives", "concept_summary",
                    "concept_bullets", "task_type", "task_prompt", "takeaway"]
COURSE_REQUIRED = ["course_id", "mode", "title", "subtitle", "course_summary", "objectives",
                   "archetype", "theme", "survey_topic", "modules"]
MODULE_REQUIRED = ["module_number", "title", "summary", "objectives", "closing_summary",
                   "summary_bullets", "sections"]

PLAIN_TEXT_FIELDS = ("concept_summary", "takeaway", "wrong_hint")
BANNED_WORDS = ("obviously", "simply", "trivial", "clearly")
BANNED_CMD = ("sudo", "chmod", "chown", "curl", "wget", "$HOME", "$USER", "alp-env")
_MD_RE = re.compile(r"\*\*|(^|\s)#{1,6}\s")
_ASCII_RE = re.compile(r"(\+[-=]{3,}|\|\s{2,}\||={4,}|-{6,})")
_EMOJI_RE = re.compile("[\U0001F300-\U0001FAFF☀-➿]")
_DANGER_RE = re.compile(r"(^|[^A-Za-z])(rm|dd)([^A-Za-z]|$)")
_MAX_MONOTONY = 4


def format_estimated_duration(total_minutes: int | float) -> str:
    mins = max(5, round(total_minutes / 5) * 5)
    if mins < 60:
        return f"About {mins} minutes"
    half_hours = max(2, round((total_minutes / 60) * 2))
    hours = half_hours / 2
    label = str(int(hours)) if hours.is_integer() else f"{hours:.1f}"
    unit = "hour" if hours == 1 else "hours"
    return f"About {label} {unit}"


def compute_course_stats(course: Any) -> dict[str, Any]:
    mods = course.get("modules") if isinstance(course, dict) and isinstance(course.get("modules"), list) else []
    section_count = 0
    total_minutes = 0
    for m in mods:
        if not isinstance(m, dict):
            continue
        secs = m.get("sections")
        if not isinstance(secs, list):
            continue
        section_count += len(secs)
        for s in secs:
            if not isinstance(s, dict):
                continue
            explicit = s.get("estimated_minutes")
            if isinstance(explicit, (int, float)) and explicit > 0:
                total_minutes += int(explicit)
            else:
                total_minutes += SECTION_MINUTES_BY_TYPE.get(s.get("task_type"), DEFAULT_SECTION_MINUTES)
    return {
        "modules": len(mods),
        "sections": section_count,
        "estimated_minutes": total_minutes,
        "estimated_duration": format_estimated_duration(total_minutes),
    }


class _Report:
    def __init__(self) -> None:
        self.errors: list[str] = []
        self.warnings: list[str] = []

    def err(self, where: str, msg: str) -> None:
        self.errors.append(f"{where}: {msg}")

    def warn(self, where: str, msg: str) -> None:
        self.warnings.append(f"{where}: {msg}")


def _texts(sec: dict) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for f in PLAIN_TEXT_FIELDS:
        if isinstance(sec.get(f), str):
            out.append((f, sec[f]))
    for f in ("objectives", "concept_bullets", "key_takeaways"):
        for v in sec.get(f) or []:
            if isinstance(v, str):
                out.append((f, v))
    for wb in sec.get("word_breakdown") or []:
        if isinstance(wb, dict):
            out.append(("word_breakdown", f"{wb.get('term', '')} {wb.get('meaning', '')}"))
    return out


def _lint_style(r: _Report, where: str, sec: dict) -> None:
    for field, text in _texts(sec):
        if _MD_RE.search(text):
            r.err(where, f"{field} has markdown symbols; use plain text")
        if _ASCII_RE.search(text):
            r.err(where, f"{field} has ASCII art")
        if _EMOJI_RE.search(text):
            r.err(where, f"{field} has emoji")
        low = text.lower()
        for w in BANNED_WORDS:
            if re.search(rf"\b{w}\b", low):
                r.warn(where, f"{field} uses condescending word '{w}'")
    summary = sec.get("concept_summary")
    if isinstance(summary, str):
        for sentence in re.split(r"[.!?]+\s", summary):
            if len(sentence.split()) > 35:
                r.warn(where, "concept_summary has a sentence over 35 words")
                break


def _lint_task(r: _Report, where: str, sec: dict, strict: bool, archetype: str = "") -> None:
    t = sec.get("task_type")
    if t not in TASK_TYPES:
        r.err(where, f"unknown task_type '{t}'")
        return
    if t == "multiple_choice":
        opts, ci = sec.get("options"), sec.get("correct_index")
        if not (isinstance(opts, list) and len(opts) >= 3):
            r.err(where, "multiple_choice needs at least 3 options")
        elif not (isinstance(ci, int) and 0 <= ci < len(opts)):
            r.err(where, "correct_index is out of range")
    elif t == "dropdown_blank":
        if "[BLANK]" not in str(sec.get("task_prompt", "")):
            r.err(where, "dropdown_blank prompt needs [BLANK]")
        if sec.get("correct_text") not in (sec.get("options") or []):
            r.err(where, "correct_text must be one of options")
    elif t == "match_columns":
        pairs = sec.get("pairs") or []
        if len(pairs) < 3 or not all(isinstance(p, dict) and p.get("left") and p.get("right") for p in pairs):
            r.err(where, "match_columns needs at least 3 pairs with left and right")
    elif t == "terminal_command":
        cmd = sec.get("expected_command")
        if not cmd:
            r.err(where, "terminal_command needs expected_command")
        else:
            if cmd != sec.get("code_snippet"):
                (r.err if archetype == "revision_sprint" else r.warn)(where, "expected_command differs from code_snippet")
            banned = tuple(b for b in BANNED_CMD if not (b == "chmod" and archetype == "hands_on_lab"))
            if any(b in cmd for b in banned) or _DANGER_RE.search(cmd):
                r.err(where, "command uses a banned or destructive word")
    elif t in EDITOR_TYPES:
        if not (sec.get("file_path") or sec.get("bicep_file")):
            r.err(where, "editor task needs file_path")
        for f in ("starter_code", "solution_code"):
            if not sec.get(f):
                r.err(where, f"editor task needs {f}")
        if not (sec.get("code_checks") or sec.get("bicep_checks")):
            r.err(where, "editor task needs code_checks")
    elif t == "agent_card":
        for f in ("agent_goal", "agent_file", "agent_format", "agent_suggestions"):
            if not sec.get(f):
                r.err(where, f"agent_card needs {f}")
    elif t == "exam_app":
        if not sec.get("exam_file"):
            r.err(where, "exam_app needs exam_file")
    if strict:
        if t in QUIZ_TYPES and t != "match_columns" and not sec.get("wrong_hint"):
            r.err(where, "quiz needs a wrong_hint that teaches")
        if t in ({"terminal_command"} | EDITOR_TYPES) and not sec.get("skip_reflection"):
            if not sec.get("predict_prompt"):
                r.warn(where, "lab step has no predict_prompt")
            if not sec.get("common_errors"):
                r.warn(where, "lab step has no common_errors")


def _lint_cross_refs(r: _Report, where: str, value, own_id, known_ids, is_related_list: bool = False) -> None:
    if value is None:
        return
    if not isinstance(value, list):
        r.err(where, "related_courses must be a list of course ids" if is_related_list else "see_also must be a list")
        return
    for item in value:
        cid = item if is_related_list else (item.get("course_id") if isinstance(item, dict) else None)
        if not isinstance(cid, str) or not cid:
            r.err(where, "cross reference needs a course id" if is_related_list else "see_also entries need a course_id")
            continue
        if cid == own_id:
            r.warn(where, "cross reference points at the course itself")
        if known_ids is not None and cid not in known_ids:
            r.warn(where, f"cross reference to unknown course '{cid}'")
        if not is_related_list:
            note = item.get("note", "")
            if note and (not isinstance(note, str) or _MD_RE.search(note) or "http" in note.lower()):
                r.err(where, "see_also note must be plain text with no markdown or links")
    if is_related_list and len(value) > 5:
        r.warn(where, "related_courses should list 5 courses or fewer")


def lint_course(course: Any, strict: bool = True, known_course_ids=None) -> dict:
    """Check a course dict against the Siraugga standard.

    Returns {passed, score, errors, warnings, stats}. 'passed' means no errors.
    strict=False downgrades framing and word_breakdown gaps to warnings.
    known_course_ids: optional set of saved course ids; when given, cross references to unknown courses are warned about.
    """
    r = _Report()
    if not isinstance(course, dict):
        return {"passed": False, "score": 0, "errors": ["course must be a JSON object"], "warnings": [], "stats": {}}

    soft = r.err if strict else r.warn
    for k in COURSE_REQUIRED:
        if not course.get(k):
            (r.err if k in ("course_id", "title", "modules") else soft)("course", f"missing '{k}'")
    if course.get("mode") != "course":
        r.err("course", "mode must be 'course'")
    if course.get("archetype") and course["archetype"] not in ARCHETYPES:
        r.err("course", f"archetype must be one of {sorted(ARCHETYPES)}")
    if course.get("theme") and course["theme"] not in THEMES:
        r.err("course", f"theme must be one of {list(THEMES)}")
    objs = course.get("objectives")
    if isinstance(objs, list) and not 3 <= len(objs) <= 8:
        r.warn("course", "objectives should number 3 to 8")

    _lint_cross_refs(r, "course", course.get("related_courses"), course.get("course_id"), known_course_ids, is_related_list=True)

    modules = course.get("modules")
    seen_ids: set[str] = set()
    n_sections = 0
    if not isinstance(modules, list) or not modules:
        r.err("course", "modules must be a non-empty list")
        modules = []

    for fld in ("subtitle", "course_summary"):
        val = course.get(fld)
        if isinstance(val, str):
            m_count = re.search(r"\b(\d+)\s*[- ]\s*modules?\b", val, re.I)
            if m_count and int(m_count.group(1)) != len(modules):
                r.warn("course", f"{fld} mentions '{m_count.group(0)}' but course has {len(modules)} modules; use '{{{{module_count}}}}' to avoid count drift")

    for m in modules:
        mw = f"module {m.get('module_number', '?')}" if isinstance(m, dict) else "module ?"
        if not isinstance(m, dict):
            r.err(mw, "must be an object")
            continue
        for k in MODULE_REQUIRED:
            if k == "module_number":
                if not isinstance(m.get(k), int):
                    r.err(mw, "missing 'module_number'")
            elif not m.get(k):
                (r.err if k in ("title", "sections") else soft)(mw, f"missing '{k}'")
        _lint_cross_refs(r, mw, m.get("see_also"), course.get("course_id"), known_course_ids)
        secs = m.get("sections") or []
        if secs and m.get("module_number") != 0 and course.get("archetype") == "revision_sprint":
            last = secs[-1]
            if not (last.get("task_type") == "match_columns" and last.get("key_takeaways")):
                r.err(mw, "revision_sprint modules must end with a match_columns summary with key_takeaways")
        run, prev = 0, None
        for s in secs:
            n_sections += 1
            if not isinstance(s, dict):
                r.err(mw, "section must be an object")
                continue
            sw = f"{s.get('id', '?')}"
            for k in SECTION_REQUIRED:
                if k == "objectives" and s.get("task_type") == "match_columns" and s.get("key_takeaways"):
                    continue
                if not s.get(k):
                    r.err(sw, f"missing '{k}'")
            if s.get("id") in seen_ids:
                r.err(sw, "duplicate section id")
            seen_ids.add(s.get("id"))
            if "estimated_minutes" in s:
                em = s.get("estimated_minutes")
                if not (isinstance(em, (int, float)) and em > 0):
                    r.err(sw, "estimated_minutes must be a positive number")
            if not s.get("word_breakdown") and s.get("task_type") not in ("match_columns", "exam_app"):
                soft(sw, "missing word_breakdown (jargon buster)")
            _lint_cross_refs(r, sw, s.get("see_also"), course.get("course_id"), known_course_ids)
            _lint_task(r, sw, s, strict, str(course.get("archetype") or ""))
            _lint_style(r, sw, s)
            tt = s.get("task_type")
            run = run + 1 if tt == prev else 1
            prev = tt
            if run == _MAX_MONOTONY + 1:
                r.warn(mw, f"more than {_MAX_MONOTONY} sections in a row use '{tt}'")

    mc = [s["correct_index"] for m in modules if isinstance(m, dict) for s in m.get("sections", [])
          if isinstance(s, dict) and s.get("task_type") == "multiple_choice" and isinstance(s.get("correct_index"), int)]
    if len(mc) >= 8 and len(set(mc)) == 1:
        r.warn("course", "every multiple_choice answer sits in the same option slot")

    stats = compute_course_stats(course)
    score = max(0, 100 - 5 * len(r.errors) - 1 * len(r.warnings))
    return {
        "passed": not r.errors,
        "score": score,
        "errors": r.errors,
        "warnings": r.warnings,
        "stats": stats,
    }


def standard_text(archetype: str = "all") -> dict:
    """The spec an agent reads before drafting a course."""
    arch = ARCHETYPES if archetype in ("", "all", None) else {archetype: ARCHETYPES.get(archetype, {})}
    return {
        "name": "Siraugga Course Standard",
        "voice_rules": VOICE_RULES,
        "archetypes": arch,
        "themes": list(THEMES),
        "task_types": sorted(TASK_TYPES),
        "course_required": COURSE_REQUIRED,
        "module_required": MODULE_REQUIRED,
        "section_required": SECTION_REQUIRED,
        "optional_course_keys": ["badge_label", "sandbox_label", "academy_label", "related_courses"],
        "optional_section_keys": ["estimated_minutes", "see_also", "skip_reflection"],
        "dynamic_stats": {
            "explanation": (
                "Module counts, section counts, and estimated duration are computed dynamically by the player from courseData.modules "
                "and section task types (or optional estimated_minutes override). Do not hardcode static counts in copy to prevent count drift."
            ),
            "placeholders": ["{{module_count}}", "{{section_count}}", "{{estimated_duration}}"],
            "section_minutes_by_type": SECTION_MINUTES_BY_TYPE,
        },
        "cross_references": (
            "Plain text only, never links. related_courses: up to 5 course ids shown at the end as 'Check out these courses next'. "
            "see_also on a module or section: [{course_id, note}] shown as 'You will meet this again in: <course title> (<note>)'. "
            "Only reference topics the other course really teaches. The platform adds the CyberBrief advert itself."
        ),
        "notes": [
            "code_editor is the canonical editor type (file_path, code_checks); bicep_editor stays as an alias.",
            "match_columns summary sections use concept_heading 'Summary' and key_takeaways (2+).",
            "Module counts, section counts, and estimated duration are computed dynamically. Avoid hardcoding static counts in subtitles and summaries; use {{module_count}}, {{section_count}}, and {{estimated_duration}} placeholders instead to avoid count drift.",
            "Sections can specify an optional positive integer 'estimated_minutes' to override the default pacing.",
            "Same voice for every course; archetype and theme change the shape and colour only.",
        ],
    }
