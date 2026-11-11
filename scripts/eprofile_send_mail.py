"""
Sends one email through the e_profile email engine (Gmail SMTP or its local mock mailbox).

Runs in its own process so e_profile's `config` module never clashes with DevCore's
imports. Reads {"to", "subject", "html", "text"} as JSON on stdin and prints
{"ok", "message", "status"} as JSON. "to": "__admin__" sends to the DevCore inbox
(TICKET_ADMIN_EMAIL, else e_profile's MAIL_USERNAME / MAIL_DEFAULT_SENDER).
"""
import json
import os
import sys
import types


def _shim_dotenv() -> None:
    """e_profile's config imports python-dotenv; provide a minimal loader if it is not installed."""
    try:
        import dotenv  # noqa: F401
        return
    except ImportError:
        pass

    def load_dotenv(path=None, override=False, **_kw):
        try:
            with open(path or ".env", "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    k, v = line.split("=", 1)
                    k = k.strip().removeprefix("export ").strip()
                    v = v.strip()
                    if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
                        v = v[1:-1]
                    if override or k not in os.environ:
                        os.environ[k] = v
            return True
        except OSError:
            return False

    sys.modules["dotenv"] = types.SimpleNamespace(load_dotenv=load_dotenv)


def main() -> int:
    devcore = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    # e_profile lives in DevCore's playground; the sibling folder is the old layout (and PythonAnywhere's).
    root = os.environ.get("EPROFILE_ROOT") or next(
        (p for p in (os.path.join(devcore, "playground", "e_profile"), os.path.join(os.path.dirname(devcore), "e_profile"))
         if os.path.isfile(os.path.join(p, "email_engine.py"))),
        os.path.join(devcore, "playground", "e_profile"))
    try:
        req = json.loads(sys.stdin.read() or "{}")
        _shim_dotenv()
        sys.path.insert(0, root)
        os.chdir(root)
        import email_engine
        cfg = email_engine.config
        to = req.get("to") or ""
        if to == "__admin__":
            to = os.environ.get("TICKET_ADMIN_EMAIL") or cfg.MAIL_USERNAME or cfg.MAIL_DEFAULT_SENDER
            # Sign-in check: send only if the address the person typed IS the owner inbox.
            # The real address is never printed back.
            want = str(req.get("only_if_matches") or "").strip().lower()
            if want and want != str(to or "").strip().lower():
                print(json.dumps({"ok": False, "message": "Address does not match.", "status": "mismatch"}))
                return 1
        if not to:
            print(json.dumps({"ok": False, "message": "No recipient address is configured."}))
            return 1
        ok, message, record = email_engine.send_email(to, req.get("subject", ""), req.get("html", ""), req.get("text") or None)
        print(json.dumps({"ok": bool(ok), "message": message, "status": record.get("status")}))
        return 0 if ok else 1
    except Exception as e:
        print(json.dumps({"ok": False, "message": f"Email engine error: {e.__class__.__name__}: {e}"}))
        return 1


if __name__ == "__main__":
    sys.exit(main())
