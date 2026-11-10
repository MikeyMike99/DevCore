"""
Per-user exam content folders.

Every user (any tier) gets a private folder of study material for the Exam Generator.
Files are uploaded through the server, stored as extracted text, and handed to that
user's own agent as text. The agent never reads the disk, and users never see each
other's files.
"""
import hashlib
import json
import os
import re
import time

DEVCORE_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONTENT_ROOT = os.path.join(DEVCORE_ROOT, "data", "exam_content")
MAX_FILES = 20
MAX_FILE_CHARS = 150_000
PROMPT_CHAR_BUDGET = 150_000
KEEP_DAYS = 30

_EXAM_WORDS = re.compile(r"\b(exam|exams|quiz|quizzes|test|tests|assessment|content folder|my content|my files|my folder|my material|my notes|my documents?)\b", re.IGNORECASE)


def _user_dir(user_id: str) -> str:
    digest = hashlib.sha256((user_id or "guest").encode("utf-8")).hexdigest()[:32]
    return os.path.join(CONTENT_ROOT, digest)


def _safe_name(name: str) -> str:
    base = os.path.basename(name or "document").strip()
    base = re.sub(r"[^A-Za-z0-9._ -]", "_", base)[:100].strip(" .") or "document"
    return base


def _cleanup(folder: str) -> None:
    cutoff = time.time() - KEEP_DAYS * 86400
    try:
        for f in os.listdir(folder):
            p = os.path.join(folder, f)
            if os.path.isfile(p) and os.path.getmtime(p) < cutoff:
                os.remove(p)
    except Exception:
        pass


def list_files(user_id: str) -> list:
    folder = _user_dir(user_id)
    if not os.path.isdir(folder):
        return []
    _cleanup(folder)
    items = []
    for f in sorted(os.listdir(folder)):
        if not f.endswith(".json"):
            continue
        try:
            with open(os.path.join(folder, f), "r", encoding="utf-8") as fh:
                meta = json.load(fh)
            items.append({"id": f[:-5], "name": meta.get("name"), "chars": len(meta.get("text", "")), "added": meta.get("added")})
        except Exception:
            continue
    return items


def add_file(user_id: str, name: str, text: str) -> dict:
    folder = _user_dir(user_id)
    os.makedirs(folder, exist_ok=True)
    _cleanup(folder)
    if len(list_files(user_id)) >= MAX_FILES:
        raise ValueError(f"Your content folder is full ({MAX_FILES} files). Delete a file first.")
    safe = _safe_name(name)
    file_id = hashlib.sha256(f"{safe}:{time.time()}".encode()).hexdigest()[:16]
    record = {"name": safe, "text": (text or "")[:MAX_FILE_CHARS], "added": time.strftime("%Y-%m-%d %H:%M")}
    with open(os.path.join(folder, f"{file_id}.json"), "w", encoding="utf-8") as fh:
        json.dump(record, fh, ensure_ascii=False)
    return {"id": file_id, "name": safe, "chars": len(record["text"]), "added": record["added"]}


def delete_file(user_id: str, file_id: str) -> bool:
    if not re.fullmatch(r"[0-9a-f]{16}", file_id or ""):
        return False
    path = os.path.join(_user_dir(user_id), f"{file_id}.json")
    if os.path.isfile(path):
        os.remove(path)
        return True
    return False


def documents_for_prompt(user_id: str, prompt: str) -> str:
    """The user's own folder as <ATTACHED_DOCUMENT> blocks, when their prompt is about exams or their content."""
    if not prompt or not _EXAM_WORDS.search(prompt):
        return ""
    folder = _user_dir(user_id)
    if not os.path.isdir(folder):
        return ""
    parts, used = [], 0
    for item in list_files(user_id):
        try:
            with open(os.path.join(folder, f"{item['id']}.json"), "r", encoding="utf-8") as fh:
                rec = json.load(fh)
        except Exception:
            continue
        text = re.sub(r"</?ATTACHED_DOCUMENT[^>]*>", "", rec.get("text", ""), flags=re.IGNORECASE)
        room = PROMPT_CHAR_BUDGET - used
        if room <= 0:
            break
        text = text[:room]
        used += len(text)
        name = str(rec.get("name", "document")).replace('"', "")
        parts.append(f'<ATTACHED_DOCUMENT name="{name}" source="content folder">\n{text}\n</ATTACHED_DOCUMENT>')
    if not parts:
        return ""
    return "\n\n[The user's exam content folder]\n" + "\n\n".join(parts)


def is_exam_request(prompt: str) -> bool:
    if not prompt:
        return False
    low = prompt.lower().strip()
    # Ticket requests ("create a ticket: the exam page is broken", "ticket to test X") are about
    # reporting a problem, not building an exam: no exam builder, no exam brief, no free prompt.
    if "[save_exam]" not in low and re.search(r"\b(tickets?|bug\s+reports?|report\s+a\s+(bug|problem|issue))\b", low):
        return False
    if any(k in low for k in ("[save_exam]", "/plugin/exam", "exam_builder", "help exam", "quiz guide", "exam guide", "/exam")):
        return True
    if re.search(r"\b(exam|exams|quiz|quizzes|assessment|assessments|questionnaire)\b", low):
        return True
    if re.search(r"\b(test|quiz|examine)\s+(me|my\s+knowledge)\b", low):
        return True
    if re.search(r"\b(practice\s+test|mock\s+test|diagnostic\s+test)\b", low):
        return True
    if re.search(r"\b(unit\s+test|pytest|test\s+case|integration\s+test|test_[\w]+)\b", low):
        return False
    if re.search(r"\b(create|make|generate|build|give\s+me|prepare|write)\b.*?\b(test|multiple\s+choice\s+questions?|study\s+questions?)\b", low):
        return True
    return False

