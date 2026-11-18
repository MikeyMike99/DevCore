"""Root-only helper inside the lab container. Reachable only through the Worker (container ports are not public).
GET  /info                -> the lab's public description (no answers)
POST /check {"step":"1"}  -> runs /labs/<lab>/checks/<step>.sh; exit 0 = pass
POST /exec  {"command":..} -> runs one command as the non-root 'learner' (used by course steps)"""
import json, os, re, shutil, signal, subprocess
from http.server import BaseHTTPRequestHandler, HTTPServer

LAB = os.environ.get("LAB_ID", "")
BASE = f"/labs/{LAB}"
EXEC_TIMEOUT = 60
MAX_OUT = 20000
LEARNER_ENV = {"PATH": "/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin", "HOME": "/home/learner", "USER": "learner",
               "LOGNAME": "learner", "LANG": "C.UTF-8", "TERM": "dumb"}


def clean_tmp():
    """Every course command starts with an empty /tmp (the old sandbox used a fresh tmpfs per command).
    The learner's home folder is kept between commands."""
    for entry in os.scandir("/tmp"):
        try:
            if entry.is_dir(follow_symlinks=False):
                shutil.rmtree(entry.path, ignore_errors=True)
            else:
                os.unlink(entry.path)
        except OSError:
            pass


def run_as_learner(cmd: str):
    clean_tmp()
    p = subprocess.Popen(
        ["runuser", "-u", "learner", "--", "bash", "-c", "ulimit -f 20480 -n 256; " + cmd],
        cwd="/home/learner", env=LEARNER_ENV, stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, errors="replace", start_new_session=True)
    try:
        out, err = p.communicate(timeout=EXEC_TIMEOUT)
        rc = p.returncode
    except subprocess.TimeoutExpired:
        os.killpg(p.pid, signal.SIGKILL)       # kill the whole command tree, not just bash
        out, err = p.communicate()
        rc, err = 124, (err or "") + "\n[stopped: the command ran longer than %ds]" % EXEC_TIMEOUT
    text = (out or "") + (("\n" + err) if err else "")
    return rc, text[:MAX_OUT]


class H(BaseHTTPRequestHandler):
    def _send(self, code, obj):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(body)

    def _body(self):
        return json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))

    def do_GET(self):
        if self.path == "/info":
            with open(f"{BASE}/lab.json", encoding="utf-8") as f:
                return self._send(200, json.load(f))
        self._send(404, {"error": "not found"})

    def do_POST(self):
        try:
            data = self._body()
        except ValueError:
            return self._send(400, {"error": "bad json"})
        if self.path == "/exec":
            cmd = data.get("command")
            if not isinstance(cmd, str) or not cmd.strip() or len(cmd) > 2000:
                return self._send(400, {"error": "bad command"})
            rc, text = run_as_learner(cmd)
            return self._send(200, {"returncode": rc, "output": text})
        if self.path != "/check":
            return self._send(404, {"error": "not found"})
        step = str(data.get("step", ""))
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
