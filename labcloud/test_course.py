"""Runs EVERY terminal step of the Linux Essentials course through core/lab_cloud.py into real containers.
    bash labcloud/dev.sh              (WSL, other terminal)
    python labcloud/test_course.py    (needs the same LAB secret as dev.sh; default is the local dev one)
Each step passes if the command exits 0 and prints something (the course's own checks run server-side on the output).
"""
import json, os, sys, time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault("SIRAUGGA_LAB_URL", "http://127.0.0.1:8788")
os.environ.setdefault("SIRAUGGA_LAB_SECRET", "local-dev-only")
from core import lab_cloud  # noqa: E402

course = json.load(open(os.path.join(ROOT, "sandbox", "static", "courses", "linux_essentials_step_by_step.json"), encoding="utf-8"))
steps = [(s["id"], s["expected_command"]) for m in course["modules"] for s in m["sections"] if s.get("task_type") == "terminal_command"]
lab = lab_cloud.lab_for_course("linux_essentials_step_by_step")
assert lab == "linux-essentials", "course is not mapped to the lab image"
learner = f"course-test-{int(time.time())}"          # a fresh learner = a fresh container
bad = []
t0 = time.time()
for sid, cmd in steps:
    try:
        rc, out = lab_cloud.run_command(learner, lab, cmd)
    except lab_cloud.LabCloudUnavailable as e:
        sys.exit(f"Lab cloud unavailable: {e} (is dev.sh running?)")
    ok = rc == 0 and out.strip() != ""
    if not ok:
        bad.append((sid, cmd, rc, out[:120]))
    print(("PASS " if ok else "FAIL ") + sid.ljust(8) + " " + cmd[:70].replace("\n", " "))
print(f"\n{len(steps) - len(bad)}/{len(steps)} course steps work in the container ({time.time() - t0:.0f}s)")
for sid, cmd, rc, out in bad:
    print(f"\n  {sid}: exit {rc}\n  cmd: {cmd[:200]}\n  out: {out!r}")
sys.exit(1 if bad else 0)
