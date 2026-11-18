"""Root-only grader inside the lab container. Reachable only via the Worker (container ports are not public).
GET /info  -> the lab's public description (no answers)
POST /check {"step": "1"} -> runs /labs/<lab>/checks/<step>.sh; exit 0 = pass."""
import json, os, re, subprocess
from http.server import BaseHTTPRequestHandler, HTTPServer

LAB = os.environ.get("LAB_ID", "")
BASE = f"/labs/{LAB}"


class H(BaseHTTPRequestHandler):
    def _send(self, code, obj):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/info":
            with open(f"{BASE}/lab.json", encoding="utf-8") as f:
                return self._send(200, json.load(f))
        self._send(404, {"error": "not found"})

    def do_POST(self):
        if self.path != "/check":
            return self._send(404, {"error": "not found"})
        try:
            step = str(json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0)))).get("step", ""))
        except ValueError:
            return self._send(400, {"error": "bad json"})
        if not re.fullmatch(r"[0-9]{1,3}", step) or not os.path.isfile(f"{BASE}/checks/{step}.sh"):
            return self._send(404, {"error": "no such step"})
        try:
            r = subprocess.run(["bash", f"{BASE}/checks/{step}.sh"], capture_output=True, text=True, timeout=5,
                               cwd="/home/learner", env={"PATH": "/usr/bin:/bin", "HOME": "/home/learner", "LAB": BASE})
            self._send(200, {"passed": r.returncode == 0, "message": (r.stdout or "").strip()[:300]})
        except subprocess.TimeoutExpired:
            self._send(200, {"passed": False, "message": "check timed out"})

    def log_message(self, *a):
        pass


HTTPServer(("0.0.0.0", 8080), H).serve_forever()
