"""Admin tool: derive one learner's lab key.  key = HMAC-SHA256(LAB_MASTER_SECRET, learner_id).

    set LAB_MASTER_SECRET=...   (same value as the Worker secret; never commit it)
    python issue_key.py alice
Give the learner:  siraugga-lab login alice <key>
"""
import hashlib
import hmac
import os
import re
import sys

if __name__ == "__main__":
    learner = sys.argv[1] if len(sys.argv) == 2 else ""
    secret = os.environ.get("LAB_MASTER_SECRET", "")
    if not re.fullmatch(r"[A-Za-z0-9_.@-]{1,64}", learner) or not secret:
        sys.exit("usage: LAB_MASTER_SECRET=... python issue_key.py <learner-id>")
    print(hmac.new(secret.encode(), learner.encode(), hashlib.sha256).hexdigest())
