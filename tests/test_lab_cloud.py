import hashlib
import hmac
import json
import os
import sys
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core import lab_cloud  # noqa: E402

SECRET = "unit-test-master"
SEEN = []


class _H(BaseHTTPRequestHandler):
    """Behaves like labcloud's Worker /lab/run: verifies the learner-key signature."""
    mode = "ok"

    def do_POST(self):
        raw = self.rfile.read(int(self.headers["Content-Length"]))
        learner = self.headers["X-Lab-Learner"]
        key = hmac.new(SECRET.encode(), b"learner:" + learner.encode(), hashlib.sha256).hexdigest()
        if self.headers["X-Lab-Signature"] != hmac.new(key.encode(), raw, hashlib.sha256).hexdigest():
            return self._r(401, {"error": "bad signature"})
        SEEN.append((self.path, learner, json.loads(raw)))
        if _H.mode == "bad":
            return self._r(400, {"error": "bad command"})
        self._r(200, {"returncode": 0, "output": "Linux"})

    def _r(self, code, obj):
        self.send_response(code)
        self.end_headers()
        self.wfile.write(json.dumps(obj).encode())

    def log_message(self, *a):
        pass


class LabCloudTests(unittest.TestCase):
    def setUp(self):
        self.srv = HTTPServer(("127.0.0.1", 0), _H)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self._env = {k: os.environ.get(k) for k in ("SIRAUGGA_LAB_URL", "SIRAUGGA_LAB_SECRET")}
        os.environ["SIRAUGGA_LAB_URL"] = f"http://127.0.0.1:{self.srv.server_port}"
        os.environ["SIRAUGGA_LAB_SECRET"] = SECRET
        _H.mode = "ok"

    def tearDown(self):
        self.srv.shutdown()
        self.srv.server_close()
        for k, v in self._env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def test_off_by_default(self):
        os.environ.pop("SIRAUGGA_LAB_URL")
        self.assertFalse(lab_cloud.configured())
        self.assertIsNone(lab_cloud.lab_for_course("linux_essentials_step_by_step"))
        with self.assertRaises(lab_cloud.LabCloudUnavailable):
            lab_cloud.run_command("lc-x", "linux-essentials", "uname -s")

    def test_unmapped_course_is_not_routed(self):
        self.assertIsNone(lab_cloud.lab_for_course("alp_phase2_bicep_course"))
        self.assertEqual(lab_cloud.lab_for_course("linux_essentials_step_by_step"), "linux-essentials")

    def test_signed_request_accepted(self):
        self.assertEqual(lab_cloud.run_command("lc-abc", "linux-essentials", "uname -s"), (0, "Linux"))
        self.assertEqual(SEEN[-1][:2], ("/lab/run", "lc-abc"))
        self.assertEqual({k: v for k, v in SEEN[-1][2].items() if k != "ts"}, {"lab": "linux-essentials", "command": "uname -s"})
        self.assertLess(abs(SEEN[-1][2]["ts"] - time.time()), 10)   # fresh timestamp for the replay window

    def test_wrong_secret_means_fallback(self):
        os.environ["SIRAUGGA_LAB_SECRET"] = "not-the-secret"
        with self.assertRaises(lab_cloud.LabCloudUnavailable):
            lab_cloud.run_command("lc-abc", "linux-essentials", "uname -s")

    def test_unreachable_means_fallback(self):
        os.environ["SIRAUGGA_LAB_URL"] = "http://127.0.0.1:9"
        with self.assertRaises(lab_cloud.LabCloudUnavailable):
            lab_cloud.run_command("lc-abc", "linux-essentials", "uname -s", timeout=1)

    def test_rejected_command_is_reported_not_fallback(self):
        _H.mode = "bad"
        self.assertEqual(lab_cloud.run_command("lc-abc", "linux-essentials", "x")[0], 2)

    def test_plain_http_to_a_remote_host_is_refused(self):
        os.environ["SIRAUGGA_LAB_URL"] = "http://lab.example.com"
        self.assertFalse(lab_cloud.configured())
        os.environ["SIRAUGGA_LAB_URL"] = "https://lab.example.com"
        self.assertTrue(lab_cloud.configured())
        os.environ["SIRAUGGA_LAB_URL"] = "http://localhost:8788"
        self.assertTrue(lab_cloud.configured())

    def test_learner_ids_are_unique_and_safe(self):
        a = lab_cloud.learner_id("/x/playground/.course_sandboxes/aaa111", True)
        b = lab_cloud.learner_id("/x/playground/.course_sandboxes/bbb222", True)
        self.assertNotEqual(a, b)
        self.assertEqual(lab_cloud.learner_id("/home/michael/alp-env/temp_phase2_sandbox", False), "owner")
        self.assertRegex(lab_cloud.learner_id("/x/../we ird;name", True), r"^[A-Za-z0-9_.@-]{1,64}$")


if __name__ == "__main__":
    unittest.main()
