"""Talks to the Siraugga lab server over the domain (same pattern as JOSHY -> api.mikeytech.dev).

Only commands a lab marks as 'remote' (they would change something on OUR side) go
through here. If the server cannot be reached, the caller gets a clearly-marked
simulated reply and the request is queued in a local outbox, then replayed by `sync`.
"""
import hashlib
import hmac
import json
import os
import time
import urllib.error
import urllib.request

DEFAULT_BASE = "https://api.mikeytech.dev/lab"
_NET_ERRORS = (urllib.error.URLError, OSError, ValueError, TimeoutError)


class Remote:
    def __init__(self, state_dir: str, token: str = "", base=None, timeout: float = 6.0):
        self.base = (base or os.environ.get("SIRAUGGA_LAB_API") or DEFAULT_BASE).rstrip("/")
        self.token = token
        self.timeout = timeout
        self.outbox = os.path.join(state_dir, "outbox.jsonl")
        os.makedirs(state_dir, exist_ok=True)

    def _post(self, path: str, payload: dict) -> dict:
        body = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
        sig = hmac.new(self.token.encode(), body, hashlib.sha256).hexdigest()
        req = urllib.request.Request(
            self.base + path, data=body, method="POST",
            headers={"Content-Type": "application/json", "X-Lab-Signature": sig,
                     "User-Agent": "SirauggaLab/0.1"})
        with urllib.request.urlopen(req, timeout=self.timeout) as r:
            return json.loads(r.read().decode())

    def execute(self, lab: str, step: str, command: str, sim_output: str):
        """Returns (was_real, output). Falls back to simulation when the server is unreachable."""
        payload = {"lab": lab, "step": step, "command": command, "ts": int(time.time())}
        try:
            reply = self._post("/exec", payload)
            return True, str(reply.get("output", ""))
        except _NET_ERRORS:
            with open(self.outbox, "a", encoding="utf-8") as f:
                f.write(json.dumps(payload) + "\n")
            return False, sim_output

    def pending(self) -> int:
        try:
            with open(self.outbox, encoding="utf-8") as f:
                return sum(1 for ln in f if ln.strip())
        except FileNotFoundError:
            return 0

    def sync(self):
        """Replay queued requests. Returns (sent, still_pending)."""
        try:
            with open(self.outbox, encoding="utf-8") as f:
                queue = [json.loads(ln) for ln in f if ln.strip()]
        except FileNotFoundError:
            return 0, 0
        left, sent = [], 0
        for item in queue:
            try:
                self._post("/exec", {**item, "replayed": True})
                sent += 1
            except _NET_ERRORS:
                left.append(item)
        with open(self.outbox, "w", encoding="utf-8") as f:
            f.writelines(json.dumps(i) + "\n" for i in left)
        return sent, len(left)
