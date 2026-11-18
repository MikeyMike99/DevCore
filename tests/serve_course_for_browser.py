"""Dev utility: serve the REAL Siraugga app (isolated temp data) with a ready-to-go test learner, so a browser can be
pointed at the course page and the live terminal tried by hand or by a browser-driving tool.

    python3 tests/serve_course_for_browser.py [port]      (WSL venv; needs the lab stack: bash labcloud/dev.sh)
Prints "READY <url>" and serves until stopped. Nothing here touches real learner data or the real server.
"""
import asyncio
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core import course_certificate  # noqa: E402
from core.routes import projects as proj_mod  # noqa: E402
from core.server import app  # noqa: E402

COURSE = "linux_essentials_step_by_step"
STEP = "lx1_6"


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 5611
    tmp = Path(tempfile.mkdtemp(prefix="course_browser_"))
    (tmp / "course_certs").mkdir()
    (tmp / "logs").mkdir()
    (tmp / "sandbox").mkdir()
    os.symlink(str(ROOT / "sandbox" / "static"), str(tmp / "sandbox" / "static"))
    os.symlink(str(ROOT / "sandbox" / "templates"), str(tmp / "sandbox" / "templates"))
    from services.mail import config as mail_cfg
    mail_cfg.config.MAILBOX_FILE = tmp / "mailbox.json"
    mail_cfg.config.MAIL_BACKEND = "local"
    app.config["TESTING"] = True

    def apply_patches():
        # The server re-imports core.routes.projects while running (core/session_manager.py hot-bind), which resets
        # module settings. Re-apply ours continuously so every request is served as the isolated test learner.
        proj_mod.COURSE_SANDBOXES_ROOT = str(tmp / "course_sandboxes")
        proj_mod._course_learner_key = lambda: "browserlearner001"
        proj_mod._course_repo_root = lambda: str(tmp)
        course_certificate.certs_root = lambda: str(tmp / "course_certs")
        orig = proj_mod._load_course_and_progress
        if not getattr(orig, "_dbg", False):
            def dbg(course_id, preview=False):
                try:
                    print("LOAD", course_id, "preview=%s" % preview, "box=", proj_mod._course_sandbox_dir(),
                          "paths=", proj_mod._progress_paths(course_id), flush=True)
                except Exception as e:
                    print("LOAD debug error:", type(e).__name__, e, flush=True)
                return orig(course_id, preview)
            dbg._dbg = True
            proj_mod._load_course_and_progress = dbg

    apply_patches()
    import threading, time

    def keep_patched():
        while True:
            apply_patches()
            time.sleep(0.2)
    threading.Thread(target=keep_patched, daemon=True).start()

    # a learner who accepted the terms, registered, and finished everything before STEP
    course_obj, prog = proj_mod._load_course_and_progress(COURSE)
    ids = [s["id"] for _, s in proj_mod._ordered_sections(course_obj)]
    before = ids[:ids.index(STEP)]
    prog["terms_accepted"] = {"accepted": True, "version": proj_mod.COURSE_TERMS_VERSION}
    prog["registration"] = {"registered": True, "verified": True, "full_name": "Browser Tester", "email": "t@example.com"}
    prog["completed_steps"] = before
    prog["reflections"] = {i: {"reflection_done": True, "explain": "Done in the test, with a reflection long enough."} for i in before}
    proj_mod._save_progress_sync(COURSE, prog)
    print("learner folder:", proj_mod._course_sandbox_dir(), flush=True)
    _, back = proj_mod._load_course_and_progress(COURSE)
    print("SEEDED terms:", (back.get("terms_accepted") or {}).get("accepted"), "completed:", len(back.get("completed_steps") or []), flush=True)

    from hypercorn.asyncio import serve
    from hypercorn.config import Config
    cfg = Config()
    cfg.bind = [f"127.0.0.1:{port}"]
    cfg.loglevel = "WARNING"
    print(f"READY http://127.0.0.1:{port}/course?course={COURSE}", flush=True)
    import json as _json, threading as _th, time as _t, urllib.request as _ur

    def _self_check():                       # ask our own server who it thinks the visitor is
        _t.sleep(4)
        try:
            with _ur.urlopen(f"http://127.0.0.1:{port}/api/course/progress?course_id={COURSE}", timeout=30) as r:
                pr = _json.loads(r.read().decode())["progress"]
            import glob as _g
            for f in _g.glob(str(tmp / "course_sandboxes" / "*" / "course_progress_*.json")):
                d = _json.load(open(f, encoding="utf-8"))
                print("ON DISK", os.path.basename(f), "terms:", (d.get("terms_accepted") or {}).get("accepted"),
                      "completed:", len(d.get("completed_steps") or []), flush=True)
            print("SELF-CHECK learner_name:", pr.get("learner_name"), "| terms:", (pr.get("terms_accepted") or {}).get("accepted"),
                  "| completed:", len(pr.get("completed_steps") or []), flush=True)
        except Exception as e:
            print("SELF-CHECK failed:", type(e).__name__, flush=True)
    _th.Thread(target=_self_check, daemon=True).start()
    asyncio.run(serve(app, cfg))


if __name__ == "__main__":
    main()
