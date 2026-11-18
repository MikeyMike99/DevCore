"""Talks to the Siraugga lab server over the domain (same pattern as JOSHY -> api.mikeytech.dev).

Only commands a lab marks as 'remote' (they would change something on OUR side) go
through here. If the server cannot be reached, the caller gets a clearly-marked
simulated reply and the request is queued in a local outbox, then replayed by `sync`.

Security: each learner has their OWN key (issued at enrolment, stored in config.json).
Requests are signed HMAC-SHA256(body) with that key, so one leaked key only affects one learner.
Every request carries a random id; the server ignores ids it has already seen, so a replay
after a flaky connection can never double-count.
"""
import hashlib
import hmac
import json
import os
import time
import urllib.error
import urllib.request
import uuid

DEFAULT_BASE = "https://api.mikeytech.dev/lab"
_NET_ERRORS = (urllib.error.URLError, OSError, ValueError, TimeoutError)


class ServerRefused(Exception):
    """The server was reached but said no (bad key, command not allowed). Not queued, not simulated."""


def load_config(state_dir: str) -> dict:
    try:
        with open(os.path.join(state_dir, "config.json"), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def save_config(state_dir: str, cfg: dict) -> None:
    os.makedirs(state_dir, exist_ok=True)
    with open(os.path.join(state_dir, "config.json"), "w", encoding="utf-8") as f:
        json.dump(cfg, f)


class Remote:
    def __init__(self, state_dir: str, learner: str = "", key: str = "", base=None, timeout: float = 6.0):
        cfg = load_config(state_dir)
        self.learner = learner or os.environ.get("SIRAUGGA_LAB_LEARNER") or cfg.get("learner", "")
        self.key = key or os.environ.get("SIRAUGGA_LAB_KEY") or cfg.get("key", "")
        self.base = (base or os.environ.get("SIRAUGGA_LAB_API") or cfg.get("api") or DEFAULT_BASE).rstrip("/")
        self.timeout = timeout
        self.outbox = os.path.join(state_dir, "outbox.jsonl")
        os.makedirs(state_dir, exist_ok=True)

    def _post(self, path: str, payload: dict) -> dict:
        body = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
        sig = hmac.new(self.key.encode(), body, hashlib.sha256).hexdigest()
        req = urllib.request.Request(
            self.base + path, data=body, method="POST",
            headers={"Content-Type": "application/json", "X-Lab-Signature": sig,
                     "X-Lab-Learner": self.learner, "User-Agent": "SirauggaLab/0.2"})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                return json.loads(r.read().decode())
        except urllib.error.HTTPError as e:   # reached the server, but it refused
            if e.code in (400, 401, 403):
                raise ServerRefused(f"server refused ({e.code}) - check your learner id/key") from e
            raise

    def execute(self, lab: str, step: str, command: str, sim_output: str):
        """Returns (was_real, output). Falls back to simulation when the server is unreachable."""
        payload = {"id": uuid.uuid4().hex, "learner": self.learner, "lab": lab, "step": step,
                   "command": command, "ts": int(time.time())}
        try:
            reply = self._post("/exec", payload)
            return True, str(reply.get("output", ""))
        except ServerRefused as e:
            return True, f"[server] {e}"
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
        """Replay queued requests (same ids, so the server de-duplicates). Returns (sent, still_pending)."""
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
            except ServerRefused:
                pass                      # permanently refused: drop it rather than retry forever
            except _NET_ERRORS:
                left.append(item)
        with open(self.outbox, "w", encoding="utf-8") as f:
            f.writelines(json.dumps(i) + "\n" for i in left)
        return sent, len(left)
