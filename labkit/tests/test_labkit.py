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

SEEN = []


class H(BaseHTTPRequestHandler):
    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        SEEN.append(body)
        out = json.dumps({"output": "labctl: registered (real server)"}).encode()
        self.send_response(200)
        self.end_headers()
        self.wfile.write(out)

    def log_message(self, *a):
        pass


class ShellTests(unittest.TestCase):
    def test_files_and_redirect(self):
        sh = SimShell({"a.txt": "hi"})
        self.assertEqual(sh.run("cat a.txt"), (0, "hi"))
        sh.run("echo c2lyYXVnZ2E= > s.txt")
        self.assertEqual(sh.run("base64 -d s.txt"), (0, "siraugga"))
        self.assertEqual(sh.run("nope")[0], 127)

    def test_cannot_escape_to_real_disk(self):
        self.assertEqual(SimShell().run("cat C:/Windows/win.ini")[0], 1)


class RemoteTests(unittest.TestCase):
    def test_offline_simulates_queues_then_syncs(self):
        with tempfile.TemporaryDirectory() as d:
            dead = Remote(d, "t", base="http://127.0.0.1:9", timeout=1)
            s = LabSession(load_lab("linux-basics-01"), dead)
            out, where = s.run_command("labctl complete linux-basics-01", "4")
            self.assertEqual(where, "simulated")
            self.assertIn("simulated", out)
            self.assertEqual(dead.pending(), 1)
            srv = HTTPServer(("127.0.0.1", 0), H)
            threading.Thread(target=srv.serve_forever, daemon=True).start()
            live = Remote(d, "t", base=f"http://127.0.0.1:{srv.server_port}/lab")
            self.assertEqual(live.sync(), (1, 0))
            self.assertTrue(SEEN[-1]["replayed"])
            out, where = LabSession(load_lab("linux-basics-01"), live).run_command("labctl x")
            self.assertEqual(where, "server")
            srv.shutdown()

    def test_local_commands_never_hit_network(self):
        with tempfile.TemporaryDirectory() as d:
            s = LabSession(load_lab("linux-basics-01"), Remote(d, "t", base="http://127.0.0.1:9", timeout=1))
            self.assertEqual(s.run_command("ls")[1], "local")
            self.assertEqual(s.remote.pending(), 0)


class PlayTests(unittest.TestCase):
    def test_full_lab_offline(self):
        script = iter(["ls", "cat notes.txt", "echo c2lyYXVnZ2E= > s.txt", "base64 -d s.txt",
                       "labctl complete linux-basics-01"])
        lines = []
        with tempfile.TemporaryDirectory() as d:
            rc = play(load_lab("linux-basics-01"), Remote(d, "t", base="http://127.0.0.1:9", timeout=1),
                      inp=lambda p: next(script), out=lines.append)
        text = "\n".join(lines)
        self.assertEqual(rc, 0)
        self.assertIn("Lab complete", text)
        self.assertIn("SIMULATED", text)
        self.assertIn("waiting to sync", text)


if __name__ == "__main__":
    unittest.main()
