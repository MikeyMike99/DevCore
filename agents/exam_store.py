"""
Server-side exam saving for every tier.

The agent never writes files to create an exam: it emits the exam JSON inside a
[SAVE_EXAM] ... [/SAVE_EXAM] block. This module validates it and saves it under an
unguessable name in sandbox/static/exams/, so users never overwrite each other's exams
and no tool access to the server is needed.
"""
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
FORMAT_SCRIPT = os.path.join(DEVCORE_ROOT, ".agents", "skills", "exam-generator", "scripts", "format_exam.py")
MAX_EXAM_BYTES = 512 * 1024
MAX_QUESTIONS = 300
KEEP_DAYS = 7

_BLOCK_RE = re.compile(r"\[SAVE_EXAM\]([\s\S]*?)\[/SAVE_EXAM\]", re.IGNORECASE)


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


def save_exam_blocks(text: str) -> list:
    """Save every [SAVE_EXAM] block in `text`. Returns [{ok, url, title, message}] per block."""
    results = []
    blocks = _BLOCK_RE.findall(text or "")
    if not blocks:
        return results
    os.makedirs(EXAMS_DIR, exist_ok=True)
    _cleanup_old()
    for raw in blocks[:5]:
        body = _strip_fences(raw)
        if len(body.encode("utf-8")) > MAX_EXAM_BYTES:
            results.append({"ok": False, "message": "The exam is too large to save (limit 512 KB)."})
            continue
        try:
            exam = json.loads(body)
        except Exception as e:
            results.append({"ok": False, "message": f"The exam was not valid JSON ({e.__class__.__name__})."})
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
        results.append({"ok": True, "url": url, "title": title, "message": note})
    return results


def render_results(results: list) -> str:
    """Markdown the chat shows after the agent's answer: a link and an embedded exam per saved block."""
    parts = []
    for r in results:
        if r.get("ok"):
            parts.append(
                f"📝 **Exam ready:** [{r['title']}]({r['url']})"
                + (f" ({r['message']})" if r.get("message") else "")
                + f'\n\n<iframe src="{r["url"]}" class="w-full aspect-video border-0 rounded-lg" allowfullscreen></iframe>'
            )
        else:
            parts.append(f"⚠️ **Exam not saved:** {r.get('message')}")
    return "\n\n".join(parts)
