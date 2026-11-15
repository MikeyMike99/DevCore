"""Git-first Cloudflare Pages build & deploy pipeline for Siraugga (mikeytech.dev).

Ensures Git (`origin/main`) is the central source of truth:
1. Stages and commits any local frontend changes to `main`.
2. Pulls (`--rebase --autostash`) from `origin/main` and pushes to `origin/main`.
3. Builds `dist/` strictly from the committed Git tree (`origin/main` / `HEAD`).
4. Deploys `dist/` to Cloudflare Pages via `npx wrangler deploy` when changed.
"""
import fcntl
import hashlib
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIST_DIR = ROOT / "dist"
ENV_FILE = ROOT / ".env.cloudflare"
CACHE_DIR = Path.home() / ".cache" / "devcore"
HASH_FILE = CACHE_DIR / "siraugga_pages_dist.sha256"
COMMIT_FILE = CACHE_DIR / "siraugga_pages_commit.sha"
LOCK_FILE = Path("/tmp/siraugga_pages_deploy.lock")
LOG_FILE = Path("/tmp/siraugga_pages_deploy.log")

FRONTEND_GIT_PATHS = [
    "sandbox/templates",
    "sandbox/static",
    "core/ui_config.json",
    "scripts/build_siraugga_pages.py",
    "scripts/deploy_siraugga_pages.py",
    "wrangler.jsonc",
    ".github/workflows/deploy-cloudflare-pages.yml",
]

_LAST_REMOTE_FETCH_TS = 0.0
REMOTE_FETCH_INTERVAL_SEC = 60.0

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _load_cf_env() -> tuple[dict, list[str]]:
    env = os.environ.copy()
    secrets = []
    if ENV_FILE.is_file():
        with open(ENV_FILE, "r", encoding="utf-8") as f:
            for line in f:
                s = line.strip()
                if not s or s.startswith("#") or "=" not in s:
                    continue
                k, v = s.split("=", 1)
                k = k.strip()
                v = v.strip().strip('"').strip("'")
                env[k] = v
                if v:
                    secrets.append(v)
    existing_wslenv = [p for p in env.get("WSLENV", "").split(":") if p]
    for var in ("CLOUDFLARE_API_TOKEN", "CLOUDFLARE_ACCOUNT_ID"):
        if var not in existing_wslenv:
            existing_wslenv.append(var)
    env["WSLENV"] = ":".join(existing_wslenv)
    return env, secrets


def _find_npx() -> str | None:
    found = shutil.which("npx")
    if found:
        return found
    win_npx = Path("/mnt/c/Program Files/nodejs/npx")
    if win_npx.is_file():
        return str(win_npx)
    return None


def _run_git(args: list[str], timeout: int = 30) -> tuple[int, str, str]:
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0", "GIT_EDITOR": "true"}
    try:
        res = subprocess.run(
            ["git", *args],
            cwd=str(ROOT),
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        return res.returncode, (res.stdout or "").strip(), (res.stderr or "").strip()
    except Exception as e:
        return 1, "", str(e)


def _git_rev(ref: str) -> str:
    rc, out, _ = _run_git(["rev-parse", ref], timeout=10)
    return out if rc == 0 else ""


def sync_git_source_of_truth(commit_message: str | None = None) -> dict:
    """Synchronize local frontend changes with origin/main so Git is the central source of truth."""
    if not (ROOT / ".git").exists():
        return {"ok": False, "error": "Not a git repository", "ref": None, "sha": ""}

    rc_st, st_out, _ = _run_git(["status", "--porcelain", "--", *FRONTEND_GIT_PATHS])
    committed_local = False
    if rc_st == 0 and st_out:
        _run_git(["add", "--", *FRONTEND_GIT_PATHS])
        rc_diff, _, _ = _run_git(["diff", "--cached", "--quiet", "--", *FRONTEND_GIT_PATHS])
        if rc_diff != 0:
            msg = (commit_message or "chore(pages): sync Siraugga frontend to origin/main").strip()
            rc_cm, out_cm, err_cm = _run_git(["commit", "-m", msg, "--", *FRONTEND_GIT_PATHS])
            if rc_cm == 0:
                committed_local = True
                _append_log(f"git commit frontend changes: {msg}")
            else:
                _append_log(f"git commit notice: {err_cm or out_cm}")

    rc_fetch, _, err_fetch = _run_git(["fetch", "origin", "main"], timeout=25)
    if rc_fetch != 0:
        _append_log(f"git fetch origin main warning: {err_fetch}")

    head_sha = _git_rev("HEAD")
    origin_sha = _git_rev("origin/main")

    if origin_sha and head_sha and origin_sha != head_sha:
        rc_anc, _, _ = _run_git(["merge-base", "--is-ancestor", "origin/main", "HEAD"])
        if rc_anc != 0:
            rc_pull, out_pull, err_pull = _run_git(
                ["pull", "--rebase", "--autostash", "origin", "main"],
                timeout=45,
            )
            if rc_pull != 0:
                _run_git(["rebase", "--abort"])
                _append_log(f"git pull --rebase warning: {err_pull or out_pull}")
            else:
                _append_log("git pull --rebase origin main succeeded")
            head_sha = _git_rev("HEAD")
            origin_sha = _git_rev("origin/main")

        if head_sha and origin_sha and head_sha != origin_sha:
            rc_push, out_push, err_push = _run_git(["push", "origin", "HEAD:main"], timeout=45)
            if rc_push == 0:
                _append_log(f"git push origin HEAD:main ({head_sha[:12]})")
                origin_sha = _git_rev("origin/main") or head_sha
            else:
                _append_log(f"git push warning: {err_push or out_push}")

    target_ref = "origin/main" if origin_sha and origin_sha == head_sha else ("HEAD" if head_sha else None)
    target_sha = origin_sha if target_ref == "origin/main" else head_sha
    return {
        "ok": bool(target_ref),
        "ref": target_ref,
        "sha": target_sha,
        "head": head_sha,
        "origin_main": origin_sha,
        "committed_local": committed_local,
        "synced_with_origin": bool(head_sha and origin_sha and head_sha == origin_sha),
    }


def compute_dist_hash(dist_dir: Path = DIST_DIR) -> str:
    h = hashlib.sha256()
    if not dist_dir.is_dir():
        return ""
    paths = sorted(p for p in dist_dir.rglob("*") if p.is_file())
    for p in paths:
        rel = p.relative_to(dist_dir).as_posix()
        h.update(rel.encode("utf-8"))
        h.update(b"\0")
        with open(p, "rb") as f:
            while True:
                chunk = f.read(65536)
                if not chunk:
                    break
                h.update(chunk)
        h.update(b"\0")
    return h.hexdigest()


def watched_inputs_signature() -> str:
    """Signature combining Git refs (HEAD + periodic origin/main check) and working-tree frontend inputs."""
    global _LAST_REMOTE_FETCH_TS
    from scripts import build_siraugga_pages as builder

    now = time.time()
    if now - _LAST_REMOTE_FETCH_TS >= REMOTE_FETCH_INTERVAL_SEC:
        _LAST_REMOTE_FETCH_TS = now
        _run_git(["fetch", "origin", "main"], timeout=15)

    h = hashlib.sha256()
    records = [
        f"git:HEAD:{_git_rev('HEAD')}",
        f"git:origin/main:{_git_rev('origin/main')}",
    ]

    candidates = [
        ROOT / "wrangler.jsonc",
        ROOT / "scripts" / "build_siraugga_pages.py",
        builder.UI_CONFIG_PATH,
    ]
    for src_name, _ in builder.PAGES:
        candidates.append(builder.TEMPLATES_DIR / src_name)
    for fname in sorted(builder.PUBLIC_STATIC_FILES):
        candidates.append(builder.STATIC_SRC / fname)

    for p in candidates:
        if p.is_file():
            st = p.stat()
            records.append(f"{p.relative_to(ROOT).as_posix()}:{st.st_mtime_ns}:{st.st_size}")

    for dname in sorted(builder.PUBLIC_STATIC_DIRS):
        dpath = builder.STATIC_SRC / dname
        if not dpath.is_dir():
            continue
        for root, dirs, files in os.walk(dpath):
            dirs[:] = sorted(d for d in dirs if d not in builder.SKIP_STATIC_DIRS)
            for fname in sorted(files):
                fpath = Path(root) / fname
                try:
                    st = fpath.stat()
                    if st.st_size <= builder.CF_PAGES_MAX_FILE_BYTES:
                        records.append(f"{fpath.relative_to(ROOT).as_posix()}:{st.st_mtime_ns}:{st.st_size}")
                except OSError:
                    continue

    h.update("\n".join(sorted(records)).encode("utf-8"))
    return h.hexdigest()


def _append_log(line: str) -> None:
    try:
        ts = time.strftime("%Y-%m-%d %H:%M:%S")
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"[{ts}] {line}\n")
    except Exception:
        pass


def sync_siraugga_pages(force: bool = False, commit_message: str | None = None) -> dict:
    """Sync with Git (origin/main), build dist/ from committed Git state, and deploy to Cloudflare Pages."""
    import importlib
    from scripts import build_siraugga_pages as builder
    importlib.reload(builder)

    LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(LOCK_FILE, "w", encoding="utf-8") as lock_fh:
        fcntl.flock(lock_fh.fileno(), fcntl.LOCK_EX)
        try:
            git_info = sync_git_source_of_truth(commit_message=commit_message)
            git_ref = git_info.get("ref")
            git_sha = git_info.get("sha", "")

            rc = builder.main(git_ref=git_ref)
            if rc != 0:
                return {"ok": False, "deployed": False, "error": f"build_siraugga_pages exited with {rc}"}

            digest = compute_dist_hash()
            prev = ""
            if HASH_FILE.is_file():
                try:
                    prev = HASH_FILE.read_text(encoding="utf-8").strip()
                except OSError:
                    prev = ""

            if not force and prev == digest:
                return {
                    "ok": True,
                    "deployed": False,
                    "reason": "unchanged",
                    "hash": digest,
                    "git_ref": git_ref,
                    "git_sha": git_sha,
                    "synced_with_origin": git_info.get("synced_with_origin", False),
                }

            if not ENV_FILE.is_file():
                msg = "Missing .env.cloudflare; skipping local Cloudflare Pages deploy (GitHub Actions will deploy from origin/main)."
                _append_log(msg)
                return {
                    "ok": True,
                    "deployed": False,
                    "reason": "git_pushed_only",
                    "hash": digest,
                    "git_ref": git_ref,
                    "git_sha": git_sha,
                }

            npx_bin = _find_npx()
            if not npx_bin:
                msg = "npx binary not found; cannot run local Cloudflare Pages deploy."
                _append_log(msg)
                return {"ok": False, "deployed": False, "error": msg}

            env, secrets = _load_cf_env()
            res = subprocess.run(
                [npx_bin, "--yes", "wrangler", "deploy"],
                cwd=str(ROOT),
                env=env,
                capture_output=True,
                text=True,
                timeout=600,
            )
            out = (res.stdout or "") + "\n" + (res.stderr or "")
            for s in secrets:
                out = out.replace(s, "<REDACTED>")
            tail = "\n".join(out.strip().splitlines()[-15:])
            _append_log(f"wrangler deploy rc={res.returncode} git={git_sha[:12]} hash={digest[:12]}\n{tail}")

            if res.returncode != 0:
                return {"ok": False, "deployed": False, "error": tail or f"wrangler exited {res.returncode}"}

            CACHE_DIR.mkdir(parents=True, exist_ok=True)
            HASH_FILE.write_text(digest + "\n", encoding="utf-8")
            if git_sha:
                COMMIT_FILE.write_text(git_sha + "\n", encoding="utf-8")
            return {
                "ok": True,
                "deployed": True,
                "hash": digest,
                "git_ref": git_ref,
                "git_sha": git_sha,
                "synced_with_origin": git_info.get("synced_with_origin", False),
                "output": tail,
            }
        finally:
            fcntl.flock(lock_fh.fileno(), fcntl.LOCK_UN)


if __name__ == "__main__":
    force_flag = "--force" in sys.argv[1:]
    commit_msg_arg = None
    if "--message" in sys.argv[1:]:
        idx = sys.argv[1:].index("--message")
        if idx + 1 < len(sys.argv[1:]):
            commit_msg_arg = sys.argv[1:][idx + 1]
    result = sync_siraugga_pages(force=force_flag, commit_message=commit_msg_arg)
    print(result)
    raise SystemExit(0 if result.get("ok") else 1)
