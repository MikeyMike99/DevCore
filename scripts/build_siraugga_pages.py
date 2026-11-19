"""Build the static Cloudflare Pages bundle for Siraugga (https://mikeytech.dev).

Renders index.html and supporting templates with default UI strings from
core/ui_config.json, copies sandbox/static/ assets (skipping files over
Cloudflare Pages' 25 MiB per-file limit), and writes _headers, _redirects,
robots.txt, and 404.html into dist/.

Supports building directly from a committed Git ref (--git-ref origin/main or HEAD)
so Git remains the single source of truth for all frontend deployments.
"""
import io
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path
from jinja2 import Environment, FileSystemLoader

ROOT = Path(__file__).resolve().parent.parent
TEMPLATES_DIR = ROOT / "sandbox" / "templates"
STATIC_SRC = ROOT / "sandbox" / "static"
UI_CONFIG_PATH = ROOT / "core" / "ui_config.json"
OUT = ROOT / "dist"

CF_PAGES_MAX_FILE_BYTES = 24 * 1024 * 1024

PAGES = [
    ("index.html", "index.html"),
    ("terms.html", "terms.html"),
    ("setup.html", "setup.html"),
]

PUBLIC_STATIC_FILES = {
    "siraugga-origin.js",
    "device-keys.js",
    "device-keys-ui.js",
    "course-tailor-crypto.js",
    "card-recorder.js",
}
PUBLIC_STATIC_DIRS = {"sounds", "speech", "help"}
SKIP_STATIC_DIRS = {"scratch", "__pycache__", ".git", "exams", "courses"}

GIT_ARCHIVE_PATHS = [
    "sandbox/templates",
    "sandbox/static",
    "core/ui_config.json",
    "security/guest_session.py",
]


def _terms_version() -> str:
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    try:
        from security import guest_session
        return str(getattr(guest_session, "TERMS_VERSION", "2026-11"))
    except Exception:
        return "2026-11"


def _build_headers() -> str:
    csp = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' 'wasm-unsafe-eval' "
        "https://siraugga.mikeytech.dev "  # the speech engine (static/speech/vendor) is served by the live server, see _redirects
        "https://cdn.tailwindcss.com https://cdn.jsdelivr.net https://unpkg.com "
        "https://www.youtube.com https://s.ytimg.com https://static.cloudflareinsights.com; "
        "worker-src 'self'; "
        "media-src 'self' blob: data: https://siraugga.mikeytech.dev; "
        "frame-src 'self' https://siraugga.mikeytech.dev "
        "http://localhost:5055 http://127.0.0.1:5055 http://localhost:5050 http://127.0.0.1:5050 "
        "https://www.youtube.com https://www.youtube-nocookie.com; "
        "connect-src 'self' https://siraugga.mikeytech.dev wss://siraugga.mikeytech.dev "
        "ws: wss: https://generativelanguage.googleapis.com http://127.0.0.1:5000; "
        "style-src 'self' 'unsafe-inline' https://cdn.tailwindcss.com https://fonts.googleapis.com https://cdnjs.cloudflare.com; "
        "font-src 'self' data: https://fonts.gstatic.com https://cdnjs.cloudflare.com; "
        "img-src 'self' data: https: https://i.ytimg.com;"
    )
    perm = (
        'geolocation=(), microphone=(self), camera=(), '
        'publickey-credentials-create=(self "http://localhost:5055" "http://127.0.0.1:5055" "http://localhost:5050" "http://127.0.0.1:5050"), '
        'publickey-credentials-get=(self "http://localhost:5055" "http://127.0.0.1:5055" "http://localhost:5050" "http://127.0.0.1:5050")'
    )
    return (
        "/*\n"
        "  X-Frame-Options: SAMEORIGIN\n"
        "  X-Content-Type-Options: nosniff\n"
        "  Referrer-Policy: strict-origin-when-cross-origin\n"
        f"  Content-Security-Policy: {csp}\n"
        f"  Permissions-Policy: {perm}\n"
        "\n"
        "/static/*\n"
        "  Cache-Control: public, max-age=3600\n"
    )


def _copy_static(src: Path, dst: Path, base_root: Path = ROOT) -> list:
    skipped = []
    dst.mkdir(parents=True, exist_ok=True)
    for fname in sorted(PUBLIC_STATIC_FILES):
        fpath = src / fname
        if fpath.is_file():
            if fpath.stat().st_size > CF_PAGES_MAX_FILE_BYTES:
                skipped.append(str(fpath.relative_to(base_root)))
            else:
                shutil.copy2(fpath, dst / fname)
    for dname in sorted(PUBLIC_STATIC_DIRS):
        dsrc = src / dname
        if not dsrc.is_dir():
            continue
        for root, dirs, files in os.walk(dsrc):
            dirs[:] = [d for d in dirs if d not in SKIP_STATIC_DIRS]
            rel = Path(root).relative_to(src)
            target_dir = dst / rel
            target_dir.mkdir(parents=True, exist_ok=True)
            for fname in files:
                fpath = Path(root) / fname
                if fpath.stat().st_size > CF_PAGES_MAX_FILE_BYTES:
                    skipped.append(str(fpath.relative_to(base_root)))
                    continue
                shutil.copy2(fpath, target_dir / fname)
    return skipped


def _extract_git_ref_tree(git_ref: str, dest_dir: Path) -> None:
    res = subprocess.run(
        ["git", "archive", "--format=tar", git_ref, "--", *GIT_ARCHIVE_PATHS],
        cwd=str(ROOT),
        capture_output=True,
        check=True,
        timeout=60,
    )
    with tarfile.open(fileobj=io.BytesIO(res.stdout), mode="r:") as tf:
        try:
            tf.extractall(path=str(dest_dir), filter="data")
        except TypeError:
            tf.extractall(path=str(dest_dir))


def build_bundle(source_root: Path = ROOT, out_dir: Path = OUT) -> int:
    templates_dir = source_root / "sandbox" / "templates"
    static_src = source_root / "sandbox" / "static"
    ui_config_path = source_root / "core" / "ui_config.json"

    with open(ui_config_path, "r", encoding="utf-8") as f:
        ui_strings = json.load(f)

    terms_ver = _terms_version()
    env = Environment(loader=FileSystemLoader(str(templates_dir)), autoescape=True)

    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True)

    for src_name, out_name in PAGES:
        tpl = env.get_template(src_name)
        rendered = tpl.render(ui=ui_strings, version=terms_ver)
        (out_dir / out_name).write_text(rendered, encoding="utf-8")

    skipped = _copy_static(static_src, out_dir / "static", base_root=source_root)

    (out_dir / "_headers").write_text(_build_headers(), encoding="utf-8")
    (out_dir / "_redirects").write_text(
        "/ai_agent / 301\n"
        "/telemetry https://siraugga.mikeytech.dev/telemetry 302\n"
        "/telemetry.html https://siraugga.mikeytech.dev/telemetry 302\n"
        "/audits https://siraugga.mikeytech.dev/audits 302\n"
        "/audits.html https://siraugga.mikeytech.dev/audits 302\n"
        "/direct https://siraugga.mikeytech.dev/direct 302\n"
        "/direct.html https://siraugga.mikeytech.dev/direct 302\n"
        "/login https://siraugga.mikeytech.dev/login 302\n"
        "/login.html https://siraugga.mikeytech.dev/login 302\n"
        "/plugin/* https://siraugga.mikeytech.dev/plugin/:splat 302\n"
        "/unlock/* https://siraugga.mikeytech.dev/unlock/:splat 302\n"
        "/owner-device/* https://siraugga.mikeytech.dev/owner-device/:splat 302\n"
        "/tickets/decide https://siraugga.mikeytech.dev/tickets/decide 302\n"
        "/static/speech/models/* https://siraugga.mikeytech.dev/static/speech/models/:splat 302\n"
        # The speech engine and its WebAssembly runtime (~23 MB, git-ignored, fetched by scripts/fetch_speech_assets.py)
        # are never part of this bundle, so the voice features need them from the live server like the models.
        "/static/speech/vendor/* https://siraugga.mikeytech.dev/static/speech/vendor/:splat 302\n",
        encoding="utf-8",
    )
    (out_dir / "robots.txt").write_text("User-agent: *\nDisallow: /setup\nDisallow: /login\n", encoding="utf-8")
    (out_dir / "404.html").write_text(
        '<!doctype html><html lang="en"><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<title>Page not found · Siraugga</title>'
        '<body style="font-family:system-ui;background:#0a0a0b;color:#e2e8f0;max-width:36rem;margin:15vh auto;padding:0 16px">'
        '<h1>Page not found</h1><p><a style="color:#2dd4bf" href="/">Open Siraugga</a></p></body></html>',
        encoding="utf-8",
    )

    print(f"Built Siraugga Pages bundle in {out_dir} ({len(PAGES)} HTML pages).")
    if skipped:
        print("Skipped files over 24 MiB (routed to siraugga.mikeytech.dev):", ", ".join(skipped))
    return 0


def main(git_ref: str | None = None, out_dir: Path = OUT) -> int:
    if git_ref:
        with tempfile.TemporaryDirectory(prefix="siraugga-git-build-") as tmp:
            tmp_root = Path(tmp)
            _extract_git_ref_tree(git_ref, tmp_root)
            return build_bundle(source_root=tmp_root, out_dir=out_dir)
    return build_bundle(source_root=ROOT, out_dir=out_dir)


if __name__ == "__main__":
    ref_arg = None
    args = sys.argv[1:]
    if "--git-ref" in args:
        idx = args.index("--git-ref")
        if idx + 1 < len(args):
            ref_arg = args[idx + 1]
    raise SystemExit(main(git_ref=ref_arg))
