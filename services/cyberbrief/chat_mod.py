"""Visitor chat: mikeytech.dev/chat.

A visitor signs up with an email and a password, confirms the email through a link, and then
chats one-to-one with the owner. The owner reads and answers every thread at /chat/admin
(admin only, same DevCore sign-in as /admin/notify). Plain polling, no extras.

Data lives in cache/chat.db (SQLite, git-ignored). Passwords are stored as scrypt hashes and
confirmation tokens as SHA-256 hashes, never in plain text.
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
VERIFY_TTL = 48 * 3600
MAX_BODY = 4000
_db_lock = threading.Lock()
_hits: dict = {}
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _db() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH, timeout=10)
    con.row_factory = sqlite3.Row
    con.executescript("""
        CREATE TABLE IF NOT EXISTS users(
            id INTEGER PRIMARY KEY, email TEXT UNIQUE NOT NULL, pw TEXT NOT NULL,
            verified INTEGER NOT NULL DEFAULT 0, vtoken TEXT, vexp REAL, created REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS messages(
            id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, sender TEXT NOT NULL,
            body TEXT NOT NULL, ts REAL NOT NULL, seen INTEGER NOT NULL DEFAULT 0);
        CREATE INDEX IF NOT EXISTS msg_user ON messages(user_id, id);
    """)
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


def _limited(key: str, limit: int, window: int) -> bool:
    now = time.time()
    hits = [t for t in _hits.get(key, []) if now - t < window]
    hits.append(now)
    _hits[key] = hits
    return len(hits) > limit


def _ip() -> str:
    return request.headers.get("CF-Connecting-IP") or request.headers.get("X-Forwarded-For", "").split(",")[0].strip() or request.remote_addr or "?"


def _is_admin() -> bool:
    from .admin_gate import request_is_admin
    return request_is_admin(request)


def _json_only() -> bool:
    return request.is_json


def _user_id():
    return session.get("chat_uid")


def _send_confirmation(email: str, token: str) -> None:
    from .email_engine import build_email_template, send_email
    link = f"{PUBLIC_URL}/chat/verify?token={token}"
    body = ("<p>Thanks for signing up. Confirm your email address to start chatting.</p>"
            "<p>This link works for 48 hours. If you did not sign up, ignore this email.</p>")
    send_email(email, "Confirm your email", build_email_template("Confirm your email", body, link, "Confirm email"),
               f"Confirm your email: {link}")


# ----------------------------- visitor side -----------------------------

@chat_bp.get("/chat")
def chat_page():
    return Response(VISITOR_PAGE, mimetype="text/html", headers={"Cache-Control": "no-store"})


@chat_bp.post("/chat/api/signup")
def signup():
    if not _json_only():
        abort(400)
    if _limited("su:" + _ip(), 8, 3600):
        return jsonify(ok=False, error="Too many tries. Try again later."), 429
    d = request.get_json(silent=True) or {}
    email = str(d.get("email", "")).strip().lower()
    pw = str(d.get("password", ""))
    if not EMAIL_RE.match(email) or len(email) > 254:
        return jsonify(ok=False, error="Enter a valid email address."), 400
    if len(pw) < 8 or len(pw) > 200:
        return jsonify(ok=False, error="The password must be at least 8 characters."), 400
    token = secrets.token_urlsafe(32)
    with _db_lock, _db() as con:
        row = con.execute("SELECT id, verified FROM users WHERE email=?", (email,)).fetchone()
        if row and row["verified"]:
            pass  # already registered: answer the same, send nothing
        elif row:
            con.execute("UPDATE users SET pw=?, vtoken=?, vexp=? WHERE id=?",
                        (_hash_pw(pw), _sha(token), time.time() + VERIFY_TTL, row["id"]))
            _send_confirmation(email, token)
        else:
            con.execute("INSERT INTO users(email,pw,verified,vtoken,vexp,created) VALUES(?,?,0,?,?,?)",
                        (email, _hash_pw(pw), _sha(token), time.time() + VERIFY_TTL, time.time()))
            _send_confirmation(email, token)
    return jsonify(ok=True, message="Check your email and click the confirmation link, then sign in.")


@chat_bp.get("/chat/verify")
def verify():
    token = request.args.get("token", "")
    done = False
    if token:
        with _db_lock, _db() as con:
            row = con.execute("SELECT id, vexp FROM users WHERE vtoken=?", (_sha(token),)).fetchone()
            if row and row["vexp"] and row["vexp"] > time.time():
                con.execute("UPDATE users SET verified=1, vtoken=NULL, vexp=NULL WHERE id=?", (row["id"],))
                done = True
    msg = "Your email is confirmed. You can sign in now." if done else "This link is invalid or has expired. Sign up again to get a new one."
    return Response(
        f"<!doctype html><html lang='en'><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>"
        f"<title>Email confirmation</title><body style='font-family:system-ui;max-width:34rem;margin:15vh auto;padding:0 16px'>"
        f"<h1>{html.escape(msg)}</h1><p><a href='/chat'>Go to chat</a></p></body></html>", mimetype="text/html")


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
    session.clear()
    session["chat_uid"] = row["id"]
    session.permanent = True
    return jsonify(ok=True, email=row["email"])


@chat_bp.post("/chat/api/logout")
def logout():
    session.pop("chat_uid", None)
    return jsonify(ok=True)


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
    uid = _user_id()
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


# -------------------------------- pages --------------------------------

_STYLE = """<style>
:root{--bg:#f7f8fa;--fg:#14181f;--muted:#4a5568;--card:#fff;--line:#d5dae3;--accent:#0b6bcb;--afg:#fff;--mine:#dbeafe;--theirs:#eef0f4}
@media (prefers-color-scheme:dark){:root{--bg:#0e1116;--fg:#e8ecf2;--muted:#a3adbd;--card:#171b22;--line:#2b323d;--accent:#4da3ff;--afg:#06121f;--mine:#1b3a5f;--theirs:#232a35}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:16px/1.5 system-ui,sans-serif}
main{max-width:42rem;margin:0 auto;padding:24px 16px 48px}h1{font-size:1.5rem;margin:0 0 12px}
label{display:block;margin:12px 0 4px;font-weight:600}
input,textarea{width:100%;font:inherit;color:var(--fg);background:var(--card);border:1px solid var(--line);border-radius:10px;padding:10px}
button{font:inherit;font-weight:600;background:var(--accent);color:var(--afg);border:0;border-radius:10px;padding:10px 16px;margin:12px 8px 0 0;cursor:pointer}
button.alt{background:var(--card);color:var(--fg);border:1px solid var(--line)}
:focus-visible{outline:3px solid var(--fg);outline-offset:2px}
.note{color:var(--muted)}.err{color:#c0392b;font-weight:600}
#log{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:12px;height:55vh;overflow:auto}
.m{margin:8px 0;padding:8px 12px;border-radius:12px;max-width:85%;white-space:pre-wrap;word-break:break-word}
.m.me{background:var(--mine);margin-left:auto}.m.them{background:var(--theirs)}
.who{font-size:.8rem;color:var(--muted);display:block}
[hidden]{display:none!important}
</style>"""

VISITOR_PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><meta name="robots" content="noindex">
<title>Chat</title>""" + _STYLE + """</head><body><main>
<h1>Chat</h1>
<section id="auth" hidden>
  <p class="note">Sign in, or create an account with your email and a password. We will email you a link to confirm it.</p>
  <label for="em">Email</label><input id="em" type="email" autocomplete="email">
  <label for="pw">Password (at least 8 characters)</label><input id="pw" type="password" autocomplete="current-password">
  <div><button id="in">Sign in</button><button id="up" class="alt">Create account</button></div>
  <p id="msg" role="status" aria-live="polite"></p>
</section>
<section id="room" hidden>
  <p class="note" id="who"></p>
  <div id="log" role="log" aria-live="polite" aria-label="Messages" tabindex="0"></div>
  <label for="body">Message</label><textarea id="body" rows="3"></textarea>
  <button id="send">Send</button><button id="out" class="alt">Sign out</button>
</section>
<script>
const $=id=>document.getElementById(id);let last=0,timer=null;
const post=(u,d)=>fetch(u,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(d||{})}).then(async r=>({s:r.status,j:await r.json().catch(()=>({}))}));
function say(t,e){$('msg').textContent=t;$('msg').className=e?'err':'note'}
function add(m){const d=document.createElement('div');d.className='m '+(m.sender==='user'?'me':'them');
 const w=document.createElement('span');w.className='who';w.textContent=(m.sender==='user'?'You':'Owner')+' · '+new Date(m.ts*1000).toLocaleString();
 const b=document.createElement('div');b.textContent=m.body;d.append(w,b);$('log').append(d);$('log').scrollTop=$('log').scrollHeight}
async function poll(){const r=await fetch('/chat/api/messages?after='+last);if(r.status===401){show(false);return}
 const j=await r.json();j.messages.forEach(m=>{add(m);last=m.id})}
function show(inRoom,email){$('auth').hidden=inRoom;$('room').hidden=!inRoom;clearInterval(timer);
 if(inRoom){$('who').textContent='Signed in as '+email;$('log').textContent='';last=0;poll();timer=setInterval(poll,3000);$('body').focus()}else{$('em').focus()}}
$('in').onclick=async()=>{const r=await post('/chat/api/login',{email:$('em').value,password:$('pw').value});
 if(r.j.ok){$('pw').value='';show(true,r.j.email)}else say(r.j.error||'Could not sign in.',true)};
$('up').onclick=async()=>{const r=await post('/chat/api/signup',{email:$('em').value,password:$('pw').value});
 say(r.j.ok?r.j.message:(r.j.error||'Could not sign up.'),!r.j.ok)};
$('send').onclick=async()=>{const t=$('body').value.trim();if(!t)return;$('body').value='';
 const r=await post('/chat/api/send',{body:t});if(!r.j.ok)say(r.j.error||'Not sent.',true);poll()};
$('body').addEventListener('keydown',e=>{if(e.key==='Enter'&&(e.ctrlKey||e.metaKey)){e.preventDefault();$('send').click()}});
$('out').onclick=async()=>{await post('/chat/api/logout');show(false)};
fetch('/chat/api/me').then(r=>r.json()).then(j=>show(!!j.ok,j.email)).catch(()=>show(false));
</script></main></body></html>"""

ADMIN_PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><meta name="robots" content="noindex">
<title>Chat inbox</title>""" + _STYLE + """</head><body><main>
<h1>Chat inbox</h1>
<label for="pick">Conversation</label><select id="pick" style="width:100%;font:inherit;padding:10px;border-radius:10px"></select>
<div id="log" role="log" aria-live="polite" aria-label="Messages" tabindex="0" style="margin-top:12px"></div>
<label for="body">Reply</label><textarea id="body" rows="3"></textarea>
<button id="send">Send</button>
<script>
const $=id=>document.getElementById(id);let cur=0,last=0;
const api=(u,o)=>fetch(u,o).then(r=>r.json());
function add(m){const d=document.createElement('div');d.className='m '+(m.sender==='owner'?'me':'them');
 const w=document.createElement('span');w.className='who';w.textContent=(m.sender==='owner'?'You':'Visitor')+' · '+new Date(m.ts*1000).toLocaleString();
 const b=document.createElement('div');b.textContent=m.body;d.append(w,b);$('log').append(d);$('log').scrollTop=$('log').scrollHeight}
async function threads(){const j=await api('/chat/admin/api/threads');const keep=$('pick').value;$('pick').textContent='';
 j.threads.forEach(t=>{const o=document.createElement('option');o.value=t.id;
  o.textContent=t.email+(t.verified?'':' (not confirmed)')+(t.unread?' ['+t.unread+' new]':'');$('pick').append(o)});
 if(keep)$('pick').value=keep;if(!cur&&j.threads.length){cur=+$('pick').value;load()}}
async function poll(){if(!cur)return;const j=await api('/chat/admin/api/messages?user='+cur+'&after='+last);j.messages.forEach(m=>{add(m);last=m.id})}
function load(){$('log').textContent='';last=0;poll()}
$('pick').onchange=()=>{cur=+$('pick').value;load()};
$('send').onclick=async()=>{const t=$('body').value.trim();if(!t||!cur)return;$('body').value='';
 await api('/chat/admin/api/send',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({user:cur,body:t})});poll()};
$('body').addEventListener('keydown',e=>{if(e.key==='Enter'&&(e.ctrlKey||e.metaKey)){e.preventDefault();$('send').click()}});
threads();setInterval(()=>{poll();threads()},4000);
</script></main></body></html>"""
