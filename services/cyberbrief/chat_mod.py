"""Private chat: mikeytech.dev/chat.

A visitor needs a CHAT TOKEN, which the owner creates in the inbox (/chat/admin). With it they sign up
with an email and a password and confirm the email through a link. After confirming they also get a
personal login link that signs them in automatically. Then they chat one-to-one with the owner,
who reads and answers every thread at /chat/admin (admin only, same DevCore sign-in as /admin/notify).

Sessions: the login cookie is a browser-session cookie (gone when the browser closes) and the server
also locks it after one hour without activity. Activity = signing in, sending a message, or the page
reporting that the person is using it (background polling does not count).

The owner gets an email when a visitor connects (CHAT_NOTIFY_EMAILS in .env, comma separated).

Data lives in cache/chat.db (SQLite, git-ignored). Passwords are scrypt hashes; confirmation tokens,
chat tokens and personal-link keys are stored only as SHA-256 hashes.
"""
from __future__ import annotations

import hashlib
import hmac
import html
import re
import secrets
import sqlite3
import threading
import time
from pathlib import Path

from flask import Blueprint, Response, abort, jsonify, redirect, request, session

from .config import Config, _env

config = Config()
chat_bp = Blueprint("vchat", __name__)

DB_PATH = Path(config.ROOT_DIR) / "cache" / "chat.db"
PUBLIC_URL = (_env("CHAT_PUBLIC_URL") or "https://mikeytech.dev").rstrip("/")
NOTIFY = [e.strip() for e in (_env("CHAT_NOTIFY_EMAILS") or "").split(",") if e.strip()]
VERIFY_TTL = 48 * 3600
IDLE_SECONDS = 3600
NOTIFY_EVERY = 600
MAX_BODY = 4000
_db_lock = threading.Lock()
_hits: dict = {}
_notified: dict = {}
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
NO_TOKEN_MSG = "A chat token is required. If you do not have one, ask the dev to create one for you."


def _db() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH, timeout=10)
    con.row_factory = sqlite3.Row
    con.executescript("""
        CREATE TABLE IF NOT EXISTS users(
            id INTEGER PRIMARY KEY, email TEXT UNIQUE NOT NULL, pw TEXT NOT NULL,
            verified INTEGER NOT NULL DEFAULT 0, vtoken TEXT, vexp REAL, created REAL NOT NULL,
            invite TEXT, autokey TEXT);
        CREATE TABLE IF NOT EXISTS messages(
            id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, sender TEXT NOT NULL,
            body TEXT NOT NULL, ts REAL NOT NULL, seen INTEGER NOT NULL DEFAULT 0);
        CREATE INDEX IF NOT EXISTS msg_user ON messages(user_id, id);
        CREATE TABLE IF NOT EXISTS tokens(
            id INTEGER PRIMARY KEY, hash TEXT UNIQUE NOT NULL, label TEXT, created REAL NOT NULL,
            used_by INTEGER, used_at REAL, revoked INTEGER NOT NULL DEFAULT 0);
    """)
    cols = {r["name"] for r in con.execute("PRAGMA table_info(users)")}
    for col in ("invite", "autokey"):
        if col not in cols:
            con.execute(f"ALTER TABLE users ADD COLUMN {col} TEXT")
    return con


def _hash_pw(pw: str, salt: bytes | None = None) -> str:
    salt = salt or secrets.token_bytes(16)
    h = hashlib.scrypt(pw.encode(), salt=salt, n=2 ** 14, r=8, p=1, dklen=32)
    return salt.hex() + ":" + h.hex()


def _check_pw(pw: str, stored: str) -> bool:
    try:
        salt_hex, _ = stored.split(":")
        return hmac.compare_digest(_hash_pw(pw, bytes.fromhex(salt_hex)), stored)
    except Exception:
        return False


def _sha(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()


def _norm_token(t: str) -> str:
    return re.sub(r"[\s-]", "", str(t or "")).lower()


def _limited(key: str, limit: int, window: int) -> bool:
    now = time.time()
    hits = [t for t in _hits.get(key, []) if now - t < window]
    hits.append(now)
    _hits[key] = hits
    return len(hits) > limit


def _ip() -> str:
    return request.headers.get("CF-Connecting-Ip") or request.headers.get("X-Forwarded-For", "").split(",")[0].strip() or request.remote_addr or "?"


def _is_admin() -> bool:
    from .admin_gate import request_is_admin
    return request_is_admin(request)


def _json_only() -> bool:
    return request.is_json


def _user_id(touch: bool = False):
    """The signed-in visitor's id, or None. Locks the session after IDLE_SECONDS without activity."""
    uid = session.get("chat_uid")
    if not uid:
        return None
    now = time.time()
    if now - session.get("chat_seen", 0) > IDLE_SECONDS:
        session.pop("chat_uid", None)
        session.pop("chat_seen", None)
        return None
    if touch:
        session["chat_seen"] = now
    return uid


def _sign_in(uid: int) -> None:
    session.clear()
    session["chat_uid"] = uid
    session["chat_seen"] = time.time()
    session.permanent = False  # browser-session cookie: gone when the browser closes


def _mail(to: str, subject: str, body_html: str, text: str, link: str | None = None, label: str | None = None) -> None:
    from .email_engine import build_email_template, send_email
    send_email(to, subject, build_email_template(subject, body_html, link, label), text)


def _notify_owner(subject: str, line: str, uid: int | None = None, force: bool = False) -> None:
    """Email the owner in the background; at most one 'connected' email per person every 10 minutes."""
    if not NOTIFY:
        return
    if uid is not None and not force:
        if time.time() - _notified.get(uid, 0) < NOTIFY_EVERY:
            return
        _notified[uid] = time.time()

    def run():
        for to in NOTIFY:
            try:
                _mail(to, subject, f"<p>{html.escape(line)}</p><p>Inbox: {PUBLIC_URL.replace('https://mikeytech.dev', 'https://siraugga.mikeytech.dev')}/chat/admin</p>",
                      f"{line}\nInbox: https://siraugga.mikeytech.dev/chat/admin")
            except Exception:
                pass
    threading.Thread(target=run, daemon=True).start()


def _new_autolink(con, uid: int) -> str:
    key = secrets.token_urlsafe(32)
    con.execute("UPDATE users SET autokey=? WHERE id=?", (_sha(key), uid))
    return f"{PUBLIC_URL}/chat/go?k={key}"


def _page(body: str, status: int = 200) -> Response:
    return Response(
        "<!doctype html><html lang='en'><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>"
        "<meta name='robots' content='noindex'><title>Chat</title>"
        "<body style='font-family:system-ui;max-width:36rem;margin:12vh auto;padding:0 16px;line-height:1.5'>" + body + "</body></html>",
        status=status, mimetype="text/html", headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"})


# ----------------------------- visitor side -----------------------------

@chat_bp.get("/chat")
def chat_page():
    return Response(VISITOR_PAGE, mimetype="text/html", headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"})


@chat_bp.post("/chat/api/signup")
def signup():
    if not _json_only():
        abort(400)
    if _limited("su:" + _ip(), 8, 3600):
        return jsonify(ok=False, error="Too many tries. Try again later."), 429
    d = request.get_json(silent=True) or {}
    email = str(d.get("email", "")).strip().lower()
    pw = str(d.get("password", ""))
    tok = _norm_token(d.get("token", ""))
    if not EMAIL_RE.match(email) or len(email) > 254:
        return jsonify(ok=False, error="Enter a valid email address."), 400
    if len(pw) < 8 or len(pw) > 200:
        return jsonify(ok=False, error="The password must be at least 8 characters."), 400
    if not tok:
        return jsonify(ok=False, error=NO_TOKEN_MSG), 400
    vtoken = secrets.token_urlsafe(32)
    with _db_lock, _db() as con:
        t = con.execute("SELECT id FROM tokens WHERE hash=? AND used_by IS NULL AND revoked=0", (_sha(tok),)).fetchone()
        if not t:
            return jsonify(ok=False, error="That chat token is not valid or was already used. " + NO_TOKEN_MSG), 400
        row = con.execute("SELECT id, verified FROM users WHERE email=?", (email,)).fetchone()
        if row and row["verified"]:
            pass  # already registered: answer the same, send nothing
        else:
            if row:
                con.execute("UPDATE users SET pw=?, vtoken=?, vexp=?, invite=? WHERE id=?",
                            (_hash_pw(pw), _sha(vtoken), time.time() + VERIFY_TTL, _sha(tok), row["id"]))
            else:
                con.execute("INSERT INTO users(email,pw,verified,vtoken,vexp,created,invite) VALUES(?,?,0,?,?,?,?)",
                            (email, _hash_pw(pw), _sha(vtoken), time.time() + VERIFY_TTL, time.time(), _sha(tok)))
            link = f"{PUBLIC_URL}/chat/verify?token={vtoken}"
            _mail(email, "Confirm your email",
                  "<p>Thanks for signing up. Confirm your email address to start chatting.</p>"
                  "<p>This link works for 48 hours. If you did not sign up, ignore this email.</p>",
                  f"Confirm your email: {link}", link, "Confirm email")
    return jsonify(ok=True, message="Check your email and click the confirmation link, then sign in.")


@chat_bp.get("/chat/verify")
def verify():
    token = request.args.get("token", "")
    autolink = None
    email = None
    if token:
        with _db_lock, _db() as con:
            row = con.execute("SELECT id, email, vexp, invite FROM users WHERE vtoken=?", (_sha(token),)).fetchone()
            if row and row["vexp"] and row["vexp"] > time.time():
                claimed = con.execute("UPDATE tokens SET used_by=?, used_at=? WHERE hash=? AND used_by IS NULL AND revoked=0",
                                      (row["id"], time.time(), row["invite"])).rowcount
                if claimed:
                    con.execute("UPDATE users SET verified=1, vtoken=NULL, vexp=NULL WHERE id=?", (row["id"],))
                    autolink = _new_autolink(con, row["id"])
                    email = row["email"]
                    _sign_in(row["id"])
    if autolink:
        _notify_owner("Chat: new person connected", f"{email} confirmed their email and connected for the first time.", force=True)
        a = html.escape(autolink)
        return _page("<h1>Your email is confirmed</h1><p>You are signed in. This is your personal login link. "
                     "It signs you in automatically, so save it somewhere private and do not share it.</p>"
                     f"<p><input readonly value=\"{a}\" style='width:100%;font:inherit;padding:8px' aria-label='Personal login link' onfocus='this.select()'></p>"
                     "<p><a href='/chat'>Open the chat</a></p>")
    return _page("<h1>This link is invalid, expired or the chat token was already used.</h1><p><a href='/chat'>Go to chat</a></p>")


@chat_bp.get("/chat/go")
def auto_login():
    k = request.args.get("k", "")
    if _limited("go:" + _ip(), 30, 900):
        return _page("<h1>Too many tries. Try again later.</h1>", 429)
    if k:
        with _db_lock, _db() as con:
            row = con.execute("SELECT id, email FROM users WHERE autokey=? AND verified=1", (_sha(k),)).fetchone()
        if row:
            _sign_in(row["id"])
            _notify_owner("Chat: connected", f"{row['email']} connected with their personal login link.", row["id"])
            return redirect("/chat", code=302)
    return _page("<h1>This login link is not valid.</h1><p><a href='/chat'>Go to chat</a></p>", 403)


@chat_bp.post("/chat/api/login")
def login():
    if not _json_only():
        abort(400)
    if _limited("li:" + _ip(), 15, 900):
        return jsonify(ok=False, error="Too many tries. Try again later."), 429
    d = request.get_json(silent=True) or {}
    email = str(d.get("email", "")).strip().lower()
    pw = str(d.get("password", ""))
    with _db_lock, _db() as con:
        row = con.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
    ok = bool(row) and _check_pw(pw, row["pw"])
    if not ok:
        return jsonify(ok=False, error="Wrong email or password."), 401
    if not row["verified"]:
        return jsonify(ok=False, error="Confirm your email first. Check your inbox for the link."), 403
    _sign_in(row["id"])
    _notify_owner("Chat: connected", f"{row['email']} connected to the chat.", row["id"])
    return jsonify(ok=True, email=row["email"])


@chat_bp.post("/chat/api/logout")
def logout():
    session.clear()
    return jsonify(ok=True)


@chat_bp.post("/chat/api/ping")
def ping():
    """The page calls this when the person is actually using it, which keeps the session unlocked."""
    return (jsonify(ok=True) if _user_id(touch=True) else (jsonify(ok=False), 401))


@chat_bp.post("/chat/api/newlink")
def new_link():
    uid = _user_id(touch=True)
    if not uid:
        return jsonify(ok=False), 401
    with _db_lock, _db() as con:
        link = _new_autolink(con, uid)
    return jsonify(ok=True, link=link)


@chat_bp.get("/chat/api/me")
def me():
    uid = _user_id()
    if not uid:
        return jsonify(ok=False), 401
    with _db_lock, _db() as con:
        row = con.execute("SELECT email FROM users WHERE id=? AND verified=1", (uid,)).fetchone()
    return (jsonify(ok=True, email=row["email"]) if row else (jsonify(ok=False), 401))


@chat_bp.get("/chat/api/messages")
def messages():
    uid = _user_id()
    if not uid:
        return jsonify(ok=False), 401
    after = request.args.get("after", 0, type=int)
    with _db_lock, _db() as con:
        rows = con.execute("SELECT id, sender, body, ts FROM messages WHERE user_id=? AND id>? ORDER BY id LIMIT 200",
                           (uid, after)).fetchall()
    return jsonify(ok=True, messages=[dict(r) for r in rows])


@chat_bp.post("/chat/api/send")
def send():
    uid = _user_id(touch=True)
    if not uid:
        return jsonify(ok=False), 401
    if not _json_only():
        abort(400)
    if _limited("sd:%s" % uid, 60, 60):
        return jsonify(ok=False, error="Slow down a little."), 429
    body = str((request.get_json(silent=True) or {}).get("body", "")).strip()[:MAX_BODY]
    if not body:
        return jsonify(ok=False, error="Empty message."), 400
    with _db_lock, _db() as con:
        cur = con.execute("INSERT INTO messages(user_id,sender,body,ts) VALUES(?,?,?,?)", (uid, "user", body, time.time()))
    return jsonify(ok=True, id=cur.lastrowid)


# ------------------------------ owner side ------------------------------

def _need_admin():
    if not _is_admin():
        abort(404)


@chat_bp.get("/chat/admin")
def admin_page():
    _need_admin()
    return Response(ADMIN_PAGE, mimetype="text/html", headers={"Cache-Control": "no-store"})


@chat_bp.get("/chat/admin/api/threads")
def admin_threads():
    _need_admin()
    with _db_lock, _db() as con:
        rows = con.execute("""
            SELECT u.id, u.email, u.verified,
                   (SELECT body FROM messages m WHERE m.user_id=u.id ORDER BY id DESC LIMIT 1) AS last_body,
                   (SELECT ts FROM messages m WHERE m.user_id=u.id ORDER BY id DESC LIMIT 1) AS last_ts,
                   (SELECT COUNT(*) FROM messages m WHERE m.user_id=u.id AND m.sender='user' AND m.seen=0) AS unread
            FROM users u ORDER BY COALESCE(last_ts, u.created) DESC""").fetchall()
    return jsonify(ok=True, threads=[dict(r) for r in rows])


@chat_bp.get("/chat/admin/api/messages")
def admin_messages():
    _need_admin()
    uid = request.args.get("user", 0, type=int)
    after = request.args.get("after", 0, type=int)
    with _db_lock, _db() as con:
        rows = con.execute("SELECT id, sender, body, ts FROM messages WHERE user_id=? AND id>? ORDER BY id LIMIT 200",
                           (uid, after)).fetchall()
        con.execute("UPDATE messages SET seen=1 WHERE user_id=? AND sender='user'", (uid,))
    return jsonify(ok=True, messages=[dict(r) for r in rows])


@chat_bp.post("/chat/admin/api/send")
def admin_send():
    _need_admin()
    if not _json_only():
        abort(400)
    d = request.get_json(silent=True) or {}
    uid = int(d.get("user") or 0)
    body = str(d.get("body", "")).strip()[:MAX_BODY]
    if not uid or not body:
        return jsonify(ok=False, error="Pick a person and write a message."), 400
    with _db_lock, _db() as con:
        if not con.execute("SELECT 1 FROM users WHERE id=?", (uid,)).fetchone():
            return jsonify(ok=False, error="Unknown person."), 404
        cur = con.execute("INSERT INTO messages(user_id,sender,body,ts) VALUES(?,?,?,?)", (uid, "owner", body, time.time()))
    return jsonify(ok=True, id=cur.lastrowid)


@chat_bp.post("/chat/admin/api/tokens")
def admin_token_create():
    """Create a single-use chat token. The token is shown once and stored only as a hash."""
    _need_admin()
    if not _json_only():
        abort(400)
    label = str((request.get_json(silent=True) or {}).get("label", "")).strip()[:80]
    raw = secrets.token_hex(8)
    shown = "-".join(raw[i:i + 4] for i in range(0, 16, 4))
    with _db_lock, _db() as con:
        con.execute("INSERT INTO tokens(hash,label,created) VALUES(?,?,?)", (_sha(raw), label, time.time()))
    return jsonify(ok=True, token=shown)


@chat_bp.get("/chat/admin/api/tokens")
def admin_token_list():
    _need_admin()
    with _db_lock, _db() as con:
        rows = con.execute("""SELECT t.id, t.label, t.created, t.revoked, t.used_at, u.email AS used_by
                              FROM tokens t LEFT JOIN users u ON u.id=t.used_by ORDER BY t.id DESC LIMIT 100""").fetchall()
    return jsonify(ok=True, tokens=[dict(r) for r in rows])


@chat_bp.delete("/chat/admin/api/tokens/<int:tid>")
def admin_token_revoke(tid: int):
    _need_admin()
    with _db_lock, _db() as con:
        con.execute("UPDATE tokens SET revoked=1 WHERE id=? AND used_by IS NULL", (tid,))
    return jsonify(ok=True)


# -------------------------------- pages --------------------------------

_STYLE = """<style>
:root{--bg:#f7f8fa;--fg:#14181f;--muted:#4a5568;--card:#fff;--line:#d5dae3;--accent:#0b6bcb;--afg:#fff;--mine:#dbeafe;--theirs:#eef0f4}
@media (prefers-color-scheme:dark){:root{--bg:#0e1116;--fg:#e8ecf2;--muted:#a3adbd;--card:#171b22;--line:#2b323d;--accent:#4da3ff;--afg:#06121f;--mine:#1b3a5f;--theirs:#232a35}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:16px/1.5 system-ui,sans-serif}
main{max-width:42rem;margin:0 auto;padding:24px 16px 48px}h1{font-size:1.5rem;margin:0 0 12px}
label{display:block;margin:12px 0 4px;font-weight:600}
input,textarea,select{width:100%;font:inherit;color:var(--fg);background:var(--card);border:1px solid var(--line);border-radius:10px;padding:10px}
button{font:inherit;font-weight:600;background:var(--accent);color:var(--afg);border:0;border-radius:10px;padding:10px 16px;margin:12px 8px 0 0;cursor:pointer}
button.alt{background:var(--card);color:var(--fg);border:1px solid var(--line)}
:focus-visible{outline:3px solid var(--fg);outline-offset:2px}
.note{color:var(--muted)}.err{color:#c0392b;font-weight:600}
#log{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:12px;height:55vh;overflow:auto}
.m{margin:8px 0;padding:8px 12px;border-radius:12px;max-width:85%;white-space:pre-wrap;word-break:break-word}
.m.me{background:var(--mine);margin-left:auto}.m.them{background:var(--theirs)}
.who{font-size:.8rem;color:var(--muted);display:block}
details{margin-top:20px}summary{cursor:pointer;font-weight:600}
[hidden]{display:none!important}
</style>"""

VISITOR_PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><meta name="robots" content="noindex">
<title>Private chat</title>""" + _STYLE + """</head><body><main>
<h1>Private chat</h1>
<section id="auth" hidden>
  <p class="note" id="lockmsg"></p>
  <div id="known" hidden>
    <p>Welcome back, <strong id="kemail"></strong>.</p>
    <label for="pw">Password</label><input id="pw" type="password" autocomplete="current-password">
    <div><button id="in">Sign in</button><button id="other" class="alt">Use a different email</button></div>
  </div>
  <div id="fresh" hidden>
    <label for="em">Email</label><input id="em" type="email" autocomplete="email">
    <label for="pw2">Password</label><input id="pw2" type="password" autocomplete="current-password">
    <div><button id="in2">Sign in</button></div>
  </div>
  <details id="signup">
    <summary>New here? Create an account</summary>
    <p class="note">A chat token is required. If you do not have one, ask the dev to create one for you.</p>
    <label for="stok">Chat token</label><input id="stok" autocomplete="off" autocapitalize="off" spellcheck="false">
    <label for="sem">Email</label><input id="sem" type="email" autocomplete="email">
    <label for="spw">Password (at least 8 characters)</label><input id="spw" type="password" autocomplete="new-password">
    <button id="up">Create account</button>
    <p class="note">We email you a link to confirm your address. You only confirm once.</p>
  </details>
  <p id="msg" role="status" aria-live="polite"></p>
</section>
<section id="room" hidden>
  <p class="note" id="who"></p>
  <div id="log" role="log" aria-live="polite" aria-label="Messages" tabindex="0"></div>
  <label for="body">Message</label><textarea id="body" rows="3"></textarea>
  <button id="send">Send</button><button id="link" class="alt">New personal login link</button><button id="out" class="alt">Sign out</button>
  <p id="linkout" class="note" role="status" aria-live="polite"></p>
</section>
<script>
const $=id=>document.getElementById(id);let last=0,timer=null,lastPing=0;
const store={get:k=>{try{return localStorage.getItem(k)}catch(e){return null}},set:(k,v)=>{try{localStorage.setItem(k,v)}catch(e){}},del:k=>{try{localStorage.removeItem(k)}catch(e){}}};
const post=(u,d)=>fetch(u,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(d||{})}).then(async r=>({s:r.status,j:await r.json().catch(()=>({}))}));
function say(t,e){$('msg').textContent=t;$('msg').className=e?'err':'note'}
function add(m){const d=document.createElement('div');d.className='m '+(m.sender==='user'?'me':'them');
 const w=document.createElement('span');w.className='who';w.textContent=(m.sender==='user'?'You':'Owner')+' \\u00b7 '+new Date(m.ts*1000).toLocaleString();
 const b=document.createElement('div');b.textContent=m.body;d.append(w,b);$('log').append(d);$('log').scrollTop=$('log').scrollHeight}
async function poll(){const r=await fetch('/chat/api/messages?after='+last);if(r.status===401){show(false,null,true);return}
 const j=await r.json();j.messages.forEach(m=>{add(m);last=m.id})}
function known(){const e=store.get('chat_email');$('known').hidden=!e;$('fresh').hidden=!!e;if(e)$('kemail').textContent=e;(e?$('pw'):$('em')).focus()}
function show(inRoom,email,locked){$('auth').hidden=inRoom;$('room').hidden=!inRoom;clearInterval(timer);
 if(inRoom){$('who').textContent='Signed in as '+email;store.set('chat_email',email);$('log').textContent='';last=0;poll();timer=setInterval(poll,3000);$('body').focus()}
 else{$('lockmsg').textContent=locked?'Locked after a period without activity. Enter your password to continue.':'Sign in with your password.';known()}}
async function doLogin(email,pw){const r=await post('/chat/api/login',{email:email,password:pw});
 if(r.j.ok){$('pw').value='';$('pw2').value='';show(true,r.j.email)}else say(r.j.error||'Could not sign in.',true)}
$('in').onclick=()=>doLogin(store.get('chat_email'),$('pw').value);
$('in2').onclick=()=>doLogin($('em').value,$('pw2').value);
$('other').onclick=()=>{store.del('chat_email');known()};
$('up').onclick=async()=>{const r=await post('/chat/api/signup',{token:$('stok').value,email:$('sem').value,password:$('spw').value});
 if(r.j.ok)store.set('chat_email',$('sem').value.trim().toLowerCase());say(r.j.ok?r.j.message:(r.j.error||'Could not sign up.'),!r.j.ok)};
$('send').onclick=async()=>{const t=$('body').value.trim();if(!t)return;$('body').value='';
 const r=await post('/chat/api/send',{body:t});if(!r.j.ok){if(r.s===401)show(false,null,true);else say(r.j.error||'Not sent.',true)}poll()};
$('link').onclick=async()=>{const r=await post('/chat/api/newlink');$('linkout').textContent=r.j.ok?'Your new personal login link (the old one stops working): '+r.j.link:'Could not make a link.'};
$('body').addEventListener('keydown',e=>{if(e.key==='Enter'&&(e.ctrlKey||e.metaKey)){e.preventDefault();$('send').click()}});
$('out').onclick=async()=>{await post('/chat/api/logout');show(false)};
['keydown','click','touchstart'].forEach(ev=>document.addEventListener(ev,()=>{const n=Date.now();if(!$('room').hidden&&n-lastPing>60000){lastPing=n;post('/chat/api/ping')}},{passive:true}));
fetch('/chat/api/me').then(r=>r.json()).then(j=>show(!!j.ok,j.email,false)).catch(()=>show(false));
</script></main></body></html>"""

ADMIN_PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><meta name="robots" content="noindex">
<title>Chat inbox</title>""" + _STYLE + """</head><body><main>
<h1>Chat inbox</h1>
<label for="pick">Conversation</label><select id="pick"></select>
<div id="log" role="log" aria-live="polite" aria-label="Messages" tabindex="0" style="margin-top:12px"></div>
<label for="body">Reply</label><textarea id="body" rows="3"></textarea>
<button id="send">Send</button>
<details open><summary>Chat tokens</summary>
  <p class="note">A person needs a token to create an account. Each token works once.</p>
  <label for="tl">Who is it for? (optional note)</label><input id="tl">
  <button id="mk">Create chat token</button>
  <p id="newtok" role="status" aria-live="polite" style="font-weight:700;font-size:1.2rem"></p>
  <ul id="toks"></ul>
</details>
<script>
const $=id=>document.getElementById(id);let cur=0,last=0;
const api=(u,o)=>fetch(u,o).then(r=>r.json());
const jpost=(u,d)=>api(u,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(d||{})});
function add(m){const d=document.createElement('div');d.className='m '+(m.sender==='owner'?'me':'them');
 const w=document.createElement('span');w.className='who';w.textContent=(m.sender==='owner'?'You':'Visitor')+' \\u00b7 '+new Date(m.ts*1000).toLocaleString();
 const b=document.createElement('div');b.textContent=m.body;d.append(w,b);$('log').append(d);$('log').scrollTop=$('log').scrollHeight}
async function threads(){const j=await api('/chat/admin/api/threads');const keep=$('pick').value;$('pick').textContent='';
 j.threads.forEach(t=>{const o=document.createElement('option');o.value=t.id;
  o.textContent=t.email+(t.verified?'':' (not confirmed)')+(t.unread?' ['+t.unread+' new]':'');$('pick').append(o)});
 if(keep)$('pick').value=keep;if(!cur&&j.threads.length){cur=+$('pick').value;load()}}
async function poll(){if(!cur)return;const j=await api('/chat/admin/api/messages?user='+cur+'&after='+last);j.messages.forEach(m=>{add(m);last=m.id})}
function load(){$('log').textContent='';last=0;poll()}
async function toks(){const j=await api('/chat/admin/api/tokens');$('toks').textContent='';
 j.tokens.forEach(t=>{const li=document.createElement('li');
  const st=t.revoked?'revoked':(t.used_by?'used by '+t.used_by:'unused');
  li.textContent=(t.label||'(no note)')+' \\u2014 '+st+' ';
  if(!t.revoked&&!t.used_by){const b=document.createElement('button');b.className='alt';b.textContent='Revoke';
   b.onclick=async()=>{await api('/chat/admin/api/tokens/'+t.id,{method:'DELETE'});toks()};li.append(b)}
  $('toks').append(li)})}
$('mk').onclick=async()=>{const j=await jpost('/chat/admin/api/tokens',{label:$('tl').value});
 $('newtok').textContent=j.ok?'Chat token (shown once): '+j.token:'Could not create a token.';$('tl').value='';toks()};
$('pick').onchange=()=>{cur=+$('pick').value;load()};
$('send').onclick=async()=>{const t=$('body').value.trim();if(!t||!cur)return;$('body').value='';
 await jpost('/chat/admin/api/send',{user:cur,body:t});poll()};
$('body').addEventListener('keydown',e=>{if(e.key==='Enter'&&(e.ctrlKey||e.metaKey)){e.preventDefault();$('send').click()}});
threads();toks();setInterval(()=>{poll();threads()},4000);
</script></main></body></html>"""
