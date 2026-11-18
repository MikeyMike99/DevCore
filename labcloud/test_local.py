"""End-to-end test of the lab cloud against `bash labcloud/dev.sh` (local only). Stdlib only.
    python labcloud/test_local.py            (dev server must be running on :8788)
"""
import base64, hashlib, hmac, json, os, socket, struct, subprocess, sys, time, urllib.error, urllib.request

BASE = os.environ.get("LAB_URL", "http://127.0.0.1:8788")
MASTER = os.environ.get("LAB_MASTER_SECRET", "local-dev-only")
LEARNER, LAB = "tester-" + str(int(time.time())), "linux-basics-01"   # fresh learner = fresh container each run
results = []


def check(name, ok, detail=""):
    results.append(ok)
    print(("PASS  " if ok else "FAIL  ") + name + (f"   [{ascii(detail)}]" if detail and not ok else ""))


def http(method, path, body=None, headers=None):
    req = urllib.request.Request(BASE + path, data=body, method=method, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def signed_session(learner, key_for=None):
    body = json.dumps({"lab": LAB}).encode()
    key = hmac.new(MASTER.encode(), (key_for or learner).encode(), hashlib.sha256).hexdigest()
    sig = hmac.new(key.encode(), body, hashlib.sha256).hexdigest()
    return http("POST", "/lab/session", body, {"X-Lab-Learner": learner, "X-Lab-Signature": sig})


def ws_terminal(token, command, want, timeout=20):
    """Minimal WebSocket client speaking ttyd's protocol through the Worker."""
    host, port = BASE.split("//")[1].split(":")
    s = socket.create_connection((host, int(port)), timeout=timeout)
    key = base64.b64encode(os.urandom(16)).decode()
    s.sendall((f"GET /t/{token}/ws HTTP/1.1\r\nHost: {host}:{port}\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
               f"Sec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\nSec-WebSocket-Protocol: tty\r\n\r\n").encode())
    head = b""
    while b"\r\n\r\n" not in head:
        head += s.recv(1)
    if b" 101 " not in head.split(b"\r\n")[0]:
        return False, head.decode(errors="replace")[:80]

    def send(op, payload):
        mask = os.urandom(4)
        n = len(payload)
        hdr = bytes([0x80 | op]) + (bytes([0x80 | n]) if n < 126 else bytes([0x80 | 126]) + struct.pack(">H", n))
        s.sendall(hdr + mask + bytes(b ^ mask[i % 4] for i, b in enumerate(payload)))

    send(1, json.dumps({"AuthToken": "", "columns": 80, "rows": 24}).encode())
    time.sleep(1)
    send(2, b"0" + command.encode() + b"\n")
    buf, end = b"", time.time() + timeout
    s.settimeout(2)
    while time.time() < end:
        try:
            h = s.recv(2)
            if len(h) < 2:
                break
            n = h[1] & 0x7F
            if n == 126:
                n = struct.unpack(">H", s.recv(2))[0]
            data = b""
            while len(data) < n:
                data += s.recv(n - len(data))
            buf += data
            if want.encode() in buf:
                s.close()
                return True, ""
        except socket.timeout:
            continue
    s.close()
    return False, buf[-300:].decode(errors="replace")


def container_id():
    rows = subprocess.run(["docker", "ps", "--format", "{{.ID}} {{.Image}}"], capture_output=True, text=True).stdout.splitlines()
    ids = [r.split()[0] for r in rows if r.split()[1].startswith("cloudflare-dev/labcontainer")]
    return ids[0] if ids else None


def main():
    st, body = signed_session(LEARNER)
    check("session: signed request accepted", st == 200, f"{st} {body[:100]}")
    if st != 200:
        return
    sess = json.loads(body)
    token = sess["terminal"].split("/")[2]
    st, _ = signed_session(LEARNER, key_for="someone-else")
    check("session: wrong learner key rejected (401)", st == 401, st)
    st, _ = http("POST", "/lab/session", b"{}", {"X-Lab-Learner": LEARNER, "X-Lab-Signature": "0" * 64})
    check("session: bad signature rejected (401)", st == 401, st)
    st, page = http("GET", sess["app"])
    check("app page loads", st == 200 and b"Siraugga Lab" in page, st)
    st, _ = http("GET", sess["app"][:-3] + "AAA")
    check("tampered token rejected (401)", st == 401, st)
    st, info = http("GET", f"/lab/info/{token}")
    check("lab info (no answers)", st == 200 and b"hello.txt" in info and b"checks" not in info, st)
    st, term = http("GET", f"/t/{token}/")
    check("terminal page served", st == 200 and b"ttyd" in term.lower(), st)

    st, out = http("POST", f"/lab/check/{token}", b'{"step":"1"}')
    check("grader: unsolved step fails", st == 200 and json.loads(out)["passed"] is False, out[:80])

    ok, detail = ws_terminal(token, "whoami > who.txt; echo M$((6*7))K", "M42K")
    check("terminal WebSocket: real shell runs a command", ok, detail)
    cid = container_id()
    check("a real container is running", cid is not None)
    if cid:
        who = subprocess.run(["docker", "exec", cid, "cat", "/home/learner/who.txt"], capture_output=True, text=True).stdout.strip()
        check("terminal runs as non-root 'learner'", who == "learner", who)
        subprocess.run(["docker", "exec", "-u", "learner", "-w", "/home/learner", cid, "bash", "-c", "echo hello > hello.txt"])
    st, out = http("POST", f"/lab/check/{token}", b'{"step":"1"}')
    check("grader: solved step passes", st == 200 and json.loads(out)["passed"] is True, out[:80])
    http("POST", f"/lab/check/{token}", b'{"step":"1"}')   # repeat: must not double-record

    st, out = http("POST", f"/lab/check/{token}", b'{"step":"99"}')
    check("grader: unknown step -> 404", st == 404, st)
    st, out = http("POST", f"/lab/check/{token}", b'{"step":"../../etc/passwd"}')
    check("grader: path trick rejected", st == 404, st)
    st, _ = http("POST", "/lab/session", json.dumps({"lab": "../x"}).encode(),
                 {"X-Lab-Learner": LEARNER, "X-Lab-Signature": "0" * 64})
    check("session: junk lab name rejected", st in (400, 401), st)
    print(f"\n{sum(results)}/{len(results)} passed")
    sys.exit(0 if all(results) else 1)


main()
