"""
Server-side exam and interactive course saving.

Exams can be saved by every tier. Creating a course needs Tier 2 or higher (the Tier 5 super admin
always qualifies); Tier 1 and unknown users are refused. Each course records a hashed owner, and only
that owner or the super admin may overwrite it: a clashing course_id from anyone else gets a new id.
"""
import hashlib
import json
import os
import re
import secrets
import subprocess
import sys
import time
from urllib.parse import quote

DEVCORE_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXAMS_DIR = os.path.join(DEVCORE_ROOT, "sandbox", "static", "exams")
COURSES_DIR = os.path.join(DEVCORE_ROOT, "sandbox", "static", "courses")
FORMAT_SCRIPT = os.path.join(DEVCORE_ROOT, ".agents", "skills", "exam-generator", "scripts", "format_exam.py")
MAX_EXAM_BYTES = 512 * 1024
MAX_QUESTIONS = 300
KEEP_DAYS = 7
COURSE_CREATOR_MIN_TIER = 2
COURSE_TIER_MESSAGE = (
    "Creating your own course needs a Tier 2 account or higher. You can still take the courses on "
    "Siraugga, and I can make you an exam on this topic instead - just ask."
)


def creator_tier(creator: dict = None, is_admin: bool = False) -> int:
    if is_admin:
        return 5
    from agents.tier_limits import get_tier_for_user
    return get_tier_for_user(creator or {})


def _owner_ref(creator: dict, tier: int) -> str:
    if tier >= 5:
        return "super-admin"
    ident = str((creator or {}).get("username") or (creator or {}).get("name") or "")
    return hashlib.sha256(("course-owner:" + ident).encode("utf-8")).hexdigest()[:16] if ident else ""


def _existing_owner(course_id: str):
    """Owner of an existing course with this id, '' for a legacy course with no owner, None if new."""
    for out_dir in (COURSES_DIR, os.path.join(DEVCORE_ROOT, "sandbox", "static")):
        path = os.path.join(out_dir, f"{course_id}.json")
        if os.path.isfile(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    return str(json.load(f).get("_owner") or "")
            except Exception:
                return ""
    return None

_BLOCK_RE = re.compile(r"\[SAVE_(?:EXAM|COURSE)\]([\s\S]*?)\[/SAVE_(?:EXAM|COURSE)\]", re.IGNORECASE)


def _strip_fences(body: str) -> str:
    body = body.strip()
    m = re.match(r"^```(?:json)?\s*([\s\S]*?)\s*```$", body)
    return m.group(1).strip() if m else body


FEATURED_FILE = os.path.join(DEVCORE_ROOT, "sandbox", "static", "featured_exam.json")


def _featured_name() -> str:
    """File name of the exam shown to every visitor, which must survive cleanup."""
    try:
        with open(FEATURED_FILE, "r", encoding="utf-8") as f:
            return os.path.basename(str(json.load(f).get("quiz") or ""))
    except Exception:
        return ""


def _cleanup_old() -> None:
    cutoff = time.time() - KEEP_DAYS * 86400
    keep = _featured_name()
    try:
        for name in os.listdir(EXAMS_DIR):
            path = os.path.join(EXAMS_DIR, name)
            if name == keep:
                continue
            if name.endswith(".json") and os.path.isfile(path) and os.path.getmtime(path) < cutoff:
                os.remove(path)
    except Exception:
        pass


def save_exam_blocks(text: str, creator: dict = None, is_admin: bool = False) -> list:
    """Save every [SAVE_EXAM] or [SAVE_COURSE] block in `text`. Returns [{ok, url, title, message, kind}] per block.
    `creator`/`is_admin` identify who asked; without them courses are refused (fail closed)."""
    results = []
    tier = creator_tier(creator, is_admin)
    blocks = _BLOCK_RE.findall(text or "")
    if not blocks:
        return results
    os.makedirs(EXAMS_DIR, exist_ok=True)
    os.makedirs(COURSES_DIR, exist_ok=True)
    _cleanup_old()
    for raw in blocks[:5]:
        body = _strip_fences(raw)
        if len(body.encode("utf-8")) > MAX_EXAM_BYTES:
            results.append({"ok": False, "message": "The payload is too large to save (limit 512 KB)."})
            continue
        try:
            exam = json.loads(body)
        except Exception as e:
            results.append({"ok": False, "message": f"The payload was not valid JSON ({e.__class__.__name__})."})
            continue

        if isinstance(exam, dict) and (exam.get("mode") == "course" or isinstance(exam.get("modules"), list)):
            if tier < COURSE_CREATOR_MIN_TIER:
                results.append({"ok": False, "kind": "course", "message": COURSE_TIER_MESSAGE})
                continue
            title = str(exam.get("title") or "Interactive Course").strip()[:120] or "Interactive Course"
            owner = _owner_ref(creator, tier)
            course_id = str(exam.get("course_id") or "").strip()
            course_id = re.sub(r"[^A-Za-z0-9_.-]", "", course_id) or secrets.token_urlsafe(10)
            current_owner = _existing_owner(course_id)
            if current_owner is not None and tier < 5 and (not owner or current_owner != owner):
                course_id = secrets.token_urlsafe(10)
            exam["course_id"] = course_id
            exam["_owner"] = owner
            for out_dir in (COURSES_DIR, os.path.join(DEVCORE_ROOT, "sandbox", "static")):
                try:
                    with open(os.path.join(out_dir, f"{course_id}.json"), "w", encoding="utf-8") as f:
                        json.dump(exam, f, ensure_ascii=False, indent=2)
                except Exception:
                    pass
            url = f"/plugin/course?course={quote(course_id)}&title={quote(title)}"
            results.append({"ok": True, "url": url, "title": title, "message": "", "kind": "course"})
            continue

        if isinstance(exam, list):
            exam = {"questions": exam}
        questions = exam.get("questions") if isinstance(exam, dict) else None
        if not isinstance(questions, list) or not questions:
            results.append({"ok": False, "message": "The exam has no questions."})
            continue
        if len(questions) > MAX_QUESTIONS:
            results.append({"ok": False, "message": f"The exam has too many questions (limit {MAX_QUESTIONS})."})
            continue
        title = str(exam.get("title") or "Exam").strip()[:120] or "Exam"
        exam_id = secrets.token_urlsafe(12)
        path = os.path.join(EXAMS_DIR, f"{exam_id}.json")
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(exam, f, ensure_ascii=False)
        except Exception as e:
            results.append({"ok": False, "message": f"Could not save the exam: {e}"})
            continue
        note = ""
        if os.path.isfile(FORMAT_SCRIPT):
            try:
                r = subprocess.run([sys.executable, FORMAT_SCRIPT, path], capture_output=True, text=True, timeout=30)
                if r.returncode != 0:
                    note = "Saved; some questions may need checking."
            except Exception:
                note = "Saved; the format check was skipped."
        url = f"/plugin/exam?quiz=exams/{exam_id}.json&title={quote(title)}"
        results.append({"ok": True, "url": url, "title": title, "message": note, "kind": "exam"})
    return results


def render_results(results: list) -> str:
    """Markdown the chat shows after the agent's answer: a link and an embedded exam or course per saved block."""
    parts = []
    for r in results:
        if r.get("ok"):
            if r.get("kind") == "course":
                parts.append(
                    f"🎓 **Interactive Course ready:** [{r['title']}]({r['url']})"
                    + (f" ({r['message']})" if r.get("message") else "")
                    + f'\n\n<iframe src="{r["url"]}" class="w-full min-h-[780px] border-0 rounded-lg shadow-xl" allowfullscreen title="{r["title"]}"></iframe>'
                )
            else:
                parts.append(
                    f"📝 **Exam ready:** [{r['title']}]({r['url']})"
                    + (f" ({r['message']})" if r.get("message") else "")
                    + f'\n\n<iframe src="{r["url"]}" class="w-full aspect-video border-0 rounded-lg" allowfullscreen></iframe>'
                )
        else:
            parts.append(f"⚠️ **Not saved:** {r.get('message')}")
    return "\n\n".join(parts)
