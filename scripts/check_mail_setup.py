"""Shows how Siraugga mail is set up, without printing any secret and without sending anything."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from services.mail import config as c  # noqa: E402

k = c.config
backend = str(getattr(k, "MAIL_BACKEND", "") or "").lower()
print("backend:", backend or "(none)")
print("dry run:", os.environ.get("DEVCORE_MAIL_DRY_RUN", "") == "1")
for name in sorted(a for a in dir(k) if a.isupper() and ("SMTP" in a or "MAIL" in a)):
    v = getattr(k, name, None)
    secret = any(w in name for w in ("PASS", "KEY", "SECRET", "TOKEN"))
    print(f"  {name}: " + ("(set)" if secret and v else "(empty)" if secret else repr(v)))
print("RESULT:", "mail is only written to a local folder, NOT sent" if backend == "local" else "real sending is configured" if backend else "unknown")
