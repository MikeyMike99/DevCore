"""Connector from Siraugga to the Siraugga Lab Cloud (labcloud/): runs a course step's command in the
learner's OWN real-Linux container instead of on this server.

OFF by default. It turns on only when both are set in the server's environment:
    SIRAUGGA_LAB_URL     where the Lab Cloud answers (e.g. http://127.0.0.1:8788 locally)
    SIRAUGGA_LAB_SECRET  the Lab Cloud's master secret (the server never prints it)
If the Lab Cloud cannot be reached, callers fall back to the old sandbox, so a course never breaks.
"""
import hashlib
import hmac
import json
import logging
import os
import re
import urllib.error
import urllib.request

log = logging.getLogger("siraugga.lab_cloud")

# course id -> lab image folder in labcloud/image/labs/
COURSE_LABS = {"linux_essentials_step_by_step": "linux-essentials"}

_ID_RE = re.compile(r"^[A-Za-z0-9_.@-]{1,64}$")


class LabCloudUnavailable(Exception):
    """The Lab Cloud is off, unreachable or refused the request: use the fallback."""


def configured() -> bool:
    return bool(os.environ.get("SIRAUGGA_LAB_URL") and os.environ.get("SIRAUGGA_LAB_SECRET"))


def lab_for_course(course_id: str):
    """The lab image to use for this course, or None (course not mapped, or Lab Cloud not configured)."""
    return COURSE_LABS.get(course_id) if configured() else None


def learner_id(sandbox_dir: str, jailed: bool) -> str:
    """A stable, unique id per learner: their private sandbox folder name (handles can repeat; this cannot)."""
    if not jailed:
        return "owner"
    name = re.sub(r"[^A-Za-z0-9_.@-]", "", os.path.basename(os.path.normpath(sandbox_dir)))[:60]
    return f"lc-{name}" if name else "lc-unknown"


def run_command(learner: str, lab: str, command: str, timeout: float = 75.0):
    """Run one command in the learner's container. Returns (returncode, output text)."""
    if not configured():
        raise LabCloudUnavailable("not configured")
    if not _ID_RE.match(learner):
        raise LabCloudUnavailable("bad learner id")
    master = os.environ["SIRAUGGA_LAB_SECRET"]
    body = json.dumps({"lab": lab, "command": command}, separators=(",", ":"), sort_keys=True).encode()
    key = hmac.new(master.encode(), learner.encode(), hashlib.sha256).hexdigest()   # the learner's own key
    sig = hmac.new(key.encode(), body, hashlib.sha256).hexdigest()
    req = urllib.request.Request(
        os.environ["SIRAUGGA_LAB_URL"].rstrip("/") + "/lab/run", data=body, method="POST",
        headers={"Content-Type": "application/json", "X-Lab-Learner": learner, "X-Lab-Signature": sig,
                 "User-Agent": "Siraugga/lab-cloud"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.loads(r.read().decode())
        return int(data.get("returncode", 1)), str(data.get("output", ""))
    except urllib.error.HTTPError as e:
        log.warning("lab cloud refused the request (HTTP %s)", e.code)
        if e.code == 400:
            return 2, "The lab computer rejected that command."
        raise LabCloudUnavailable(f"HTTP {e.code}") from e
    except (urllib.error.URLError, OSError, ValueError, TimeoutError) as e:
        log.warning("lab cloud unreachable: %s", type(e).__name__)
        raise LabCloudUnavailable(type(e).__name__) from e
