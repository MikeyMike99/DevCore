"""
In-game / app developer workspaces.

A developer is handed work by the Super Admin (or the project's admin) with an access link that
names ONE project and the PARTS (folders or files inside it) they may change. They never get raw
access and never see code or the project's structure:

  * Their agent works in a private SANDBOX copy of the project (playground/.dev_sandboxes/...),
    never in the real project. It may read the whole copy to understand it, but may only change
    files inside the assigned parts (enforced on every tool call, see execution_mixin).
  * Everything sent to the developer's screen passes scrub_message(): code blocks, inline code,
    file names, paths and tool details are removed, so the agent cannot show code even if it
    tried to.
  * Finished work is submitted for approval; only changes inside the assigned parts can ever
    reach the real project.
"""
import fnmatch
import hashlib
import os
import re
import shutil
import time
from pathlib import Path

DEVCORE_ROOT = Path(__file__).resolve().parent.parent
PLAYGROUND = DEVCORE_ROOT / "playground"
SANDBOX_ROOT = PLAYGROUND / ".dev_sandboxes"
DEV_ROLES = {"gamedev", "dev", "developer"}

# Never copied into a sandbox (secrets, VCS, caches, environments).
_SKIP_DIRS = {".git", "__pycache__", "node_modules", "venv", ".venv", ".virtualenvs", ".ssh", ".gnupg",
              ".aws", ".config", ".gemini", ".claude", ".cache", ".local", ".dev_sandboxes"}
_SKIP_FILES = ("*.env", ".env", ".env.*", "*.key", "*.pem", "*.pfx", "*.p12", "*.kdbx", "*.vault", "*.vault.*",
               "*vault_store*", "*secret*", "*token*", "*password*", "*credential*", "id_rsa*", "id_ed25519*",
               "keys.json", "sessions.json")


# ---- who is a developer ------------------------------------------------------------------------
def is_dev(user) -> bool:
    return bool(isinstance(user, dict) and str(user.get("role") or "").lower() in DEV_ROLES
                and user.get("dev_project"))


def clean_parts(project: str, parts) -> list:
    """Validate the assigned parts: relative paths inside the project, existing. [] = whole project."""
    if isinstance(parts, str):
        parts = [p for p in re.split(r"[,\n]+", parts)]
    out = []
    base = (PLAYGROUND / project).resolve()
    for p in parts or []:
        p = str(p).strip().strip("/\\").replace("\\", "/")
        if not p:
            continue
        if p.startswith(("/", "~")) or ".." in p.split("/") or ":" in p:
            raise ValueError(f"'{p}' must be a folder or file inside the project.")
        target = (base / p).resolve()
        if not str(target).startswith(str(base) + os.sep) or not target.exists():
            raise ValueError(f"'{p}' doesn't exist in that project.")
        out.append(p)
    return sorted(set(out))


def _dev_id(user) -> str:
    who = str(user.get("key_id") or user.get("username") or "dev")
    slug = re.sub(r"[^a-z0-9]+", "-", who.lower()).strip("-")[:32] or "dev"
    return f"{slug}-{hashlib.sha256(who.encode()).hexdigest()[:8]}"


# ---- the sandbox copy --------------------------------------------------------------------------
def sandbox_path(user) -> Path:
    return SANDBOX_ROOT / _dev_id(user) / str(user["dev_project"])


def _ignore(directory, names):
    skip = []
    for n in names:
        full = os.path.join(directory, n)
        if os.path.isdir(full) and (n in _SKIP_DIRS or n.startswith(".dev_")):
            skip.append(n)
        elif any(fnmatch.fnmatch(n.lower(), g) for g in _SKIP_FILES):
            skip.append(n)
    return skip


def ensure_sandbox(user, refresh: bool = False) -> Path:
    """The developer's private copy of their project (made on first use; refresh re-copies it)."""
    project = str(user["dev_project"])
    src = PLAYGROUND / project
    if not src.is_dir() or project.startswith(".") or "/" in project or "\\" in project:
        raise ValueError("The assigned project doesn't exist any more.")
    dst = sandbox_path(user)
    if refresh and dst.exists():
        shutil.rmtree(dst)
    if not dst.exists():
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(src, dst, ignore=_ignore)
        (dst.parent / ".copied_at").write_text(str(time.time()), encoding="utf-8")
    return dst


def _inside(path: Path, base: Path) -> bool:
    try:
        path.resolve().relative_to(base.resolve())
        return True
    except ValueError:
        return False


def check_tool_path(user, path: str, writing: bool) -> None:
    """Raise PermissionError unless `path` is inside the developer's sandbox, and (when writing)
    inside one of their assigned parts."""
    box = sandbox_path(user)
    p = Path(path)
    if not p.is_absolute():
        p = box / p
    if not _inside(p, box):
        raise PermissionError("Developers work only inside their sandbox copy of the project.")
    if writing:
        parts = user.get("dev_parts") or []
        if parts and not any(_inside(p, box / part) for part in parts):
            raise PermissionError("That part of the project wasn't handed to this developer. Only the assigned parts may be changed.")


# ---- never show code ---------------------------------------------------------------------------
_HIDDEN = "[code hidden]"
# One linear pass over "word-like" tokens; each token is then judged by plain string checks.
# (A nested-repetition path regex took seconds on 20 KB of text and froze the whole server.)
_TOKEN_RE = re.compile(r"[\w.\-~:\\/]+")
_CODE_EXTS = {"py", "js", "ts", "jsx", "tsx", "mjs", "htm", "html", "css", "json", "yml", "yaml", "toml", "ini", "cfg",
              "lua", "cs", "cpp", "c", "h", "hpp", "java", "kt", "go", "rs", "rb", "php", "sh", "ps1", "sql", "md",
              "xml", "gd", "shader", "glsl"}
_INLINE_RE = re.compile(r"`[^`\n]{1,500}`")
_MAX_TEXT = 20000           # longer text sent to a developer (e.g. raw tool output) is hidden outright


def _token(m):
    tok = m.group(0)
    core = tok.strip(".:-~")
    if ("/" in core or "\\" in core) and any(ch.isalnum() for ch in core):
        return "[file]"                                   # a/b/c, C:\x\y, /mnt/..., ./x
    stem, dot, ext = core.rpartition(".")
    if dot and stem and ext.lower() in _CODE_EXTS:
        return "[file]"                                   # player.py, menu.js
    return tok


def scrub_text(text: str) -> str:
    """Remove code and structure from a complete piece of text (linear time)."""
    if not isinstance(text, str) or not text:
        return text
    if len(text) > _MAX_TEXT:
        return "[long technical output hidden]"
    text = re.sub(r"```.*?(?:```|$)", _HIDDEN, text, flags=re.S)
    text = _INLINE_RE.sub("[code]", text)
    return _TOKEN_RE.sub(_token, text)


class StreamScrubber:
    """Stateful version for streamed chunks: a code block may start in one chunk and end later."""

    def __init__(self):
        self.in_fence = False
        self.carry = ""

    def feed(self, chunk: str) -> str:
        text = self.carry + (chunk or "")
        self.carry = ""
        # keep a trailing partial fence marker (` or ``) for the next chunk
        m = re.search(r"`{1,2}$", text)
        if m:
            self.carry, text = m.group(0), text[:m.start()]
        out = []
        while text:
            idx = text.find("```")
            if idx < 0:
                if not self.in_fence:
                    out.append(text)
                break
            if not self.in_fence:
                out.append(text[:idx])
                out.append(_HIDDEN)
            self.in_fence = not self.in_fence
            text = text[idx + 3:]
        return scrub_text("".join(out))


_SENSITIVE_KEYS = {"parameters", "params", "tool_info", "raw", "diff", "patch", "code", "content", "path",
                   "paths", "file", "files", "target_file", "command", "cmd", "cwd", "stdout", "stderr"}


def _scrub_obj(obj):
    if isinstance(obj, str):
        return scrub_text(obj)
    if isinstance(obj, list):
        return [_scrub_obj(x) for x in obj]
    if isinstance(obj, dict):
        return {k: _scrub_obj(v) for k, v in obj.items() if str(k).lower() not in _SENSITIVE_KEYS}
    return obj


_scrubbers = {}       # owner -> StreamScrubber (one per running task)


def scrub_message(msg: dict, owner: str) -> dict:
    """What a developer's screen may receive. Runs for every message of a developer's task."""
    t = msg.get("type")
    if t == "agent_chunk":
        s = _scrubbers.setdefault(owner, StreamScrubber())
        return {**msg, "chunk": s.feed(msg.get("chunk") or "")}
    if t in ("agent_done", "agent_stop"):
        _scrubbers.pop(owner, None)
    if "action" in msg:                          # tool steps: never their inputs or outputs
        act = msg.get("action") or {}
        label = "Checking the project" if t == "action_start" else "Step finished"
        msg = {**msg, "action": {"announcement": label, "friendly_name": label,
                                 "status": act.get("status") if isinstance(act, dict) else None}}
    return _scrub_obj(msg)
