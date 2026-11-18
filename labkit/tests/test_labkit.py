import hashlib
import hmac
import json
import os
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from siraugga_lab.engine import LabSession, load_lab, play  # noqa: E402
from siraugga_lab.remote import Remote  # noqa: E402
from siraugga_lab.sim_shell import SimShell  # noqa: E402

SEEN, KEY = [], "learnerkey"
DEAD = "http://127.0.0.1:9"


class H(BaseHTTPRequestHandler):
    """Mock lab server: checks the signature and de-duplicates on request id, like the Worker."""
    def do_POST(self):
        raw = self.rfile.read(int(self.headers["Content-Length"]))
        want = hmac.new(KEY.encode(), raw, hashlib.sha256).hexdigest()
        if self.headers.get("X-Lab-Signature") != want:
            self.send_response(401)
            self.end_headers()
            return
        body = json.loads(raw)
        fresh = body["id"] not in [s["id"] for s in SEEN]
        SEEN.append(body)
        self.send_response(200)
        self.end_headers()
        self.wfile.write(json.dumps({"output": "labctl: registered (real server)" + ("" if fresh else " (already recorded)")}).encode())

    def log_message(self, *a):
        pass


def serve():
    srv = HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


class ShellTests(unittest.TestCase):
    def test_files_and_redirect(self):
        sh = SimShell({"a.txt": "hi"})
        self.assertEqual(sh.run("cat a.txt"), (0, "hi"))
        sh.run("echo c2lyYXVnZ2E= > s.txt")
        self.assertEqual(sh.run("base64 -d s.txt"), (0, "siraugga"))
        self.assertEqual(sh.run("nope")[0], 127)

    def test_pipes(self):
        sh = SimShell({"l.txt": "b\na\nb\nc"})
        self.assertEqual(sh.run("cat l.txt | sort | uniq"), (0, "a\nb\nc"))
        self.assertEqual(sh.run("cat l.txt | grep b | wc -l"), (0, "2"))
        self.assertEqual(sh.run("echo hello | base64"), (0, "aGVsbG8="))
        sh.run("cat l.txt | sort > sorted.txt")
        self.assertEqual(sh.run("head sorted.txt"), (0, "a\nb\nb\nc"))

    def test_cannot_escape_to_real_disk(self):
        self.assertEqual(SimShell().run("cat C:/Windows/win.ini")[0], 1)
        self.assertEqual(SimShell().run("cat ../../etc/passwd")[0], 1)

    def test_state_roundtrip(self):
        a = SimShell()
        a.run("echo x > f.txt")
        b = SimShell()
        b.import_state(a.export_state())
        self.assertEqual(b.run("cat f.txt"), (0, "x"))


class RemoteTests(unittest.TestCase):
    def test_offline_simulates_queues_then_syncs_once(self):
        with tempfile.TemporaryDirectory() as d:
            dead = Remote(d, "L", KEY, base=DEAD, timeout=1)
            s = LabSession(load_lab("linux-basics-01"), dead)
            out, where = s.run_command("labctl complete linux-basics-01", "4")
            self.assertEqual((where, dead.pending()), ("simulated", 1))
            self.assertIn("simulated", out)
            srv = serve()
            live = Remote(d, "L", KEY, base=f"http://127.0.0.1:{srv.server_port}/lab")
            self.assertEqual(live.sync(), (1, 0))
            self.assertTrue(SEEN[-1]["replayed"])
            self.assertEqual(live.pending(), 0)
            out, where = LabSession(load_lab("linux-basics-01"), live).run_command("labctl x")
            self.assertEqual(where, "server")
            srv.shutdown()
            srv.server_close()

    def test_wrong_key_is_refused_not_simulated(self):
        with tempfile.TemporaryDirectory() as d:
            srv = serve()
            bad = Remote(d, "L", "wrong", base=f"http://127.0.0.1:{srv.server_port}/lab")
            out, where = LabSession(load_lab("linux-basics-01"), bad).run_command("labctl complete x")
            self.assertEqual(where, "server")
            self.assertIn("refused", out)
            self.assertEqual(bad.pending(), 0)
            srv.shutdown()
            srv.server_close()

    def test_local_commands_never_hit_network(self):
        with tempfile.TemporaryDirectory() as d:
            s = LabSession(load_lab("linux-basics-01"), Remote(d, "L", KEY, base=DEAD, timeout=1))
            self.assertEqual(s.run_command("ls")[1], "local")
            self.assertEqual(s.remote.pending(), 0)


class PlayTests(unittest.TestCase):
    FULL = ["ls", "cat notes.txt", "echo c2lyYXVnZ2E= > s.txt", "base64 -d s.txt", "labctl complete linux-basics-01"]

    def run_lab(self, d, script, **kw):
        it, lines = iter(script), []
        rc = play(load_lab("linux-basics-01"), Remote(d, "L", KEY, base=DEAD, timeout=1),
                  inp=lambda p: next(it), out=lines.append, **kw)
        return rc, "\n".join(lines)

    def test_full_lab_offline(self):
        with tempfile.TemporaryDirectory() as d:
            rc, text = self.run_lab(d, self.FULL)
        self.assertEqual(rc, 0)
        for s in ("Lab complete", "SIMULATED", "waiting to sync"):
            self.assertIn(s, text)

    def test_hint_and_resume(self):
        with tempfile.TemporaryDirectory() as d:
            pd = os.path.join(d, "progress")
            _, t1 = self.run_lab(d, ["ls", "hint", "cat notes.txt", "echo c2lyYXVnZ2E= > s.txt", "exit"], progress_dir=pd)
            self.assertIn("Hint:", t1)
            self.assertIn("progress is saved", t1)
            _, t2 = self.run_lab(d, ["base64 -d s.txt", "labctl complete linux-basics-01"], progress_dir=pd)
            self.assertIn("resuming at step 3", t2)   # s.txt survived the restart
            self.assertIn("Lab complete", t2)
            self.assertFalse(os.listdir(pd))           # finished labs clear their progress


class EveryLabIsSolvable(unittest.TestCase):
    def test_solutions_complete_every_bundled_lab(self):
        from siraugga_lab.engine import list_labs
        self.assertGreaterEqual(len(list_labs()), 2)
        for name in list_labs():
            lab = load_lab(name)
            cmds = []
            sols = json.load(open(os.path.join(os.path.dirname(__file__), "solutions", name + ".json"), encoding="utf-8"))
            for st in lab["steps"]:
                sol = sols[st["id"]]
                cmds += sol if isinstance(sol, list) else [sol]
            it, lines = iter(cmds), []
            with tempfile.TemporaryDirectory() as d:
                rc = play(lab, Remote(d, "L", KEY, base=DEAD, timeout=1), inp=lambda p: next(it), out=lines.append)
            self.assertEqual(rc, 0, name)
            self.assertIn("Lab complete", "\n".join(lines), name)
            self.assertEqual(next(it, None), None, f"{name}: unused solution commands")


if __name__ == "__main__":
    unittest.main(warnings="ignore")
