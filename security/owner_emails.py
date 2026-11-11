"""Extra email addresses the Super Admin (owner) may sign in with, besides the owner inbox.

Kept outside the repo so the addresses never reach GitHub: one address per line (or
comma-separated, # starts a comment) in ~/.config/devcore/owner_emails.txt, plus the
OWNER_EXTRA_EMAILS environment variable. Used only for the owner's sign-in email step and
owner recovery links, never for ticket mail. No imports from DevCore, so the mail sender
script can use it too.
"""
import os

FILE = os.path.expanduser("~/.config/devcore/owner_emails.txt")


def extra_owner_emails() -> list:
    raw = os.environ.get("OWNER_EXTRA_EMAILS", "")
    try:
        with open(FILE, encoding="utf-8") as f:
            raw += "\n" + f.read()
    except OSError:
        pass
    out = []
    for part in raw.replace(",", "\n").splitlines():
        part = part.split("#", 1)[0].strip().lower()
        if "@" in part and part not in out:
            out.append(part)
    return out


def is_extra_owner_email(email: str) -> bool:
    return bool(email) and str(email).strip().lower() in extra_owner_emails()
