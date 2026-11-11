"""
Access keys: sign in to Siraugga on any device with a passkey (Windows Hello, fingerprint,
face or phone PIN), including on the public domain.

  * The owner sets an OWNER PASSWORD (only while already Super Admin).
  * On a new device the owner opens /setup, types that password and registers an access key
    on the device. From then on the device signs in with the key alone, as Super Admin.
  * For anyone else, the owner creates a ONE-TIME SETUP LINK and picks their role first.
    The person opens it, registers a key on their device, and gets exactly that role.

Stored in ~/.config/devcore/device_keys.json (mode 600):
  owner_password  werkzeug scrypt hash (never the password)
  keys            credential id -> public key, sign count, name, role, label, dates
  invites         sha256(code) -> name, role, expiry   (codes are single use)
  people          username -> name, role, email, password hash (invited people's own sign-in)

Signing in with a password always takes three steps, for the owner and for everyone else:
username + password, then the account's email address, then a one-time link emailed to that
address. Opening the link signs in that device, which may then add a passkey (fingerprint /
face / PIN) so it signs in by itself from then on.
Challenges for an in-progress setup/sign-in live in memory only and expire in 5 minutes.

A passkey's private key never leaves the user's device; the server only keeps the public key.
Passkeys are bound to the website they were made on (mikeytech.dev or localhost).
"""
import hashlib
import json
import os
import secrets
import threading
import time

STORE_FILE = os.path.expanduser("~/.config/devcore/device_keys.json")
OWNER_ROLE = "owner"                      # stored on the owner's keys; signs in as Super Admin
# Roles the owner may hand out with a setup link ("owner" is deliberately not one of them).
INVITE_ROLES = {
    "guest": "Guest (chat only)",
    "modder": "Modder",
    "gamedev": "Game developer",
    # No "admin" here: in core/roles.py "admin" is a Tier-5 (Super Admin) role, so an invite
    # must never hand it out. Add a limited Tier-4 admin role first, then offer that.
}
INVITE_TTL = 3 * 86400                    # a setup link works once, within 3 days
# "Forgot your password?": an owner setup link emailed to the DevCore inbox. Whoever can read
# that inbox can use it, so it is short-lived and rate-limited (counted across all visitors).
RECOVERY_TTL = 30 * 60
RECOVERY_PER_DAY = 3
RECOVERY_MIN_GAP = 10 * 60
_recovery_sent = []                       # timestamps (memory only)
CHALLENGE_TTL = 300
MIN_PASSWORD_LEN = 10
# Wrong owner passwords: at most this many per window, counted across ALL visitors
# (behind Cloudflare an attacker can change IP, so a per-IP limit wouldn't hold).
PW_FAIL_LIMIT = 8
PW_FAIL_WINDOW = 15 * 60

_lock = threading.Lock()
_challenges = {}                          # id -> {...}   (memory only)
_pw_failures = []                         # timestamps of recent wrong passwords


# ---- storage -------------------------------------------------------------------------------
def _load() -> dict:
    try:
        with open(STORE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        data = {}
    if not isinstance(data, dict):
        data = {}
    data.setdefault("owner_password", None)
    data.setdefault("people", {})
    data.setdefault("keys", {})
    data.setdefault("invites", {})
    return data


def _save(data: dict) -> None:
    os.makedirs(os.path.dirname(STORE_FILE), mode=0o700, exist_ok=True)
    tmp = STORE_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=1)
    try:
        os.chmod(tmp, 0o600)
    except Exception:
        pass
    os.replace(tmp, STORE_FILE)


def _h(value: str) -> str:
    return hashlib.sha256(("devcore-device-key|" + value).encode()).hexdigest()


# ---- owner password ------------------------------------------------------------------------
def has_password() -> bool:
    return bool(_load().get("owner_password"))


def set_password(password: str) -> None:
    from werkzeug.security import generate_password_hash
    if not isinstance(password, str) or len(password) < MIN_PASSWORD_LEN:
        raise ValueError(f"Use at least {MIN_PASSWORD_LEN} characters.")
    if len(password) > 256:
        raise ValueError("That password is too long.")
    with _lock:
        data = _load()
        data["owner_password"] = generate_password_hash(password)
        _save(data)


def check_password(password: str) -> str:
    """'' when correct; otherwise a message saying why not."""
    from werkzeug.security import check_password_hash
    now = time.time()
    with _lock:
        _pw_failures[:] = [t for t in _pw_failures if t > now - PW_FAIL_WINDOW]
        if len(_pw_failures) >= PW_FAIL_LIMIT:
            wait = int((_pw_failures[0] + PW_FAIL_WINDOW - now) / 60) + 1
            return f"Too many wrong passwords. Try again in {wait} minute(s)."
        if not password:          # nothing typed: not a guess, so it doesn't count
            return "Type your owner password first."
        stored = _load().get("owner_password")
        if not stored:
            return "No owner password has been set yet. Set one in Settings on a device where you are already Super Admin."
        if isinstance(password, str) and 0 < len(password) <= 256 and check_password_hash(stored, password):
            return ""
        _pw_failures.append(now)
        return "Wrong password."


# ---- invites (one-time setup links) --------------------------------------------------------
# ---- invited people's own username + password -------------------------------------------
_USERNAME_RE = __import__("re").compile(r"^[a-z0-9][a-z0-9._-]{2,31}$")


def clean_username(username: str) -> str:
    u = (username or "").strip().lower()
    if not _USERNAME_RE.match(u):
        raise ValueError("Choose a username of 3 to 32 letters or numbers (dots, dashes and underscores are fine).")
    if u in ("owner", "admin", "root", "superadmin", "super_admin", "michael"):
        raise ValueError("That username is reserved. Choose another one.")
    return u


def _check_new_password(password: str) -> str:
    from werkzeug.security import generate_password_hash
    if not isinstance(password, str) or len(password) < MIN_PASSWORD_LEN:
        raise ValueError(f"The password needs at least {MIN_PASSWORD_LEN} characters.")
    if len(password) > 256:
        raise ValueError("That password is too long.")
    return generate_password_hash(password)


def delete_person(username: str) -> bool:
    """Owner: remove an invited person's password sign-in and all their access keys."""
    with _lock:
        data = _load()
        rec = data["people"].pop(str(username or "").lower(), None)
        if not rec:
            return False
        for cid in [c for c, k in data["keys"].items() if k.get("username") == username.lower()]:
            del data["keys"][cid]
        _save(data)
    return True


LOGIN_STEP_TTL = 10 * 60        # between a correct password and asking for the email link
LOGIN_LINK_TTL = 15 * 60        # the emailed sign-in link
LOGIN_EMAIL_TRIES = 3           # wrong email addresses per password step
_login_steps = {}               # id -> {"who": {...}, "expires_at", "tries"}   (memory only)
_login_links = {}               # sha256(code) -> {"who": {...}, "expires_at"}  (memory only)


def _too_many_failures(now: float) -> str:
    _pw_failures[:] = [t for t in _pw_failures if t > now - PW_FAIL_WINDOW]
    if len(_pw_failures) >= PW_FAIL_LIMIT:
        wait = int((_pw_failures[0] + PW_FAIL_WINDOW - now) / 60) + 1
        return f"Too many wrong passwords. Try again in {wait} minute(s)."
    return ""


def start_login(username: str, password: str) -> str:
    """Step 1: username + password. Returns a step id; raises ValueError with a message.
    The owner's username can be anything; invited people use the username they chose."""
    from werkzeug.security import check_password_hash
    if not password:
        raise ValueError("Type your password first.")
    uname = str(username or "").strip().lower()
    now = time.time()
    with _lock:
        msg = _too_many_failures(now)
        if msg:
            raise ValueError(msg)
        data = _load()
        who = None
        person = data["people"].get(uname)
        if person and len(password) <= 256 and check_password_hash(person["pw_hash"], password):
            who = {"kind": "person", "username": uname}
        elif data.get("owner_password") and len(password) <= 256 \
                and check_password_hash(data["owner_password"], password):
            who = {"kind": "owner"}
        if not who:
            _pw_failures.append(now)
            raise ValueError("Wrong username or password.")
        for k in [k for k, v in _login_steps.items() if v["expires_at"] <= now]:
            _login_steps.pop(k, None)
        sid = secrets.token_urlsafe(18)
        _login_steps[sid] = {"who": who, "expires_at": now + LOGIN_STEP_TTL, "tries": 0}
    return sid


def login_email_target(step_id: str, email: str) -> dict:
    """Step 2: the email address. For a person it must match the one on their account; for
    the owner the mail sender checks it against the owner inbox (returns to="__admin__").
    Returns {"to", "typed", "who", "name"}; raises ValueError."""
    typed = clean_email(email)
    if not typed:
        raise ValueError("Type your email address.")
    now = time.time()
    with _lock:
        st = _login_steps.get(step_id or "")
        if not st or st["expires_at"] <= now:
            _login_steps.pop(step_id or "", None)
            raise ValueError("This sign-in took too long. Type your username and password again.")
        who = st["who"]
        if who["kind"] == "owner":
            return {"to": "__admin__", "typed": typed, "who": who, "name": "Owner"}
        person = _load()["people"].get(who["username"])
        if not person:
            raise ValueError("This account no longer exists.")
        if person.get("email", "").lower() != typed:
            note_wrong_email(step_id, locked=True)
            raise ValueError("That email address doesn't match this account.")
        return {"to": person["email"], "typed": typed, "who": who, "name": person.get("name") or who["username"]}


def note_wrong_email(step_id: str, locked: bool = False) -> None:
    """Count a wrong email; after LOGIN_EMAIL_TRIES the password step must be redone."""
    def _do():
        st = _login_steps.get(step_id or "")
        if st:
            st["tries"] += 1
            if st["tries"] >= LOGIN_EMAIL_TRIES:
                _login_steps.pop(step_id, None)
    if locked:
        _do()
    else:
        with _lock:
            _do()


def new_login_link(step_id: str) -> str:
    """Step 3: a one-time sign-in code for the email (the step is used up)."""
    now = time.time()
    with _lock:
        st = _login_steps.pop(step_id or "", None)
        if not st or st["expires_at"] <= now:
            raise ValueError("This sign-in took too long. Type your username and password again.")
        for k in [k for k, v in _login_links.items() if v["expires_at"] <= now]:
            _login_links.pop(k, None)
        code = secrets.token_urlsafe(32)
        _login_links[_h(code)] = {"who": st["who"], "expires_at": now + LOGIN_LINK_TTL}
    return code


def cancel_login_link(code: str) -> None:
    with _lock:
        _login_links.pop(_h(code or ""), None)


def take_login_link(code: str) -> dict:
    """Open the emailed link: returns the user record to sign in ({role, name, ...}), once."""
    if not code or len(code) > 100:
        raise ValueError("This sign-in link is not valid.")
    with _lock:
        link = _login_links.pop(_h(code), None)
        if not link or link["expires_at"] <= time.time():
            raise ValueError("This sign-in link has expired or was already used. Sign in again to get a new one.")
        who = link["who"]
        if who["kind"] == "owner":
            return {"role": OWNER_ROLE, "name": "Owner"}
        p = _load()["people"].get(who["username"])
        if not p:
            raise ValueError("This account no longer exists.")
        return {"role": p["role"], "name": p.get("name") or who["username"], "username": who["username"],
                "email": p.get("email", ""), "project": p.get("project", ""), "parts": p.get("parts") or []}


def person_record(username: str):
    p = _load()["people"].get(str(username or "").lower())
    return dict(p, username=username.lower()) if p else None


_EMAIL_RE = __import__("re").compile(r"^[^@\s<>\"']{1,64}@[A-Za-z0-9.-]{1,190}\.[A-Za-z]{2,24}$")


def clean_email(email: str) -> str:
    """'' for no email; the lower-cased address when valid; raises ValueError otherwise."""
    email = (email or "").strip().lower()
    if not email:
        return ""
    if not _EMAIL_RE.match(email):
        raise ValueError("That email address doesn't look right.")
    return email


DEV_ROLE = "gamedev"          # in-game/app developer: works only on what is handed to them


def _clean_assignment(role: str, project: str, parts):
    """A developer must be handed a project (and optionally parts of it); others get none."""
    if role != DEV_ROLE:
        return "", []
    from security import dev_workspaces
    project = (project or "").strip()
    if not project or project.startswith(".") or "/" in project or "\\" in project \
            or not (dev_workspaces.PLAYGROUND / project).is_dir():
        raise ValueError("Pick the project this developer may work on.")
    return project, dev_workspaces.clean_parts(project, parts)


def create_invite(name: str, role: str, email: str = "", ttl: int = INVITE_TTL,
                  project: str = "", parts=None) -> str:
    name = (name or "").strip()[:60]
    if not name:
        raise ValueError("Give the person a name so you can recognise their key later.")
    if role not in INVITE_ROLES:
        raise ValueError("Pick one of the listed roles.")
    email = clean_email(email)
    if not email:
        raise ValueError("Add their email address: everyone confirms sign-in with a link sent to it.")
    project, parts = _clean_assignment(role, project, parts)
    code = secrets.token_urlsafe(24)
    now = time.time()
    with _lock:
        data = _load()
        data["invites"] = {k: v for k, v in data["invites"].items() if v.get("expires_at", 0) > now}
        data["invites"][_h(code)] = {"id": "inv-" + secrets.token_hex(4), "name": name, "role": role,
                                     "email": email, "project": project, "parts": parts,
                                     "created_at": now, "expires_at": now + ttl}
        _save(data)
    return code


# "Invited before? Email me a new link": per address, at most this many a day.
PERSON_RECOVERY_PER_DAY = 3
_person_recovery = {}                     # email -> [timestamps]   (memory only)


def create_person_recovery_invite(email: str):
    """A fresh 30-minute link with the SAME name and role as an existing invited person's key,
    for their own email address. Returns (code, name, email), or None when the address isn't
    known or its daily limit is used up. Never for the owner (owner recovery goes to the
    owner inbox only)."""
    try:
        email = clean_email(email)
    except ValueError:
        return None
    if not email:
        return None
    now = time.time()
    with _lock:
        sent = [t for t in _person_recovery.get(email, []) if t > now - 86400]
        if len(sent) >= PERSON_RECOVERY_PER_DAY:
            return None
        person = next((k for k in _load()["keys"].values()
                       if k.get("email") == email and k.get("role") in INVITE_ROLES), None)
        if not person:
            return None
        sent.append(now)
        _person_recovery[email] = sent
    return (create_invite(person["name"], person["role"], email, ttl=RECOVERY_TTL,
                          project=person.get("project", ""), parts=person.get("parts") or []),
            person["name"], email)


def create_recovery_invite() -> str:
    """An OWNER setup link for the recovery email. Raises ValueError when the limit is reached."""
    now = time.time()
    with _lock:
        _recovery_sent[:] = [t for t in _recovery_sent if t > now - 86400]
        if len(_recovery_sent) >= RECOVERY_PER_DAY:
            raise ValueError("limit")
        if _recovery_sent and _recovery_sent[-1] > now - RECOVERY_MIN_GAP:
            raise ValueError("limit")
        _recovery_sent.append(now)
        code = secrets.token_urlsafe(24)
        data = _load()
        data["invites"] = {k: v for k, v in data["invites"].items() if v.get("expires_at", 0) > now}
        data["invites"][_h(code)] = {"id": "rec-" + secrets.token_hex(4), "name": "Owner", "role": OWNER_ROLE,
                                     "created_at": now, "expires_at": now + RECOVERY_TTL, "recovery": True}
        _save(data)
    return code


def peek_invite(code: str):
    if not code or len(code) > 100:
        return None
    inv = _load()["invites"].get(_h(code))
    return inv if inv and inv.get("expires_at", 0) > time.time() else None


def _take_invite(data: dict, code: str):
    inv = data["invites"].pop(_h(code), None)
    return inv if inv and inv.get("expires_at", 0) > time.time() else None


def delete_invite(invite_id: str) -> bool:
    with _lock:
        data = _load()
        for k, v in list(data["invites"].items()):
            if v.get("id") == invite_id:
                del data["invites"][k]
                _save(data)
                return True
    return False


# ---- keys ----------------------------------------------------------------------------------
def overview() -> dict:
    """Non-secret summary for the owner's Settings panel."""
    data = _load()
    now = time.time()
    keys = [{"id": cid[:16], "name": k.get("name"), "role": k.get("role"), "label": k.get("label"), "email": k.get("email", ""),
             "project": k.get("project", ""), "parts": k.get("parts") or [],
             "rp_id": k.get("rp_id"), "created_at": k.get("created_at"), "last_used": k.get("last_used")}
            for cid, k in data["keys"].items()]
    invites = [{"id": v["id"], "name": "Recovery email" if v.get("recovery") else v["name"], "role": v["role"],
                "email": v.get("email", ""), "project": v.get("project", ""), "parts": v.get("parts") or [],
                "expires_at": v["expires_at"]}
               for v in data["invites"].values() if v.get("expires_at", 0) > now]
    people = [{"username": u, "name": p.get("name"), "role": p.get("role"), "email": p.get("email", "")}
              for u, p in data["people"].items()]
    return {"has_password": bool(data.get("owner_password")), "keys": keys, "invites": invites, "people": people,
            "roles": INVITE_ROLES,                                            # what may be handed out
            "role_labels": {**INVITE_ROLES, OWNER_ROLE: "Super Admin (you)"}}  # display only


def delete_key(short_id: str) -> bool:
    with _lock:
        data = _load()
        for cid in list(data["keys"]):
            if cid[:16] == short_id:
                del data["keys"][cid]
                _save(data)
                return True
    return False


def _new_challenge(kind: str, **extra) -> tuple:
    cid = secrets.token_urlsafe(16)
    now = time.time()
    with _lock:
        for k in [k for k, v in _challenges.items() if v["expires_at"] <= now]:
            _challenges.pop(k, None)
        if len(_challenges) > 500:            # flood guard
            raise ValueError("Too many sign-ins in progress. Try again in a minute.")
        challenge = secrets.token_bytes(32)
        _challenges[cid] = {"kind": kind, "challenge": challenge, "expires_at": now + CHALLENGE_TTL, **extra}
    return cid, challenge


def _pop_challenge(cid: str, kind: str):
    with _lock:
        ch = _challenges.pop(cid or "", None)
    if not ch or ch["kind"] != kind or ch["expires_at"] <= time.time():
        return None
    return ch


def registration_options(rp_id: str, *, password: str = "", invite: str = "", owner_ok: bool = False,
                         username: str = "", new_password: str = "", person: dict = None) -> dict:
    """Step 1 of setting up a device. Proves the right to add a key (owner password or a
    one-time link) and returns the browser's passkey-creation options."""
    from webauthn import generate_registration_options, options_to_json
    from webauthn.helpers.structs import (AuthenticatorSelectionCriteria, ResidentKeyRequirement,
                                          UserVerificationRequirement)
    pw_hash = ""
    if person:                 # an invited person already signed in (password + email link)
        inv = {"email": person.get("email", ""), "project": person.get("project", ""), "parts": person.get("parts") or []}
        name, role, username = person.get("name") or person["username"], person["role"], person["username"]
        invite = ""
    elif invite:
        inv = peek_invite(invite)
        if not inv:
            raise ValueError("This setup link has expired or was already used. Ask for a new one.")
        name, role = inv["name"], inv["role"]
        if role != OWNER_ROLE:
            # Everyone gets the same sign-in as the owner: username + password + email link.
            username = clean_username(username)
            if not inv.get("email"):
                raise ValueError("This invitation has no email address, so it can't be used for sign-in. "
                                 "Ask the owner for a new invitation with your email.")
            other = _load()["people"].get(username)
            if other and other.get("email", "").lower() != inv["email"].lower():
                raise ValueError("That username is taken. Choose another one.")
            pw_hash = _check_new_password(new_password)
        else:
            username = ""
    else:
        if not owner_ok:   # owner_ok: the caller is already signed in as the verified owner
            # A password alone is not enough any more: sign in (password + email link) first.
            raise ValueError("Sign in first (username, password and the emailed link), then add fingerprint or face.")
        name, role = "Owner", OWNER_ROLE
    user_handle = secrets.token_bytes(16)
    has_inv = bool(invite or person)
    cid, challenge = _new_challenge("register", rp_id=rp_id, name=name, role=role, invite=invite,
                                    user_handle=user_handle, email=(inv.get("email", "") if has_inv else ""),
                                    project=(inv.get("project", "") if has_inv else ""),
                                    parts=(inv.get("parts") or [] if has_inv else []),
                                    username=(username if role != OWNER_ROLE else ""), pw_hash=pw_hash)
    opts = generate_registration_options(
        rp_id=rp_id, rp_name="Siraugga", user_id=user_handle,
        user_name=f"{name} (Siraugga)" if role != OWNER_ROLE else "Siraugga owner",
        user_display_name=name, challenge=challenge, timeout=CHALLENGE_TTL * 1000,
        authenticator_selection=AuthenticatorSelectionCriteria(
            resident_key=ResidentKeyRequirement.REQUIRED,          # lets the key sign in without a username
            user_verification=UserVerificationRequirement.REQUIRED),  # fingerprint / face / PIN every time
    )
    return {"setup_id": cid, "options": json.loads(options_to_json(opts)), "name": name, "role": role}


def finish_registration(setup_id: str, credential: dict, origin: str, label: str = "") -> dict:
    """Step 2: verify the new passkey and store it. Returns the key's user record."""
    from webauthn import verify_registration_response
    from webauthn.helpers import bytes_to_base64url
    ch = _pop_challenge(setup_id, "register")
    if not ch:
        raise ValueError("This setup took too long or was already finished. Start again.")
    v = verify_registration_response(credential=credential, expected_challenge=ch["challenge"],
                                     expected_rp_id=ch["rp_id"], expected_origin=origin,
                                     require_user_verification=True)
    cred_id = bytes_to_base64url(v.credential_id)
    now = time.time()
    with _lock:
        data = _load()
        if ch["invite"] and not _take_invite(data, ch["invite"]):
            raise ValueError("This setup link was used by someone else in the meantime.")
        data["keys"][cred_id] = {
            "public_key": bytes_to_base64url(v.credential_public_key), "sign_count": v.sign_count,
            "name": ch["name"], "role": ch["role"], "rp_id": ch["rp_id"], "email": ch.get("email", ""),
            "project": ch.get("project", ""), "parts": ch.get("parts") or [],
            "label": str(label or "")[:120], "created_at": now, "last_used": now,
            "username": ch.get("username", ""),
        }
        if ch.get("username") and ch.get("pw_hash"):
            data["people"][ch["username"]] = {
                "name": ch["name"], "role": ch["role"], "email": ch.get("email", ""),
                "project": ch.get("project", ""), "parts": ch.get("parts") or [],
                "pw_hash": ch["pw_hash"], "created_at": now}
        _save(data)
    return {"name": ch["name"], "role": ch["role"], "project": ch.get("project", ""), "parts": ch.get("parts") or [],
            "username": ch.get("username", "")}


def authentication_options(rp_id: str) -> dict:
    from webauthn import generate_authentication_options, options_to_json
    from webauthn.helpers.structs import UserVerificationRequirement
    cid, challenge = _new_challenge("login", rp_id=rp_id)
    opts = generate_authentication_options(rp_id=rp_id, challenge=challenge, timeout=CHALLENGE_TTL * 1000,
                                           user_verification=UserVerificationRequirement.REQUIRED)
    return {"login_id": cid, "options": json.loads(options_to_json(opts))}


def finish_authentication(login_id: str, credential: dict, origin: str) -> dict:
    """Verify a sign-in. Returns the key's user record ({name, role})."""
    from webauthn import verify_authentication_response
    from webauthn.helpers import base64url_to_bytes
    ch = _pop_challenge(login_id, "login")
    if not ch:
        raise ValueError("This sign-in took too long. Try again.")
    cred_id = str((credential or {}).get("id") or "")
    with _lock:
        data = _load()
        rec = data["keys"].get(cred_id)
        if not rec or rec.get("rp_id") != ch["rp_id"]:
            raise ValueError("This access key isn't registered here (it may have been removed). Set this device up again.")
        v = verify_authentication_response(
            credential=credential, expected_challenge=ch["challenge"], expected_rp_id=ch["rp_id"],
            expected_origin=origin, credential_public_key=base64url_to_bytes(rec["public_key"]),
            credential_current_sign_count=int(rec.get("sign_count") or 0), require_user_verification=True)
        rec["sign_count"] = v.new_sign_count
        rec["last_used"] = time.time()
        _save(data)
    return {"name": rec["name"], "role": rec["role"], "project": rec.get("project", ""), "parts": rec.get("parts") or [],
            "username": rec.get("username", "")}
