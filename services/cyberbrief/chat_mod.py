"""Private chat: mikeytech.dev/chat.

Invite-only. The owner invites a person by email in the inbox (/chat/admin). The person gets an email
with a private link. Clicking it verifies them and signs them in. There is no public sign-up and no
password: the link is the key, so the email tells them to keep it safe. Then they chat one-to-one
with the owner, who reads and answers every thread at /chat/admin (admin only, same DevCore sign-in
as /admin/notify).

Rotating a link = the owner sends that person a new link (the old one stops working immediately).

Sessions: the login cookie is a browser-session cookie (gone when the browser closes) and the server
also locks it after one hour without activity (typing, clicking, sending; background polling does not
count). A locked person just clicks their private link again.

The owner gets an email when a person connects (CHAT_NOTIFY_EMAILS in .env, comma separated).
Data lives in cache/chat.db (SQLite, git-ignored); links are stored only as SHA-256 hashes.
"""
from __future__ import annotations

import hashlib
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
INBOX_URL = (_env("CHAT_INBOX_URL") or "https://siraugga.mikeytech.dev").rstrip("/") + "/chat/admin"
NOTIFY = [e.strip() for e in (_env("CHAT_NOTIFY_EMAILS") or "").split(",") if e.strip()]
IDLE_SECONDS = 3600
NOTIFY_EVERY = 600
MAX_BODY = 4000
_db_lock = threading.Lock()
_hits: dict = {}
_notified: dict = {}
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _db() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH, timeout=10)
    con.row_factory = sqlite3.Row
    con.executescript("""
        CREATE TABLE IF NOT EXISTS users(
            id INTEGER PRIMARY KEY, email TEXT UNIQUE NOT NULL, pw TEXT NOT NULL DEFAULT '!',
            verified INTEGER NOT NULL DEFAULT 0, vtoken TEXT, vexp REAL, created REAL NOT NULL,
            invite TEXT, autokey TEXT);
        CREATE TABLE IF NOT EXISTS messages(
            id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, sender TEXT NOT NULL,
            body TEXT NOT NULL, ts REAL NOT NULL, seen INTEGER NOT NULL DEFAULT 0);
        CREATE INDEX IF NOT EXISTS msg_user ON messages(user_id, id);
    """)
    cols = {r["name"] for r in con.execute("PRAGMA table_info(users)")}
    for col in ("invite", "autokey"):
        if col not in cols:
            con.execute(f"ALTER TABLE users ADD COLUMN {col} TEXT")
    return con


def _sha(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()


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
    """The signed-in person's id, or None. Locks the session after IDLE_SECONDS without activity."""
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


def _notify_owner(subject: str, line: str, uid: int | None = None, force: bool = False) -> None:
    """Email the owner in the background; at most one 'connected' email per person every 10 minutes."""
    if not NOTIFY:
        return
    if uid is not None and not force:
        if time.time() - _notified.get(uid, 0) < NOTIFY_EVERY:
            return
        _notified[uid] = time.time()

    def run():
        from .email_engine import build_email_template, send_email
        for to in NOTIFY:
            try:
                send_email(to, subject,
                           build_email_template(subject, f"<p>{html.escape(line)}</p>", INBOX_URL, "Open the chat inbox"),
                           f"{line}\nInbox: {INBOX_URL}")
            except Exception:
                pass
    threading.Thread(target=run, daemon=True).start()


def _invite_email(email: str, link: str) -> None:
    from .email_engine import build_email_template, send_email
    body = (
        "<p>Here is your link to a <strong>private communication channel</strong>. "
        "It is a one-to-one chat between you and the person who invited you.</p>"
        "<p><strong>Your private link is below. Please keep it safe.</strong></p>"
        "<ul>"
        "<li>This link is your key. Anyone who has it can enter the chat as you.</li>"
        "<li>Do not share it, forward this email or post the link anywhere.</li>"
        "<li>Clicking it for the first time confirms your email address and signs you in.</li>"
        "<li>The chat locks when you close your browser or after an hour without activity. "
        "To get back in, click the same link again.</li>"
        "<li>If you lose it or think someone else has seen it, tell the person who invited you "
        "and they will send you a new one. The old link stops working.</li>"
        "</ul>"
        "<p>If you were not expecting this invitation, ignore this email. Nothing happens unless the link is opened.</p>")
    text = ("You have been invited to a private communication channel: a one-to-one chat between you and the person who invited you.\n\n"
            f"Your private link (keep it safe, it is your key; anyone with it can enter as you; do not share or forward it):\n{link}\n\n"
            "Opening it the first time confirms your email and signs you in. The chat locks when you close the browser or after an hour "
            "without activity; click the same link again to get back in. If you lose it or think someone saw it, ask for a new one "
            "and the old one stops working.\n\nIf you were not expecting this, ignore this email.")
    send_email(email, "Your private chat link: keep it safe",
               build_email_template("Your private chat link", body, link, "Open the private chat"), text)


def _page(body: str, status: int = 200) -> Response:
    return Response(
        "<!doctype html><html lang='en'><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>"
        "<meta name='robots' content='noindex'><title>Private chat</title>"
        "<body style='font-family:system-ui;max-width:36rem;margin:12vh auto;padding:0 16px;line-height:1.5'>" + body + "</body></html>",
        status=status, mimetype="text/html", headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"})


# ----------------------------- visitor side -----------------------------

@chat_bp.get("/chat")
def chat_page():
    return Response(VISITOR_PAGE, mimetype="text/html", headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"})


@chat_bp.get("/chat/go")
def private_link():
    """The private link from the invitation email: verifies the person and signs them in."""
    k = request.args.get("k", "")
    if _limited("go:" + _ip(), 30, 900):
        return _page("<h1>Too many tries. Try again later.</h1>", 429)
    if k:
        with _db_lock, _db() as con:
            row = con.execute("SELECT id, email, verified FROM users WHERE autokey=?", (_sha(k),)).fetchone()
            if row:
                first = not row["verified"]
                if first:
                    con.execute("UPDATE users SET verified=1 WHERE id=?", (row["id"],))
        if row:
            _sign_in(row["id"])
            if first:
                _notify_owner("Chat: new person connected", f"{row['email']} opened their private link and connected for the first time.", force=True)
            else:
                _notify_owner("Chat: connected", f"{row['email']} connected to the chat.", row["id"])
            return redirect("/chat", code=302)
    return _page("<h1>This link is not valid.</h1><p>It may have been replaced by a newer one. Ask the person who invited you for a new link.</p>", 403)


@chat_bp.post("/chat/api/request")
def request_link():
    """Person types their email on /chat; their private link is emailed to them."""
    if not _json_only():
        abort(400)
    email = str((request.get_json(silent=True) or {}).get("email", "")).strip().lower()
    if not EMAIL_RE.match(email) or len(email) > 254:
        return jsonify(ok=False, error="Enter a valid email address."), 400
    if _limited("rq:" + _ip(), 5, 900) or _limited("rqe:" + email, 3, 900):
        return jsonify(ok=False, error="Too many tries. Try again later."), 429
    with _db_lock, _db() as con:
        row = con.execute("SELECT id FROM users WHERE email=?", (email,)).fetchone()
        uid = row["id"] if row else con.execute(
            "INSERT INTO users(email,pw,verified,created) VALUES(?,'!',0,?)", (email, time.time())).lastrowid
        key = secrets.token_urlsafe(32)
        con.execute("UPDATE users SET autokey=? WHERE id=?", (_sha(key), uid))
    try:
        _invite_email(email, f"{PUBLIC_URL}/chat/go?k={key}")
    except Exception:
        return jsonify(ok=False, error="The email could not be sent. Try again later."), 502
    return jsonify(ok=True)


@chat_bp.post("/chat/api/logout")
def logout():
    session.clear()
    return jsonify(ok=True)


@chat_bp.post("/chat/api/ping")
def ping():
    """The page calls this when the person is actually using it, which keeps the session unlocked."""
    return (jsonify(ok=True) if _user_id(touch=True) else (jsonify(ok=False), 401))


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


@chat_bp.post("/chat/admin/api/invite")
def admin_invite():
    """Invite a new person by email, or send an existing person a NEW link (the old one stops working)."""
    _need_admin()
    if not _json_only():
        abort(400)
    d = request.get_json(silent=True) or {}
    with _db_lock, _db() as con:
        if d.get("user"):
            row = con.execute("SELECT id, email FROM users WHERE id=?", (int(d["user"]),)).fetchone()
            if not row:
                return jsonify(ok=False, error="Unknown person."), 404
            uid, email = row["id"], row["email"]
        else:
            email = str(d.get("email", "")).strip().lower()
            if not EMAIL_RE.match(email) or len(email) > 254:
                return jsonify(ok=False, error="Enter a valid email address."), 400
            row = con.execute("SELECT id FROM users WHERE email=?", (email,)).fetchone()
            if row:
                uid = row["id"]
            else:
                uid = con.execute("INSERT INTO users(email,pw,verified,created) VALUES(?,'!',0,?)", (email, time.time())).lastrowid
        key = secrets.token_urlsafe(32)
        con.execute("UPDATE users SET autokey=? WHERE id=?", (_sha(key), uid))
    link = f"{PUBLIC_URL}/chat/go?k={key}"
    try:
        _invite_email(email, link)
    except Exception as e:
        return jsonify(ok=False, error=f"The email could not be sent: {e}"), 502
    return jsonify(ok=True, email=email)


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
<section id="locked" hidden>
  <p>This is a private communication channel. Enter your email and we will send you your private link.</p>
  <label for="em">Your email</label><input id="em" type="email" autocomplete="email">
  <button id="req">Email me my private link</button>
  <p class="note" id="lockmsg" role="status" aria-live="polite"></p>
</section>
<section id="room" hidden>
  <p class="note" id="who"></p>
  <div id="log" role="log" aria-live="polite" aria-label="Messages" tabindex="0"></div>
  <label for="body">Message</label><textarea id="body" rows="3"></textarea>
  <button id="send">Send</button><button id="out" class="alt">Sign out</button>
  <p id="msg" role="status" aria-live="polite"></p>
</section>
<script>
const $=id=>document.getElementById(id);let last=0,timer=null,lastPing=0;
const post=(u,d)=>fetch(u,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(d||{})}).then(async r=>({s:r.status,j:await r.json().catch(()=>({}))}));
function add(m){const d=document.createElement('div');d.className='m '+(m.sender==='user'?'me':'them');
 const w=document.createElement('span');w.className='who';w.textContent=(m.sender==='user'?'You':'Owner')+' \\u00b7 '+new Date(m.ts*1000).toLocaleString();
 const b=document.createElement('div');b.textContent=m.body;d.append(w,b);$('log').append(d);$('log').scrollTop=$('log').scrollHeight}
async function poll(){const r=await fetch('/chat/api/messages?after='+last);if(r.status===401){show(false,null,true);return}
 const j=await r.json();j.messages.forEach(m=>{add(m);last=m.id})}
function show(inRoom,email,wasIn){$('locked').hidden=inRoom;$('room').hidden=!inRoom;clearInterval(timer);
 if(inRoom){$('who').textContent='Signed in as '+email;$('log').textContent='';last=0;poll();timer=setInterval(poll,3000);$('body').focus()}
 else if(wasIn){$('lockmsg').textContent='The chat locked after a period without activity. Click your private link again to continue.'}}
$('send').onclick=async()=>{const t=$('body').value.trim();if(!t)return;$('body').value='';
 const r=await post('/chat/api/send',{body:t});if(!r.j.ok){if(r.s===401)show(false,null,true);else $('msg').textContent=r.j.error||'Not sent.'}poll()};
$('body').addEventListener('keydown',e=>{if(e.key==='Enter'&&(e.ctrlKey||e.metaKey)){e.preventDefault();$('send').click()}});
$('req').onclick=async()=>{const r=await post('/chat/api/request',{email:$('em').value});
 $('lockmsg').textContent=r.j.ok?'Done. Check your email and open the private link. Keep it safe.':(r.j.error||'Something went wrong.')};
$('out').onclick=async()=>{await post('/chat/api/logout');show(false)};
['keydown','click','touchstart'].forEach(ev=>document.addEventListener(ev,()=>{const n=Date.now();if(!$('room').hidden&&n-lastPing>60000){lastPing=n;post('/chat/api/ping')}},{passive:true}));
fetch('/chat/api/me').then(r=>r.json()).then(j=>show(!!j.ok,j.email,false)).catch(()=>show(false));
</script></main></body></html>"""

ADMIN_PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><meta name="robots" content="noindex">
<title>Chat inbox</title>""" + _STYLE + """</head><body><main>
<h1>Chat inbox</h1>
<details open><summary>Invite a person</summary>
  <p class="note">They get an email with a private link. Opening it verifies them and signs them in.</p>
  <label for="ie">Their email</label><input id="ie" type="email" autocomplete="off">
  <button id="inv">Send invitation</button>
  <p id="invout" role="status" aria-live="polite"></p>
</details>
<label for="pick">Conversation</label><select id="pick"></select>
<button id="rot" class="alt">Send this person a new link</button>
<div id="log" role="log" aria-live="polite" aria-label="Messages" tabindex="0" style="margin-top:12px"></div>
<label for="body">Reply</label><textarea id="body" rows="3"></textarea>
<button id="send">Send</button>
<script>
const $=id=>document.getElementById(id);let cur=0,last=0;
const api=(u,o)=>fetch(u,o).then(r=>r.json());
const jpost=(u,d)=>api(u,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(d||{})});
function add(m){const d=document.createElement('div');d.className='m '+(m.sender==='owner'?'me':'them');
 const w=document.createElement('span');w.className='who';w.textContent=(m.sender==='owner'?'You':'Visitor')+' \\u00b7 '+new Date(m.ts*1000).toLocaleString();
 const b=document.createElement('div');b.textContent=m.body;d.append(w,b);$('log').append(d);$('log').scrollTop=$('log').scrollHeight}
async function threads(){const j=await api('/chat/admin/api/threads');const keep=$('pick').value;$('pick').textContent='';
 j.threads.forEach(t=>{const o=document.createElement('option');o.value=t.id;
  o.textContent=t.email+(t.verified?'':' (invited, not opened yet)')+(t.unread?' ['+t.unread+' new]':'');$('pick').append(o)});
 if(keep)$('pick').value=keep;if(!cur&&j.threads.length){cur=+$('pick').value;load()}}
async function poll(){if(!cur)return;const j=await api('/chat/admin/api/messages?user='+cur+'&after='+last);j.messages.forEach(m=>{add(m);last=m.id})}
function load(){$('log').textContent='';last=0;poll()}
$('inv').onclick=async()=>{const e=$('ie').value.trim();if(!e)return;$('invout').textContent='Sending...';
 const j=await jpost('/chat/admin/api/invite',{email:e});$('invout').textContent=j.ok?'Invitation sent to '+j.email+'.':(j.error||'Could not send.');if(j.ok)$('ie').value='';threads()};
$('rot').onclick=async()=>{if(!cur)return;if(!confirm('Send this person a new link? The old link stops working.'))return;
 const j=await jpost('/chat/admin/api/invite',{user:cur});$('invout').textContent=j.ok?'New link sent to '+j.email+'. The old one no longer works.':(j.error||'Could not send.')};
$('pick').onchange=()=>{cur=+$('pick').value;load()};
$('send').onclick=async()=>{const t=$('body').value.trim();if(!t||!cur)return;$('body').value='';
 await jpost('/chat/admin/api/send',{user:cur,body:t});poll()};
$('body').addEventListener('keydown',e=>{if(e.key==='Enter'&&(e.ctrlKey||e.metaKey)){e.preventDefault();$('send').click()}});
threads();setInterval(()=>{poll();threads()},4000);
</script></main></body></html>"""
