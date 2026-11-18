#!/usr/bin/env python3
"""
=============================================================================
   SIRAUGGA LAB CLOUD AUDITOR (audit_labcloud.py)
=============================================================================
Permanent audit of the real-Linux lab system (labcloud/) and its link to the courses
(core/lab_cloud.py + the routing in core/routes/projects.py).

  Stage 1  Lab container image   pinned bases, pinned download, non-root terminal, answers root-only
  Stage 2  Worker & config       signing, replay window, key separation, CSP, internet off, instance cap
  Stage 3  Course connector      HTTPS-only, safe order of checks, fallback, no secret logging
  Stage 4  Secrets & supply chain  no secrets in the tree, dependency audit (skipped offline)
  Stage 5  Unit tests            tests/test_lab_cloud.py
  Stage 6  Live probes           against a running stack (bash labcloud/dev.sh): attacks + all course steps
  Stage 7  Tripwire              SHA-256 of security-critical files vs. the approved baseline

Every FAIL/WARN is appended to logs/security_violations.jsonl. Exit code 1 if anything FAILs.

Usage:
  python3 scripts/audit_labcloud.py                  # everything (live stage skips if the stack is not running)
  python3 scripts/audit_labcloud.py --no-live        # static + unit tests only (also skips network); used by pre-commit
  python3 scripts/audit_labcloud.py --require-live   # FAIL instead of SKIP when the live stack is not running
  python3 scripts/audit_labcloud.py --json
  python3 scripts/audit_labcloud.py --accept-integrity   # approve deliberate changes to the tripwire baseline
  python3 scripts/audit_labcloud.py --install-hook       # run this audit automatically on commits touching labcloud/
=============================================================================
"""
import argparse
import glob
import hashlib
import hmac
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
BASELINE_REL = "labcloud/audit_baseline.json"
VIOLATIONS_REL = "logs/security_violations.jsonl"
HOOK_MARK = "labcloud-audit"

TRIPWIRE_FILES = [
    "labcloud/src/worker.js", "labcloud/wrangler.jsonc", "labcloud/image/Dockerfile",
    "labcloud/image/entrypoint.sh", "labcloud/image/learner_shell.sh", "labcloud/image/grader.py",
    "labcloud/issue_key.py", "labcloud/dev.sh", "core/lab_cloud.py", "scripts/audit_labcloud.py",
]
TRIPWIRE_GLOBS = ["labcloud/image/labs/*/checks/*.sh", "labcloud/image/labs/*/lab.json"]


class Report:
    def __init__(self):
        self.rows = []   # (stage, id, status, message)
        self.stage = ""

    def add(self, cid, status, msg):
        self.rows.append((self.stage, cid, status, msg))

    def ok(self, cid, msg): self.add(cid, "PASS", msg)
    def warn(self, cid, msg): self.add(cid, "WARN", msg)
    def fail(self, cid, msg): self.add(cid, "FAIL", msg)
    def skip(self, cid, msg): self.add(cid, "SKIP", msg)
    def info(self, cid, msg): self.add(cid, "INFO", msg)

    def check(self, cid, cond, ok_msg, fail_msg, level="FAIL"):
        self.add(cid, "PASS" if cond else level, ok_msg if cond else fail_msg)

    def count(self, status):
        return sum(1 for r in self.rows if r[2] == status)


class Tree:
    """Reads files relative to a repo root (so tests can audit a modified copy)."""
    def __init__(self, root):
        self.root = root

    def read(self, rel):
        try:
            with open(os.path.join(self.root, rel), encoding="utf-8", errors="replace") as f:
                return f.read()
        except OSError:
            return None

    def exists(self, rel):
        return os.path.exists(os.path.join(self.root, rel))

    def glob(self, pattern):
        return sorted(os.path.relpath(p, self.root).replace(os.sep, "/")
                      for p in glob.glob(os.path.join(self.root, pattern)))


# ---------------------------------------------------------------- Stage 1: container image
def stage_image(r: Report, t: Tree):
    r.stage = "1 Lab container image"
    df = t.read("labcloud/image/Dockerfile") or ""
    r.check("IMG-01", bool(df), "Dockerfile present", "labcloud/image/Dockerfile missing")
    froms = re.findall(r"^FROM\s+(?:--platform=\S+\s+)?(\S+)", df, re.M)
    unpinned = [f for f in froms if "@sha256:" not in f]
    r.check("IMG-02", bool(froms) and not unpinned, f"all {len(froms)} base images pinned by digest",
            f"base image(s) not pinned by digest: {unpinned}")
    r.check("IMG-03", "sha256sum -c" in df, "downloaded terminal program is checksum-verified",
            "a downloaded binary is not checksum-verified in the Dockerfile")
    r.check("IMG-04", re.search(r"chmod\s+-R\s+go-rwx\s+/labs", df) is not None,
            "/labs (answers, seeds) is root-only", "Dockerfile does not make /labs root-only (chmod -R go-rwx /labs)")
    r.check("IMG-05", "curl | sh" not in df and "| bash" not in df and "wget -O- " not in df,
            "no pipe-to-shell installs", "Dockerfile pipes a download into a shell")
    ent = t.read("labcloud/image/entrypoint.sh") or ""
    r.check("IMG-06", "*[!A-Za-z0-9_-]*" in ent, "LAB_ID is validated before use", "entrypoint does not validate LAB_ID")
    r.check("IMG-07", re.search(r"ttyd[^\n]*\s-u\s", ent) is not None and re.search(r"ttyd[^\n]*\s-g\s", ent) is not None,
            "terminal (ttyd) is started as the non-root learner (-u/-g)", "ttyd is not dropped to a non-root user")
    sh = t.read("labcloud/image/learner_shell.sh") or ""
    r.check("IMG-08", "export HOME=/home/learner" in sh, "terminal shell pins HOME to the learner's home", "learner shell does not set HOME")
    g = t.read("labcloud/image/grader.py") or ""
    r.check("IMG-09", "shell=True" not in g, "grader never uses a shell string", "grader uses shell=True")
    r.check("IMG-10", "timeout=" in g and "killpg" in g, "grader times out and kills the whole process group",
            "grader lacks timeout / process-group kill")
    r.check("IMG-11", "MAX_OUT" in g and "[:MAX_OUT]" in g, "command output is capped", "grader output is not capped")
    r.check("IMG-12", "fullmatch(r\"[0-9]{1,3}\"" in g.replace("'", '"') or "[0-9]{1,3}" in g,
            "step ids are validated (no path tricks)", "grader does not validate step ids")
    r.check("IMG-13", "len(cmd) > 2000" in g, "command length is limited in the grader", "grader does not limit command length", "WARN")
    r.check("IMG-14", "runuser" in g and "learner" in g, "commands run as the learner via runuser", "grader does not drop to the learner")

    labs = [os.path.basename(os.path.dirname(p)) for p in t.glob("labcloud/image/labs/*/lab.json")]
    r.check("IMG-20", bool(labs), f"{len(labs)} labs found: {', '.join(labs)}", "no labs found")
    bad_exec = re.compile(r"(^|[;&|\s])(source|eval|exec|sh|bash|python3?|perl)\s|^\s*\.\s", re.M)
    for lab in labs:
        meta_raw = t.read(f"labcloud/image/labs/{lab}/lab.json") or "{}"
        try:
            meta = json.loads(meta_raw)
        except ValueError:
            r.fail("IMG-21", f"{lab}: lab.json is not valid JSON")
            continue
        steps = meta.get("steps", [])
        r.check("IMG-21", meta.get("id") == lab, f"{lab}: id matches folder", f"{lab}: lab.json id != folder name")
        r.check("IMG-22", t.exists(f"labcloud/image/labs/{lab}/seed"), f"{lab}: seed folder present", f"{lab}: seed folder missing")
        leak = re.search(r'"(check|checks|answer|answers|solution|solutions|expected)"', meta_raw)
        r.check("IMG-23", leak is None, f"{lab}: lab.json holds no answers", f"{lab}: lab.json contains an answer-like key ({leak.group(1) if leak else ''})")
        for s in steps:
            sid = str(s.get("id"))
            chk = t.read(f"labcloud/image/labs/{lab}/checks/{sid}.sh")
            if chk is None:
                r.fail("IMG-24", f"{lab}: step {sid} has no check script")
                continue
            if bad_exec.search(chk):
                r.fail("IMG-25", f"{lab}/checks/{sid}.sh runs/sources something (checks run as root and must only read learner files)")
        extra = [os.path.basename(p)[:-3] for p in t.glob(f"labcloud/image/labs/{lab}/checks/*.sh")]
        r.check("IMG-26", set(extra) <= {str(s.get("id")) for s in steps}, f"{lab}: no orphan check scripts",
                f"{lab}: check scripts without a step: {sorted(set(extra) - {str(s.get('id')) for s in steps})}", "WARN")


# ---------------------------------------------------------------- Stage 2: Worker & config
def stage_worker(r: Report, t: Tree):
    r.stage = "2 Worker & config"
    w = t.read("labcloud/src/worker.js") or ""
    cfg = t.read("labcloud/wrangler.jsonc") or ""
    r.check("WRK-01", bool(w) and bool(cfg), "worker.js and wrangler.jsonc present", "worker.js or wrangler.jsonc missing")
    r.check("WRK-02", len(re.findall(r"safeEqual\(", w)) >= 3, "signatures compared in constant time",
            "signature comparison is not constant-time everywhere")
    r.check("WRK-03", '"learner:"' in w and '"token:v1."' in w,
            "learner keys and link signatures use separate HMAC domains", "HMAC domain separation missing (learner key vs token signature)")
    r.check("WRK-04", "MAX_SKEW" in w and "stale or missing timestamp" in w, "signed requests have a replay window (timestamp)",
            "no replay window on signed backend requests")
    r.check("WRK-05", "TOKEN_TTL" in w and re.search(r"TOKEN_TTL\s*=\s*(\d+)\s*\*\s*3600", w) is not None
            and int(re.search(r"TOKEN_TTL\s*=\s*(\d+)\s*\*\s*3600", w).group(1)) <= 8, "browser links expire (<= 8 hours)",
            "link lifetime missing or longer than 8 hours")
    r.check("WRK-06", "ID_RE" in w and "LAB_RE" in w, "learner and lab names are validated", "learner/lab name validation missing")
    r.check("WRK-07", "readToken(env, token)" in w and "verifySigned(" in w, "every route is behind a signed link or a signed request",
            "a route may be reachable without authentication")
    r.check("WRK-08", "enableInternet = false" in w, "learner containers have no outbound internet", "enableInternet is not false")
    r.check("WRK-09", re.search(r"sleepAfter\s*=", w) is not None, "idle containers sleep", "sleepAfter not set")
    m = re.search(r'"max_instances"\s*:\s*(\d+)', cfg)
    r.check("WRK-10", m is not None, f"max_instances set ({m.group(1) if m else '-'})", "no max_instances cap on live containers")
    if m and int(m.group(1)) > 50:
        r.warn("WRK-11", f"max_instances is {m.group(1)}: confirm the cost/capacity is intended")
    r.check("WRK-12", "Content-Security-Policy" in w and "nonce-" in w, "lab page has a nonce-based CSP", "lab page has no CSP")
    csp = re.search(r"script-src ([^;`]*)", w)
    r.check("WRK-13", csp is not None and "unsafe-inline" not in csp.group(1) and "unsafe-eval" not in csp.group(1),
            "CSP allows no unsafe script", "CSP allows unsafe-inline/unsafe-eval scripts")
    r.check("WRK-14", "nosniff" in w and "no-referrer" in w and "no-store" in w, "nosniff / no-referrer / no-store headers set",
            "security headers (nosniff, no-referrer, no-store) missing")
    r.check("WRK-15", "EMBED_ORIGINS" in w, "embedding sites are configurable (frame-ancestors)", "frame-ancestors is not configurable", "WARN")
    r.check("WRK-16", '"workers_dev": false' in cfg.replace(" ", "") or '"workers_dev":false' in cfg.replace(" ", ""),
            "no public workers.dev address", "workers_dev is not disabled")
    r.check("WRK-17", not re.search(r"(?i)\"vars\"\s*:\s*\{[^}]*(secret|token|key|password)", cfg), "no secrets in wrangler vars",
            "wrangler.jsonc has a secret-looking var")
    r.check("WRK-18", "eval(" not in w and "new Function(" not in w, "no eval in the Worker", "eval/new Function used in the Worker")
    r.check("WRK-19", "INSERT OR IGNORE" in w, "progress writes are idempotent", "progress writes are not idempotent", "WARN")
    r.check("WRK-20", "x-forwarded" not in w.lower(), "no trust in forwarded headers", "Worker trusts forwarded headers", "WARN")
    r.check("WRK-21", "LIMITS" in w and "429" in w and w.count("limited(env") >= 4,
            "per-learner rate limits on session, run and check", "rate limiting missing on a route (session/run/check)")
    r.check("WRK-23", "raw.length > 256" in w, "request bodies are size-limited on every route", "a route reads an unbounded body")
    if re.search(r'"routes"\s*:', cfg):
        r.info("WRK-22", "wrangler.jsonc defines a public route: this build is configured for deployment")
    else:
        r.info("WRK-22", "no route/domain configured: local-only build")


# ---------------------------------------------------------------- Stage 3: connector & course integration
def stage_connector(r: Report, t: Tree):
    r.stage = "3 Course connector"
    c = t.read("core/lab_cloud.py") or ""
    r.check("CON-01", bool(c), "core/lab_cloud.py present", "core/lab_cloud.py missing")
    r.check("CON-02", "_safe_url" in c and '"https"' in c, "commands are sent only over HTTPS (or to this machine)", "connector can send over plain HTTP to a remote host")
    r.check("CON-03", "timeout=timeout" in c, "requests have a timeout", "connector request has no timeout")
    r.check("CON-04", '"ts": int(time.time())' in c, "requests carry a timestamp for the replay window", "requests carry no timestamp")
    r.check("CON-05", b"learner:" in c.encode(), "uses the separated learner-key derivation", "connector does not use the learner: key domain")
    log_lines = [ln for ln in c.splitlines() if re.search(r"\blog\.(debug|info|warning|error|exception)\(", ln)]
    leaky = [ln.strip() for ln in log_lines if re.search(r"(?i)secret|master|\bkey\b|sig\b|environ", ln)]
    r.check("CON-06", not leaky, "no secret/key/signature in log lines", f"log line may leak a secret: {leaky[:1]}")
    r.check("CON-07", "SIRAUGGA_LAB_SECRET" in c and "print(" not in c, "secret comes from the environment and is never printed", "connector prints or hardcodes the secret")
    mapped = re.findall(r'"([A-Za-z0-9_]+)"\s*:\s*"([A-Za-z0-9_-]+)"', (re.search(r"COURSE_LABS\s*=\s*\{([^}]*)\}", c) or [None, ""])[1])
    for course, lab in mapped:
        r.check("CON-08", t.exists(f"labcloud/image/labs/{lab}/lab.json"), f"course {course} -> lab '{lab}' exists",
                f"course {course} maps to missing lab '{lab}'")
        cj = t.read(f"sandbox/static/courses/{course}.json")
        if cj:
            try:
                cmds = [s.get("expected_command", "") for m in json.loads(cj)["modules"] for s in m["sections"] if s.get("task_type") == "terminal_command"]
                egress = [x for x in cmds if re.search(r"(?<![\w-])(curl|wget|nc|ncat|ping|nmap|telnet|ftp)\s", x)]
                r.check("CON-09", not egress, f"{course}: no network-egress commands among {len(cmds)} steps",
                        f"{course}: steps use network tools (the lab has no internet): {egress[:2]}", "WARN")
            except (ValueError, KeyError):
                r.warn("CON-09", f"{course}: could not parse course JSON")

    p = t.read("core/routes/projects.py")
    if p is None:
        r.skip("CON-10", "core/routes/projects.py not found")
        return
    if "lab_cloud" not in p:
        r.warn("CON-10", "projects.py does not use lab_cloud: courses still run only in the old sandbox")
        return
    api = p.find("async def api_course_execute")
    ex = p.find("def _execute_sandbox_sync")
    api_body = p[api:p.find("\ndef ", api + 10)] if api >= 0 else ""
    allow_i = api_body.find("command in allowed_cmds")
    call_i = api_body.rfind("_execute_sandbox_sync")   # the LAST call runs the course command (an earlier one only reads transcripts)
    r.check("CON-11", allow_i >= 0 and call_i > allow_i,
            "the course's command allow-list is enforced BEFORE anything runs", "allow-list check does not precede execution in api_course_execute")
    pred_i = api_body.find("pre-run prediction")
    r.check("CON-12", pred_i >= 0 and call_i > pred_i, "the prediction requirement is enforced before execution", "prediction check does not precede execution", "WARN")
    body = p[ex:p.find("\ndef ", ex + 10)] if ex >= 0 else ""
    route_i = body.find("lab_cloud.lab_for_course")
    rec_i = body.find("cmd.startswith('rec-sandbox')")
    read_i = body.find("cmd.startswith('read-sandbox')")
    r.check("CON-13", route_i > max(rec_i, read_i) > 0, "evidence builtins are handled before cloud routing", "cloud routing happens before the rec/read builtins")
    r.check("CON-14", "except lab_cloud.LabCloudUnavailable" in body and "COURSE_JAIL" in body,
            "falls back to the old jailed sandbox when the lab cloud is unavailable", "no safe fallback when the lab cloud is unavailable")
    r.check("CON-15", call_i >= 0 and "course_id" in api_body[call_i:call_i + 500], "course id is passed through to the executor", "course id is not passed to the executor")


# ---------------------------------------------------------------- Stage 4: secrets & supply chain
def stage_supply(r: Report, t: Tree, offline: bool):
    r.stage = "4 Secrets & supply chain"
    secret_re = re.compile(r"(?i)(LAB_MASTER_SECRET|SIRAUGGA_LAB_SECRET|API[_-]?KEY|PRIVATE KEY|password)\s*[:=]\s*[\"']([^\"'\s]{12,})[\"']")
    hex_re = re.compile(r"\b[0-9a-f]{64}\b")
    allowed_hex = {"8a217c968aba172e0dbf3f34447218dc015bc4d5e59bf51db2f2cd12b7be4f55",
                   "734a72b3d6142a71993b4bc580ca01d8ca687f77a2c422d96a961d3376b179bc"}
    leaks = []
    files = []
    for dp, dn, fn in os.walk(os.path.join(t.root, "labcloud")):
        dn[:] = [d for d in dn if d not in ("node_modules", ".wrangler", "__pycache__")]
        files += [os.path.relpath(os.path.join(dp, f), t.root).replace(os.sep, "/") for f in fn]
    for rel in files + ["core/lab_cloud.py"]:
        if rel.endswith(("package-lock.json", "audit_baseline.json")):
            continue
        txt = t.read(rel) or ""
        for m in secret_re.finditer(txt):
            if m.group(2) != "local-dev-only":
                leaks.append(f"{rel}: {m.group(1)}")
        for m in hex_re.finditer(txt):
            if m.group(0) not in allowed_hex and not rel.endswith(".py"):
                leaks.append(f"{rel}: 64-hex string")
    r.check("SUP-01", not leaks, f"no secrets in {len(files) + 1} lab cloud files", f"possible secrets: {leaks[:3]}")
    gi = (t.read("labcloud/.gitignore") or "") + (t.read(".gitignore") or "")
    r.check("SUP-02", ".dev.vars" in gi, ".dev.vars is gitignored", ".dev.vars is not gitignored")
    r.check("SUP-03", "node_modules" in gi, "node_modules is gitignored", "node_modules is not gitignored")
    dev = t.read("labcloud/dev.sh") or ""
    r.check("SUP-04", "local-dev-only" in dev and "--local" in dev and "--remote" not in dev,
            "dev.sh is local-only (local DB, local dev secret)", "dev.sh may touch remote resources")
    pkg = t.read("labcloud/package.json") or "{}"
    try:
        deps = json.loads(pkg).get("dependencies", {})
    except ValueError:
        deps = {}
    loose = [k for k, v in deps.items() if re.match(r"^[\^~*]|latest", v)]
    if loose:
        r.check("SUP-05", t.exists("labcloud/package-lock.json"), "dependencies use ranges but a lockfile pins them",
                f"unpinned dependencies without a lockfile: {loose}")
    else:
        r.ok("SUP-05", "dependencies are exact")
    if offline:
        r.skip("SUP-06", "npm audit skipped (offline mode)")
        return
    try:
        res = subprocess.run(["npm", "audit", "--omit=dev", "--audit-level=high", "--json"], cwd=os.path.join(t.root, "labcloud"),
                             capture_output=True, text=True, timeout=90, shell=(os.name == "nt"))
        data = json.loads(res.stdout or "{}")
        vul = (data.get("metadata", {}).get("vulnerabilities") or {})
        high = int(vul.get("high", 0)) + int(vul.get("critical", 0))
        r.check("SUP-06", high == 0, f"npm audit: no high/critical vulnerabilities ({vul.get('total', 0)} total)",
                f"npm audit: {high} high/critical vulnerabilities")
    except (OSError, ValueError, subprocess.TimeoutExpired):
        r.skip("SUP-06", "npm audit could not run (npm missing or no network)")


# ---------------------------------------------------------------- Stage 5: unit tests
def stage_tests(r: Report, t: Tree):
    r.stage = "5 Unit tests"
    if not t.exists("tests/test_lab_cloud.py"):
        r.fail("TST-01", "tests/test_lab_cloud.py missing")
        return
    res = subprocess.run([sys.executable, "-m", "unittest", "tests.test_lab_cloud"], cwd=t.root, capture_output=True, text=True, timeout=180)
    last = (res.stderr.strip().splitlines() or [""])[-1]
    n = re.search(r"Ran (\d+) tests", res.stderr)
    r.check("TST-01", res.returncode == 0, f"connector unit tests pass ({n.group(1) if n else '?'} tests)", f"connector unit tests failed: {last}")


# ---------------------------------------------------------------- Stage 6: live probes
def _http(method, url, body=None, headers=None, timeout=60):
    req = urllib.request.Request(url, data=body, method=method, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, dict(resp.headers), resp.read()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read()


def stage_live(r: Report, t: Tree, require: bool, url: str, secret: str):
    r.stage = "6 Live probes"
    try:
        st, _, _ = _http("GET", url + "/lab/info/x", timeout=5)
    except (urllib.error.URLError, OSError):
        (r.fail if require else r.skip)("LIV-00", f"lab cloud not running at {url} (start it: bash labcloud/dev.sh)")
        return
    r.check("LIV-00", st == 401, f"lab cloud answering at {url}", f"unexpected answer {st} for a bad link")

    def sess(learner, lab="linux-essentials", ts=None, domain=b"learner:", key_learner=None):
        body = json.dumps({"lab": lab, "ts": int(time.time()) if ts is None else ts}).encode()
        key = hmac.new(secret.encode(), domain + (key_learner or learner).encode(), hashlib.sha256).hexdigest()
        sig = hmac.new(key.encode(), body, hashlib.sha256).hexdigest()
        return _http("POST", url + "/lab/session", body, {"X-Lab-Learner": learner, "X-Lab-Signature": sig})

    def run(learner, cmd, lab="linux-essentials", ts=None):
        body = json.dumps({"lab": lab, "command": cmd, "ts": int(time.time()) if ts is None else ts}).encode()
        key = hmac.new(secret.encode(), b"learner:" + learner.encode(), hashlib.sha256).hexdigest()
        sig = hmac.new(key.encode(), body, hashlib.sha256).hexdigest()
        st, _, out = _http("POST", url + "/lab/run", body, {"X-Lab-Learner": learner, "X-Lab-Signature": sig})
        return st, (json.loads(out) if out[:1] == b"{" else {})

    a, b = f"audit-a-{int(time.time())}", f"audit-b-{int(time.time())}"
    st, _, out = sess(a)
    r.check("LIV-01", st == 200, "signed session accepted", f"signed session refused ({st}): {out[:80]!r}")
    if st != 200:
        r.fail("LIV-02", "secret mismatch? set SIRAUGGA_LAB_SECRET to the stack's LAB_MASTER_SECRET")
        return
    sj = json.loads(out)
    token = sj["terminal"].split("/")[2]
    r.check("LIV-03", sess(a, ts=int(time.time()) - 1000)[0] == 401, "stale request (replay) refused", "a 1000-second-old signed request was accepted")
    r.check("LIV-04", sess(a, ts=int(time.time()) + 1000)[0] == 401, "future-dated request refused", "a future-dated request was accepted")
    body = json.dumps({"lab": "linux-essentials"}).encode()
    key = hmac.new(secret.encode(), b"learner:" + a.encode(), hashlib.sha256).hexdigest()
    r.check("LIV-05", _http("POST", url + "/lab/session", body, {"X-Lab-Learner": a, "X-Lab-Signature": hmac.new(key.encode(), body, hashlib.sha256).hexdigest()})[0] == 401,
            "request without a timestamp refused", "a request without a timestamp was accepted")
    r.check("LIV-06", sess(a, domain=b"")[0] == 401, "old un-separated key derivation refused", "the key without domain separation was accepted")
    r.check("LIV-07", sess(a, key_learner=b)[0] == 401, "another learner's key refused", "learner A signed with learner B's key and was accepted")
    r.check("LIV-08", sess("bad id!")[0] == 401, "malformed learner id refused", "malformed learner id accepted")
    r.check("LIV-09", sess(a, lab="../etc")[0] in (400, 401), "malformed lab name refused", "malformed lab name accepted")
    r.check("LIV-10", _http("GET", url + sj["app"][:-2] + "xx")[0] == 401, "tampered link refused", "tampered link accepted")
    st, h, page = _http("GET", url + sj["app"])
    hl = {k.lower(): v for k, v in h.items()}
    csp = hl.get("content-security-policy", "")
    r.check("LIV-11", st == 200 and "nonce-" in csp and "unsafe-inline" not in csp.split("script-src")[-1].split(";")[0],
            "lab page served with a strict CSP", f"lab page CSP weak or missing: {csp[:80]!r}")
    r.check("LIV-12", hl.get("x-content-type-options") == "nosniff" and hl.get("referrer-policy") == "no-referrer" and "no-store" in hl.get("cache-control", ""),
            "lab page has nosniff / no-referrer / no-store", "lab page is missing a security header")
    n = re.search(r'nonce="([^"]+)"', page.decode(errors="replace"))
    r.check("LIV-13", n is not None and f"nonce-{n.group(1)}" in csp, "inline script/style carry the CSP nonce", "page nonce does not match the CSP")
    st, _, info = _http("GET", url + f"/lab/info/{token}")
    r.check("LIV-14", st == 200 and b"checks" not in info and b"expected" not in info, "lab info leaks no answers", "lab info exposes answer data")
    r.check("LIV-15", _http("POST", url + "/lab/check/" + token, b'{"step":"../../etc/passwd"}')[0] == 404, "grader refuses path tricks", "grader accepted a path-trick step id")
    st, _ = run(a, "x" * 2500)
    r.check("LIV-16", st == 400, "over-long command refused", f"over-long command not refused ({st})")
    r.check("LIV-17", _http("GET", url + "/lab/run")[0] in (404, 405) and _http("GET", url + "/nope")[0] == 404, "wrong method / unknown route refused", "unexpected route behaviour")
    st, h2, _ = _http("POST", url + "/lab/run", b"{}", {})
    r.check("LIV-18", st == 401, "unsigned /lab/run refused", f"unsigned /lab/run answered {st}")
    burst = [_http("POST", url + "/lab/check/" + token, b'{"step":"1"}') for _ in range(40)]
    limited = [x for x in burst if x[0] == 429]
    r.check("LIV-19", len(limited) >= 1 and any("retry-after" in {k.lower() for k in x[1]} for x in limited),
            f"rate limit works: {len(limited)} of 40 rapid checks were refused (429 + Retry-After)",
            "40 rapid /lab/check calls were all accepted (no rate limit)")

    def sh(who, cmd):
        s, o = run(who, cmd)
        return o.get("returncode"), (o.get("output") or "").strip()
    rc, out = sh(a, "id -un")
    r.check("LIV-20", out == "learner", "commands run as the non-root learner", f"commands run as {out!r}")
    rc, out = sh(a, "cat /labs/*/lab.json 2>&1; ls /labs 2>&1")
    r.check("LIV-21", "Permission denied" in out and "title" not in out, "learner cannot read /labs (answers)", f"learner can read /labs: {out[:60]!r}")
    rc, out = sh(a, "touch /etc/audit_x 2>&1; touch /usr/audit_x 2>&1")
    r.check("LIV-22", out.count("Permission denied") == 2, "learner cannot write system folders", f"system write not denied: {out[:60]!r}")
    sh(a, "echo mine > keep.txt")
    r.check("LIV-23", sh(a, "cat keep.txt")[1] == "mine", "learner's home persists between steps", "home folder did not persist")
    r.check("LIV-24", "No such file" in sh(b, "cat keep.txt 2>&1")[1], "another learner cannot see the files", "learners share files")
    sh(a, "echo t > /tmp/t1")
    r.check("LIV-25", sh(a, "ls /tmp | wc -l")[1] == "0", "/tmp is empty before every command", "/tmp persisted between commands")
    r.check("LIV-26", len(sh(a, "yes | head -c 500000")[1]) <= 20000, "output is capped at 20000 characters", "output cap not applied")
    t0 = time.time()
    rc, out = sh(a, "sleep 2; echo done")
    r.check("LIV-27", out == "done" and time.time() - t0 < 30, "normal commands complete", "normal command failed")
    rc, out = sh(a, "timeout 3 bash -c 'echo > /dev/tcp/1.1.1.1/53' 2>&1; echo rc=$?")
    reachable = "rc=0" in out
    local = "127.0.0.1" in url or "localhost" in url
    if not reachable:
        r.ok("LIV-29", "container has no outbound internet")
    elif local:
        r.warn("LIV-29", "container CAN reach the internet in local dev (Cloudflare enforces enableInternet=false; "
                         "re-run against the deployed URL with --require-live to verify)")
    else:
        r.fail("LIV-29", "the DEPLOYED lab container can reach the internet: enableInternet=false is not in effect")
    ctr = subprocess.run(["docker", "ps", "--format", "{{.Image}}"], capture_output=True, text=True).stdout
    r.info("LIV-28", f"{ctr.count('labcontainer')} lab containers running for this audit")
    for name, script in (("LIV-30", "labcloud/test_local.py"), ("LIV-31", "labcloud/test_course.py")):
        if not t.exists(script):
            r.fail(name, f"{script} missing")
            continue
        env = dict(os.environ, SIRAUGGA_LAB_URL=url, LAB_URL=url, SIRAUGGA_LAB_SECRET=secret, LAB_MASTER_SECRET=secret, MSYS_NO_PATHCONV="1")
        res = subprocess.run([sys.executable, script], cwd=t.root, capture_output=True, text=True, env=env, timeout=900)
        tail = [ln for ln in res.stdout.splitlines() if "passed" in ln or "course steps" in ln]
        r.check(name, res.returncode == 0, f"{os.path.basename(script)}: {tail[-1].strip() if tail else 'ok'}",
                f"{os.path.basename(script)} failed: {(res.stdout + res.stderr)[-200:]!r}")


# ---------------------------------------------------------------- Stage 7: tripwire
def _tripwire_files(t: Tree):
    files = [f for f in TRIPWIRE_FILES if t.exists(f)]
    for g in TRIPWIRE_GLOBS:
        files += t.glob(g)
    return sorted(set(files))


def _digest(t: Tree, rel):
    with open(os.path.join(t.root, rel), "rb") as f:
        return hashlib.sha256(f.read().replace(b"\r\n", b"\n")).hexdigest()   # line endings must not matter


def stage_tripwire(r: Report, t: Tree, accept: bool):
    r.stage = "7 Tripwire"
    cur = {f: _digest(t, f) for f in _tripwire_files(t)}
    path = os.path.join(t.root, BASELINE_REL)
    if accept:
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            json.dump({"approved_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "files": cur}, f, indent=1, sort_keys=True)
        r.ok("TRP-00", f"baseline approved: {len(cur)} security-critical files recorded")
        return
    if not os.path.isfile(path):
        r.fail("TRP-00", "no approved baseline (run: python3 scripts/audit_labcloud.py --accept-integrity)")
        return
    base = json.load(open(path, encoding="utf-8")).get("files", {})
    changed = sorted(f for f in cur if f in base and cur[f] != base[f])
    added = sorted(f for f in cur if f not in base)
    removed = sorted(f for f in base if f not in cur)
    r.check("TRP-01", not changed, f"{len(cur)} security-critical files match the approved baseline",
            f"changed since approval: {changed} (review, then run with --accept-integrity)")
    r.check("TRP-02", not added, "no new unreviewed security-critical files", f"new files not in baseline: {added} (review, then --accept-integrity)")
    r.check("TRP-03", not removed, "no security-critical file was removed", f"removed since approval: {removed}")


# ---------------------------------------------------------------- driver
def run_audit(root=ROOT, live=True, require_live=False, offline=False, accept=False,
              url="http://127.0.0.1:8788", secret=None, tests=True) -> Report:
    t, r = Tree(root), Report()
    stage_image(r, t)
    stage_worker(r, t)
    stage_connector(r, t)
    stage_supply(r, t, offline or not live)
    if tests:
        stage_tests(r, t)
    if live:
        sec = secret or os.environ.get("SIRAUGGA_LAB_SECRET") or ("local-dev-only" if "127.0.0.1" in url or "localhost" in url else "")
        if sec:
            stage_live(r, t, require_live, url, sec)
        else:
            r.stage = "6 Live probes"
            r.skip("LIV-00", "no secret for a non-local URL (set SIRAUGGA_LAB_SECRET)")
    stage_tripwire(r, t, accept)
    return r


def log_violations(r: Report, root=ROOT):
    rows = [x for x in r.rows if x[2] in ("FAIL", "WARN")]
    if not rows:
        return
    path = os.path.join(root, VIOLATIONS_REL)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        for stage, cid, status, msg in rows:
            f.write(json.dumps({"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "source": "audit_labcloud",
                                "stage": stage, "id": cid, "level": status, "message": msg}) + "\n")


def install_hook(root=ROOT) -> str:
    hook = os.path.join(root, ".git", "hooks", "pre-commit")
    if not os.path.isfile(hook):
        return "no .git/hooks/pre-commit found (run scripts/git_bootstrap.py first)"
    txt = open(hook, encoding="utf-8").read()
    if HOOK_MARK in txt:
        return "hook already installed"
    block = f"""
# >>> {HOOK_MARK} (installed by scripts/audit_labcloud.py --install-hook)
if git diff --cached --name-only | grep -qE '^(labcloud/|core/lab_cloud\\.py|scripts/audit_labcloud\\.py)'; then
    echo "🔒 [PRE-COMMIT] Auditing the Lab Cloud..."
    python3 "$(git rev-parse --show-toplevel)/scripts/audit_labcloud.py" --no-live || exit 1
fi
# <<< {HOOK_MARK}
"""
    with open(hook, "a", encoding="utf-8", newline="\n") as f:
        f.write(block)
    os.chmod(hook, 0o755)
    return "hook installed: commits touching labcloud/ now run the audit"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Siraugga Lab Cloud auditor")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--no-live", action="store_true", help="static checks + unit tests only (no network)")
    ap.add_argument("--require-live", action="store_true", help="FAIL if the live stack is not running")
    ap.add_argument("--accept-integrity", action="store_true", help="approve the current security-critical files")
    ap.add_argument("--install-hook", action="store_true")
    ap.add_argument("--url", default=os.environ.get("SIRAUGGA_LAB_URL", "http://127.0.0.1:8788"))
    args = ap.parse_args(argv)
    if args.install_hook:
        print(install_hook())
        return 0
    r = run_audit(live=not args.no_live, require_live=args.require_live, accept=args.accept_integrity, url=args.url)
    if not args.accept_integrity:
        log_violations(r)
    if args.json:
        print(json.dumps({"summary": {s: r.count(s) for s in ("PASS", "WARN", "FAIL", "SKIP", "INFO")},
                          "results": [{"stage": a, "id": b, "status": c, "message": d} for a, b, c, d in r.rows]}, indent=1))
    else:
        last = None
        for stage, cid, status, msg in r.rows:
            if stage != last:
                print(f"\n=== Stage {stage} ===")
                last = stage
            print(f"  [{status:<4}] {cid:<7} {msg}")
        print("\n" + "=" * 70)
        print(f"  LAB CLOUD AUDIT: {r.count('PASS')} pass, {r.count('WARN')} warn, {r.count('FAIL')} FAIL, {r.count('SKIP')} skipped")
        print("=" * 70)
    return 1 if r.count("FAIL") else 0


if __name__ == "__main__":
    sys.exit(main())
