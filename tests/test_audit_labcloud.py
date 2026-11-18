"""Keeps the Lab Cloud audit honest and permanent.

1. The real tree must pass the static audit (no FAIL) - so any future change that weakens security breaks the test suite.
2. The audit must CATCH each known weakness: we break a throw-away copy on purpose and expect the matching check to FAIL.
"""
import json
import os
import shutil
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import audit_labcloud as A  # noqa: E402


def _copy_tree():
    tmp = tempfile.mkdtemp(prefix="auditcopy_")
    shutil.copytree(os.path.join(ROOT, "labcloud"), os.path.join(tmp, "labcloud"),
                    ignore=shutil.ignore_patterns("node_modules", ".wrangler", "__pycache__"))
    for rel in ("core/lab_cloud.py", "core/routes/projects.py", "tests/test_lab_cloud.py",
                "security/security_headers.py", "sandbox/templates/course_application.html",
                "sandbox/static/courses/linux_essentials_step_by_step.json", "scripts/audit_labcloud.py"):
        if os.path.isfile(os.path.join(ROOT, rel)):
            os.makedirs(os.path.dirname(os.path.join(tmp, rel)), exist_ok=True)
            shutil.copy(os.path.join(ROOT, rel), os.path.join(tmp, rel))
    return tmp


def _statuses(root):
    r = A.run_audit(root=root, live=False, tests=False)
    return {(cid): st for _, cid, st, _ in r.rows if st in ("FAIL",)}, r


class RealTreeTests(unittest.TestCase):
    def test_real_tree_has_no_failures(self):
        fails, r = _statuses(ROOT)
        detail = [(cid, msg) for _, cid, st, msg in r.rows if st == "FAIL"]
        self.assertEqual(fails, {}, f"audit failures: {detail}  (deliberate change? review, then run: "
                                    f"python3 scripts/audit_labcloud.py --accept-integrity)")

    def test_audit_covers_the_system(self):
        _, r = _statuses(ROOT)
        self.assertGreaterEqual(len(r.rows), 60)
        self.assertEqual({s.split()[0] for s, *_ in r.rows} >= {"1", "2", "3", "4", "7"}, True)


class MutationTests(unittest.TestCase):
    """Each case weakens a copy of the system; the audit must flag exactly that weakness."""
    CASES = [
        ("IMG-02", "labcloud/image/Dockerfile", "@sha256:", "@sha256_"),
        ("IMG-03", "labcloud/image/Dockerfile", "sha256sum -c", "echo"),
        ("IMG-04", "labcloud/image/Dockerfile", "chmod -R go-rwx /labs", "chmod -R a+rx /labs"),
        ("IMG-07", "labcloud/image/entrypoint.sh", " -u ", " "),
        ("IMG-09", "labcloud/image/grader.py", "capture_output=True", "shell=True, capture_output=True"),
        ("IMG-10", "labcloud/image/grader.py", "killpg", "kill"),
        ("IMG-23", "labcloud/image/labs/linux-basics-01/lab.json", '"title"', '"solution":"x","title"'),
        ("WRK-02", "labcloud/src/worker.js", "safeEqual(", "looseEqual("),
        ("WRK-03", "labcloud/src/worker.js", '"token:v1."', '"v1."'),
        ("WRK-04", "labcloud/src/worker.js", "MAX_SKEW", "MAX_WINDOW"),
        ("WRK-08", "labcloud/src/worker.js", "enableInternet = false", "enableInternet = true"),
        ("SET-03", "labcloud/setup.sh", "docker build", "docker pull evil/image && docker build"),
        ("SET-04", "labcloud/setup.sh", '[ "$answer" = "DEPLOY" ]', "true"),
        ("SET-05", "labcloud/setup.sh", "npm ci", "npm install"),
        ("SET-06", "labcloud/setup.sh", "chmod 600", "chmod 644"),
        ("SET-08", "labcloud/setup.sh", "audit_labcloud.py --no-live", "echo skipped"),
        ("WRK-21", "labcloud/src/worker.js", "LIMITS", "LIM"),
        ("WRK-23", "labcloud/src/worker.js", "raw.length > 256", "raw.length > 999999"),
        ("WRK-10", "labcloud/wrangler.jsonc", '"max_instances"', '"max_inst"'),
        ("WRK-12", "labcloud/src/worker.js", "Content-Security-Policy", "X-Nothing"),
        ("WRK-13", "labcloud/src/worker.js", "script-src 'nonce-", "script-src 'unsafe-inline' 'nonce-"),
        ("CON-02", "core/lab_cloud.py", "_safe_url", "_whatever"),
        ("CON-04", "core/lab_cloud.py", '"ts": int(time.time())', '"x": 1'),
        ("CON-14", "core/routes/projects.py", "except lab_cloud.LabCloudUnavailable", "except ZeroDivisionError"),
        ("CON-16", "core/routes/projects.py", "_is_registered(progress):\n        return 403, {\"ok\": False, \"code\": \"REGISTRATION_REQUIRED\", \"error\": \"Complete User Registration first.\"}\n    sandbox_dir", "_is_registered(progress):\n        pass\n    sandbox_dir"),
        ("CON-17", "security/security_headers.py", "lab_cloud.public_origin()", "'http://evil.example'"),
        ("CON-18", "sandbox/templates/course_application.html", "setAttribute('sandbox'", "setAttribute('data-x'"),
    ]

    def test_each_weakness_is_caught(self):
        for cid, rel, old, new in self.CASES:
            with self.subTest(check=cid):
                tmp = _copy_tree()
                try:
                    path = os.path.join(tmp, rel)
                    if not os.path.isfile(path):
                        self.skipTest(f"{rel} not present")
                    txt = open(path, encoding="utf-8").read()
                    self.assertIn(old, txt, f"mutation anchor vanished from {rel}")
                    open(path, "w", encoding="utf-8", newline="\n").write(txt.replace(old, new))   # every occurrence: the weakness must be real
                    fails, _ = _statuses(tmp)
                    self.assertIn(cid, fails, f"audit did NOT catch the weakness behind {cid}")
                finally:
                    shutil.rmtree(tmp, ignore_errors=True)

    def test_secret_in_tree_is_caught(self):
        tmp = _copy_tree()
        try:
            open(os.path.join(tmp, "labcloud", "oops.txt"), "w").write('LAB_MASTER_SECRET = "abcdef1234567890abcd"\n')
            fails, _ = _statuses(tmp)
            self.assertIn("SUP-01", fails)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_built_artifacts_in_the_tree_are_caught(self):
        for name, size in (("lab-image.tar", 10), ("huge.dat", 1_200_000)):
            with self.subTest(file=name):
                tmp = _copy_tree()
                try:
                    open(os.path.join(tmp, "labcloud", name), "wb").write(b"x" * size)
                    fails, _ = _statuses(tmp)
                    self.assertIn("SET-01", fails)
                finally:
                    shutil.rmtree(tmp, ignore_errors=True)

    def test_setup_script_printing_the_secret_is_caught(self):
        tmp = _copy_tree()
        try:
            open(os.path.join(tmp, "labcloud/setup.sh"), "a").write('\necho "secret is $(cat "$SECRET_FILE")"\n')
            fails, _ = _statuses(tmp)
            self.assertIn("SET-07", fails)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_check_script_that_executes_learner_files_is_caught(self):
        tmp = _copy_tree()
        try:
            p = os.path.join(tmp, "labcloud/image/labs/linux-basics-01/checks/1.sh")
            open(p, "a").write("\nsource hello.txt\n")
            fails, _ = _statuses(tmp)
            self.assertIn("IMG-25", fails)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_tripwire_detects_tampering_and_accepts_approval(self):
        tmp = _copy_tree()
        try:
            wk = os.path.join(tmp, "labcloud/src/worker.js")
            open(wk, "a").write("\n// harmless-looking edit\n")
            fails, _ = _statuses(tmp)
            self.assertIn("TRP-01", fails)
            A.run_audit(root=tmp, live=False, tests=False, accept=True)      # approve
            fails, _ = _statuses(tmp)
            self.assertNotIn("TRP-01", fails)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_line_endings_do_not_trip_the_wire(self):
        tmp = _copy_tree()
        try:
            wk = os.path.join(tmp, "labcloud/src/worker.js")
            data = open(wk, "rb").read().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
            open(wk, "wb").write(data)
            fails, _ = _statuses(tmp)
            self.assertNotIn("TRP-01", fails)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class PlumbingTests(unittest.TestCase):
    def test_violations_are_logged(self):
        tmp = _copy_tree()
        try:
            p = os.path.join(tmp, "labcloud/image/Dockerfile")
            open(p, "w", encoding="utf-8").write(open(p, encoding="utf-8").read().replace("@sha256:", "@x:"))
            _, r = _statuses(tmp)
            A.log_violations(r, root=tmp)
            lines = open(os.path.join(tmp, A.VIOLATIONS_REL), encoding="utf-8").read().splitlines()
            rec = [json.loads(x) for x in lines]
            self.assertTrue(any(x["id"] == "IMG-02" and x["level"] == "FAIL" and x["source"] == "audit_labcloud" for x in rec))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_hook_install_is_idempotent_and_targets_labcloud(self):
        tmp = tempfile.mkdtemp(prefix="hookcopy_")
        try:
            os.makedirs(os.path.join(tmp, ".git", "hooks"))
            hook = os.path.join(tmp, ".git", "hooks", "pre-commit")
            open(hook, "w").write("#!/usr/bin/env bash\nset -e\n")
            self.assertIn("installed", A.install_hook(tmp))
            first = open(hook).read()
            self.assertIn("audit_labcloud.py", first)
            self.assertIn("--no-live", first)
            self.assertIn("labcloud/", first)
            self.assertIn("already installed", A.install_hook(tmp))
            self.assertEqual(open(hook).read(), first)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
