"""Access keys (passkeys) for signing in on any device; see security/device_keys.py."""
import os
import urllib.parse

from quart import Blueprint, current_app, jsonify, request

from security import device_keys as dk

device_keys_bp = Blueprint("device_keys_bp", __name__)

_NO_STORE = {"Cache-Control": "no-store"}


def _public_url() -> str:
    return (os.environ.get("DEVCORE_PUBLIC_URL") or "https://mikeytech.dev").rstrip("/")


def _public_hosts() -> set:
    """Every public address that serves this same Siraugga (the tunnel routes all of them here).
    Extra ones via DEVCORE_PUBLIC_ORIGINS (comma-separated)."""
    hosts = {"mikeytech.dev", "www.mikeytech.dev", "siraugga.mikeytech.dev"}
    pub = urllib.parse.urlparse(_public_url())
    if pub.hostname:
        hosts.add(pub.hostname.lower())
    for o in os.environ.get("DEVCORE_PUBLIC_ORIGINS", "").split(","):
        h = urllib.parse.urlparse(o.strip()).hostname
        if h:
            hosts.add(h.lower())
    return hosts


def _site():
    """(rp_id, origin) for this request, or None when keys can't be used on this address.
    Only Siraugga's own public addresses (from configuration, never what the browser claims).
    The key is tied to the main domain, so one made on www. or siraugga. works on all of them."""
    raw_host = (request.headers.get("Host") or "").strip()
    host = raw_host.split(":")[0].lower()
    if host in _public_hosts():
        base = (urllib.parse.urlparse(_public_url()).hostname or "mikeytech.dev").lower()
        rp_id = base if (host == base or host.endswith("." + base)) else host
        return rp_id, f"https://{host}"
    if host == "localhost":
        return "localhost", f"http://{raw_host}"
    return None


def _bearer() -> str:
    return request.headers.get("Authorization", "").replace("Bearer ", "").strip()


def _is_owner() -> bool:
    sec = current_app.security_mgr
    if sec.is_host_owner_request(request.remote_addr, request.headers):
        return True
    tok = _bearer()
    user = sec.get_user_from_token(tok) if tok else None
    # Owner sessions (key_id "owner") are only ever issued to the verified owner.
    return bool(user and user.get("key_id") == "owner" and sec.check_master_signature())


def _session_person():
    """The invited person signed in with this request's session, or None."""
    tok = _bearer()
    user = current_app.security_mgr.get_user_from_token(tok) if tok else None
    kid = str((user or {}).get("key_id") or "")
    return dk.person_record(kid[4:]) if kid.startswith("dkp-") else None


def _owner_only():
    if not _is_owner():
        return jsonify({"success": False, "error": "Only the Super Admin can do this."}), 403, _NO_STORE
    return None


async def _json() -> dict:
    data = await request.get_json(silent=True)
    return data if isinstance(data, dict) else {}


def _fail(msg: str, code: int = 400):
    return jsonify({"success": False, "error": msg}), code, _NO_STORE


def _site_or_fail():
    site = _site()
    if not site:
        return None, _fail(f"Access keys only work on {_public_url()} (or on localhost on the host computer).")
    return site, None


# ---- the setup page ------------------------------------------------------------------------
@device_keys_bp.route("/setup", methods=["GET"])
async def setup_page():
    # Read directly: importing core.server here would load a second copy of the server
    # (it runs as __main__ from core/).
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "sandbox", "templates", "setup.html")
    try:
        with open(path, "rb") as f:
            page = f.read()
    except OSError:
        return "Setup page not found", 404
    return page, 200, {"Content-Type": "text/html; charset=utf-8", "Cache-Control": "no-store",
                       "Referrer-Policy": "no-referrer", "X-Robots-Tag": "noindex"}


@device_keys_bp.route("/api/device-keys/invite-info", methods=["GET"])
async def invite_info():
    inv = dk.peek_invite((request.args.get("code") or "").strip())
    if not inv:
        return _fail("This setup link has expired or was already used. Ask for a new one.", 404)
    label = "Super Admin (owner)" if inv["role"] == dk.OWNER_ROLE else dk.INVITE_ROLES.get(inv["role"], inv["role"])
    return jsonify({"success": True, "name": inv["name"], "role": inv["role"], "role_label": label,
                    "recovery": bool(inv.get("recovery"))}), 200, _NO_STORE


_RECOVERY_REPLY = ("If recovery is available, a one-time setup link has been emailed to the Siraugga "
                   "owner's inbox. It works for 30 minutes. Open it on this device.")


_PERSON_RECOVERY_REPLY = ("If that address belongs to someone with Siraugga access, a new one-time setup link "
                          "has been emailed to it. It works for 30 minutes. Open it on this device.")


def _email_link(to: str, *, kicker: str, heading: str, intro: str, url: str, expiry: str,
                requested_from: str = "", warn_inbox: bool = False, button: str = "Set up this device",
                only_if_matches: str = ""):
    """Send a setup-link email on a worker thread; returns an awaitable with the send result."""
    import asyncio
    import html
    req = (f'<p style="margin:0 0 10px 0;font-size:13px;color:#9aa4b2;">Requested from: {html.escape(requested_from)}</p>'
           if requested_from else "")
    inbox = (" Anyone who can read this inbox could use the link, so keep this email account protected with "
             "2-step verification.") if warn_inbox else ""
    inner = (
        f'<p style="margin:0 0 6px 0;font-size:12px;font-family:monospace;color:#2dd4bf;text-transform:uppercase;'
        f'letter-spacing:1px;">{html.escape(kicker)}</p>'
        f'<h2 style="margin:0 0 14px 0;color:#fff;font-size:20px;">{html.escape(heading)}</h2>'
        f'<p style="margin:0 0 10px 0;">{intro}</p>{req}'
        '<table role="presentation" cellspacing="0" cellpadding="0" border="0" align="center" style="margin:22px auto 8px auto;"><tr>'
        f'{_mail()._button(url, button, "#0f766e")}</tr></table>'
        f'<p style="margin:10px 0 0 0;font-size:12px;color:#888;">Open this email <strong>on the device you want to use</strong>. '
        f"The link works once and expires in {html.escape(expiry)}. <strong>If you didn't expect this, ignore it.</strong>{inbox}</p>")
    text = (f"{heading}\n\n{html.unescape(__import__('re').sub('<[^>]+>', '', intro))}\n"
            + (f"Requested from: {requested_from}\n" if requested_from else "")
            + f"\nOpen this on the device you want to use (works once, for {expiry}):\n{url}\n\n"
              "If you didn't expect this, ignore this email.")

    def _send():
        m = _mail()
        if only_if_matches:
            result = _send_if_owner_inbox(to, f"[Siraugga] {heading}", m._wrap(heading, inner), text, only_if_matches)
            if result.get("status") == "mismatch":
                return result
        else:
            result = m._send(to, f"[Siraugga] {heading}", m._wrap(heading, inner), text)
        if not result.get("ok"):                 # one retry: Gmail SMTP sometimes times out once
            result = (_send_if_owner_inbox(to, f"[Siraugga] {heading}", m._wrap(heading, inner), text, only_if_matches)
                      if only_if_matches else m._send(to, f"[Siraugga] {heading}", m._wrap(heading, inner), text))
        return result

    # Returns a future: the owner's invite awaits it to report failures; recovery doesn't wait.
    return asyncio.get_running_loop().run_in_executor(None, _send)


@device_keys_bp.route("/api/device-keys/recover", methods=["POST"])
async def recover():
    """New device, no password at hand. Without an email: an owner setup link goes to the
    DevCore inbox. With an email: if it belongs to someone the owner invited, a new link with
    their same role goes to that address. The reply never says whether an email went out, so
    addresses and limits can't be probed."""
    site, err = _site_or_fail()
    if err:
        return err
    data = await _json()
    ua = (request.headers.get("User-Agent") or "unknown device")[:160]
    email = str(data.get("email") or "").strip()
    if email:
        found = dk.create_person_recovery_invite(email)
        if found:
            code, name, addr = found
            _email_link(addr, kicker="New device", heading="Your new Siraugga setup link",
                        intro=f"Hi {__import__('html').escape(name)}, someone asked for a new Siraugga setup link for this email address. "
                              "If that was you, press the button on your new device.",
                        url=f"{_public_url()}/setup?invite={code}", expiry="30 minutes", requested_from=ua)
        else:
            # One of the owner's extra sign-in addresses: an owner setup link goes to it
            # (the reply is the same either way).
            from security import owner_emails
            code = None
            if owner_emails.is_extra_owner_email(email):
                try:
                    code = dk.create_recovery_invite()
                except ValueError:
                    code = None
            if code:
                _email_link(email.lower(), kicker="Owner access request", heading="Owner setup link (expires in 30 minutes)",
                            intro="Someone asked for a new Siraugga setup link for this owner email address. If that was you, "
                                  "press the button on the new device to make it Super Admin. You can also cancel it in Settings → Access keys.",
                            url=f"{_public_url()}/setup?invite={code}", expiry="30 minutes", requested_from=ua, warn_inbox=True)
            else:
                print("[DeviceKeys] person recovery: no email sent (unknown address or daily limit)")
        return jsonify({"success": True, "message": _PERSON_RECOVERY_REPLY}), 200, _NO_STORE
    try:
        code = dk.create_recovery_invite()
    except ValueError:
        print("[DeviceKeys] recovery email not sent: limit reached")
        return jsonify({"success": True, "message": _RECOVERY_REPLY}), 200, _NO_STORE
    _email_link("__admin__", kicker="Owner access request", heading="Owner setup link (expires in 30 minutes)",
                intro="Someone pressed <strong>Forgot your password?</strong> on the Siraugga setup page. If that was you, "
                      "press the button on the new device to make it Super Admin. You can also cancel it in Settings → Access keys.",
                url=f"{_public_url()}/setup?invite={code}", expiry="30 minutes", requested_from=ua, warn_inbox=True)
    return jsonify({"success": True, "message": _RECOVERY_REPLY}), 200, _NO_STORE


def _mail():
    from agents import ticket_mail
    return ticket_mail


def _send_if_owner_inbox(to, subject, html_body, text_body, typed_email) -> dict:
    """Send to the owner inbox only when `typed_email` is that inbox's address. The sender
    script does the comparison, so the address itself never comes back to this server."""
    import json as _j
    import subprocess
    import sys
    payload = _j.dumps({"to": to, "subject": subject, "html": html_body, "text": text_body,
                        "only_if_matches": typed_email})
    try:
        r = subprocess.run([sys.executable, _mail().SENDER_SCRIPT], input=payload, capture_output=True,
                           text=True, timeout=60)
        out = (r.stdout or "").strip().splitlines()
        return _j.loads(out[-1]) if out else {"ok": False, "message": (r.stderr or "No output")[-300:]}
    except Exception as e:
        return {"ok": False, "message": f"{e.__class__.__name__}: {e}"}


# ---- set up a device -----------------------------------------------------------------------
@device_keys_bp.route("/api/device-keys/setup/start", methods=["POST"])
async def setup_start():
    site, err = _site_or_fail()
    if err:
        return err
    data = await _json()
    invite = str(data.get("invite") or "").strip()
    password = str(data.get("password") or "")
    person = None
    if not invite and not password and not _is_owner():
        person = _session_person()
        if not person:
            return _fail("Sign in first (username, password and the emailed link), then add fingerprint or face.", 403)
    try:
        out = dk.registration_options(site[0], password=password, invite=invite,
                                      owner_ok=(not invite and not password and _is_owner()),
                                      username=str(data.get("username") or ""),
                                      new_password=str(data.get("new_password") or ""), person=person)
    except ValueError as e:
        return _fail(str(e))
    return jsonify({"success": True, **out}), 200, _NO_STORE


@device_keys_bp.route("/api/device-keys/setup/finish", methods=["POST"])
async def setup_finish():
    site, err = _site_or_fail()
    if err:
        return err
    data = await _json()
    try:
        rec = dk.finish_registration(str(data.get("setup_id") or ""), data.get("credential") or {},
                                     origin=site[1], label=(request.headers.get("User-Agent") or ""))
    except ValueError as e:
        return _fail(str(e))
    except Exception as e:  # webauthn verification errors
        print(f"[DeviceKeys] registration rejected: {e}")
        return _fail("The access key could not be verified. Try again.")
    return await _signed_in(rec)


# ---- sign in -------------------------------------------------------------------------------
@device_keys_bp.route("/api/device-keys/password-login", methods=["POST"])
async def password_login_removed():
    return _fail("Sign-in now also checks your email. Reload the page and sign in again.", 410)


# Username + password -> email address -> one-time link by email. Same for every account.
@device_keys_bp.route("/api/login/password", methods=["POST"])
async def login_password():
    site, err = _site_or_fail()
    if err:
        return err
    data = await _json()
    try:
        step = dk.start_login(str(data.get("username") or ""), str(data.get("password") or ""))
    except ValueError as e:
        msg = str(e)
        return _fail(msg, 429 if msg.startswith("Too many") else 401)
    return jsonify({"success": True, "step_id": step}), 200, _NO_STORE


@device_keys_bp.route("/api/login/email", methods=["POST"])
async def login_email():
    site, err = _site_or_fail()
    if err:
        return err
    data = await _json()
    step = str(data.get("step_id") or "")
    try:
        target = dk.login_email_target(step, str(data.get("email") or ""))
    except ValueError as e:
        return _fail(str(e))
    import html as _html
    try:
        code = dk.new_login_link(step)        # uses up the password step
    except ValueError as e:
        return _fail(str(e))
    url = f"{site[1]}/setup?signin={code}"
    ua = (request.headers.get("User-Agent") or "unknown device")[:160]
    sent = await _email_link(
        target["to"], kicker="Sign-in", heading="Your Siraugga sign-in link",
        intro=f"Hi {_html.escape(target['name'])}, your username and password were just entered correctly. "
              "Press the button to finish signing in.",
        url=url, expiry="15 minutes", requested_from=ua, button="Sign in to Siraugga",
        only_if_matches=(target["typed"] if target["to"] == "__admin__" else ""))
    if sent.get("status") == "mismatch":
        dk.cancel_login_link(code)
        return _fail("That email address doesn't match this account. Sign in again and use the right address.")
    if not sent.get("ok"):
        dk.cancel_login_link(code)
        return _fail("The email could not be sent right now. Try again in a minute.", 502)
    return jsonify({"success": True, "message": "Sign-in link sent. Open your email on this device and press "
                    "\"Sign in to Siraugga\". The link works once, for 15 minutes."}), 200, _NO_STORE


@device_keys_bp.route("/api/login/link", methods=["POST"])
async def login_link():
    site, err = _site_or_fail()
    if err:
        return err
    data = await _json()
    try:
        rec = dk.take_login_link(str(data.get("code") or "").strip())
    except ValueError as e:
        return _fail(str(e))
    return await _signed_in(rec)


@device_keys_bp.route("/api/device-keys/people/<username>", methods=["DELETE"])
async def keys_delete_person(username):
    denied = _owner_only()
    if denied:
        return denied
    return jsonify({"success": dk.delete_person(username)}), 200, _NO_STORE


@device_keys_bp.route("/api/device-keys/login/start", methods=["POST"])
async def login_start():
    site, err = _site_or_fail()
    if err:
        return err
    try:
        out = dk.authentication_options(site[0])
    except ValueError as e:
        return _fail(str(e), 429)
    return jsonify({"success": True, **out}), 200, _NO_STORE


@device_keys_bp.route("/api/device-keys/login/finish", methods=["POST"])
async def login_finish():
    site, err = _site_or_fail()
    if err:
        return err
    data = await _json()
    try:
        rec = dk.finish_authentication(str(data.get("login_id") or ""), data.get("credential") or {},
                                       origin=site[1])
    except ValueError as e:
        return _fail(str(e))
    except Exception as e:
        print(f"[DeviceKeys] sign-in rejected: {e}")
        return _fail("The access key could not be verified. Try again.")
    return await _signed_in(rec)


async def _signed_in(rec: dict):
    """Issue a session for the key's role. The owner also gets the trusted-device cookie, so
    owner-only parts of Siraugga (which check the device, not the session) work too."""
    sec = current_app.security_mgr
    if rec["role"] == dk.OWNER_ROLE:
        if not sec.check_master_signature():
            return _fail("This server can't confirm the owner (master key missing).", 403)
        res = sec.create_owner_session()
    else:
        is_admin = rec["role"] == "admin"
        sess_user = {"username": rec["name"], "name": rec["name"], "role": rec["role"],
                     "allowed_projects": ["*"] if is_admin else [],
                     "key_id": ("dkp-" + rec["username"]) if rec.get("username")
                               else "dk-" + rec["name"].lower().replace(" ", "-")[:40]}
        if rec.get("project"):
            # An in-game/app developer: only the project (and parts) they were handed.
            sess_user.update(allowed_projects=[rec["project"]], dev_project=rec["project"],
                             dev_parts=list(rec.get("parts") or []))
        res = sec.create_session(sess_user, kind="admin" if is_admin else "user")
    resp = await current_app.make_response((jsonify({"success": True, **res}), 200, _NO_STORE))
    if rec["role"] == dk.OWNER_ROLE and _site() and _site()[0] != "localhost":
        from security import owner_device
        secret = owner_device.claim(owner_device.new_handoff(), label=(request.headers.get("User-Agent") or "")[:120])
        if secret:
            resp.set_cookie(owner_device.COOKIE_NAME, secret, max_age=owner_device.DEVICE_TTL, path="/",
                            httponly=True, secure=True, samesite="Strict")
    return resp


# ---- owner management ----------------------------------------------------------------------
@device_keys_bp.route("/api/device-keys", methods=["GET"])
async def keys_overview():
    denied = _owner_only()
    if denied:
        return denied
    return jsonify({"success": True, "setup_url": _public_url() + "/setup", **dk.overview()}), 200, _NO_STORE


@device_keys_bp.route("/api/device-keys/password", methods=["POST"])
async def keys_set_password():
    denied = _owner_only()
    if denied:
        return denied
    data = await _json()
    try:
        dk.set_password(str(data.get("password") or ""))
    except ValueError as e:
        return _fail(str(e))
    return jsonify({"success": True}), 200, _NO_STORE


@device_keys_bp.route("/api/device-keys/invites", methods=["POST"])
async def keys_create_invite():
    denied = _owner_only()
    if denied:
        return denied
    data = await _json()
    name = str(data.get("name") or "")
    role = str(data.get("role") or "")
    try:
        email = dk.clean_email(str(data.get("email") or ""))
        code = dk.create_invite(name, role, email, project=str(data.get("project") or ""),
                                parts=data.get("parts") or [])
    except ValueError as e:
        return _fail(str(e))
    url = f"{_public_url()}/setup?invite={code}"
    email_error = ""
    if email:
        import html as _html
        sent = await _email_link(email, kicker="Invitation", heading="You're invited to Siraugga",
                    intro=f"Hi {_html.escape(name.strip())}, you've been given access to Siraugga as "
                          f"<strong>{_html.escape(dk.INVITE_ROLES.get(role, role))}</strong>. Press the button on the device "
                          "you want to use, then confirm with its fingerprint, face or PIN. Nothing to remember: that device "
                          "signs you in from then on. If you get a new device later, use \"Invited before? Email me a new link\" "
                          "on the setup page.",
                    url=url, expiry="3 days")
        if not sent.get("ok"):
            email_error = "The email could not be sent right now. Copy the link below and send it yourself."
    return jsonify({"success": True, "url": url, "emailed_to": email if email and not email_error else "",
                    "email_error": email_error, "expires_in_hours": dk.INVITE_TTL // 3600}), 200, _NO_STORE


@device_keys_bp.route("/api/device-keys/invites/<invite_id>", methods=["DELETE"])
async def keys_delete_invite(invite_id):
    denied = _owner_only()
    if denied:
        return denied
    return jsonify({"success": dk.delete_invite(invite_id)}), 200, _NO_STORE


@device_keys_bp.route("/api/device-keys/keys/<key_id>", methods=["DELETE"])
async def keys_delete(key_id):
    denied = _owner_only()
    if denied:
        return denied
    return jsonify({"success": dk.delete_key(key_id)}), 200, _NO_STORE
