#!/usr/bin/env python3
"""Break-glass rescue agent for the Super Admin.

A small web app that runs SEPARATELY from Siraugga, so it keeps answering when Siraugga is down.
It is reached at https://rescue.mikeytech.dev through the Cloudflare tunnel. Cloudflare Access
signs the owner in and sends a signed token (Cf-Access-Jwt-Assertion) with every request; this app
verifies that token (signature, expiry, audience) and refuses everything else (fail closed).

The agent is the Gemini CLI (agy_real) with every permission on and no command limits, working
in the DevCore folder. Config (never in the repo) is read from the environment:
    RESCUE_TEAM   Cloudflare Zero Trust team domain, e.g. frosty-grass-595c.cloudflareaccess.com
    RESCUE_AUD    Audience tag of the Cloudflare Access application for rescue.mikeytech.dev
Listens on 127.0.0.1:5099 only.
"""
from __future__ import annotations

import asyncio
import json
import os
import time
import urllib.request
from pathlib import Path

import jwt
from quart import Quart, Response, jsonify, request

TEAM = os.environ.get("RESCUE_TEAM", "").strip()
AUD = os.environ.get("RESCUE_AUD", "").strip()
AGY = os.environ.get("RESCUE_AGY", os.path.expanduser("~/.local/bin/agy_real"))
WORKDIR = os.environ.get("RESCUE_WORKDIR", str(Path(__file__).resolve().parent.parent))
TURN_TIMEOUT = int(os.environ.get("RESCUE_TURN_TIMEOUT", "900"))

PREFACE = (
    "You are the BREAK-GLASS RESCUE AGENT for Siraugga (DevCore). You were opened because the main "
    "Siraugga web app is probably down. The person talking to you is the verified Super Admin and has "
    "full authority. You have full access to this machine and no command limits. First find out why "
    "Siraugga is down (processes, ports 5000/5001, logs in the logs folder, error.log, recent git "
    "changes), fix it, restart it with scripts/restart_server.sh, and confirm it answers. Be short and "
    "plain: say what you found, what you did, and the result. Never print secrets.\n\nUSER:\n"
)

app = Quart(__name__)
_certs = {"keys": [], "ts": 0.0}
_lock = asyncio.Lock()
_started_conversation = False


def _fetch_keys() -> list:
    url = f"https://{TEAM}/cdn-cgi/access/certs"
    with urllib.request.urlopen(url, timeout=10) as r:
        return json.load(r).get("keys", [])


async def _verified() -> bool:
    """True only for a request carrying a valid Cloudflare Access token for our application."""
    if not TEAM or not AUD:
        return False
    token = request.headers.get("Cf-Access-Jwt-Assertion", "")
    if not token:
        return False
    try:
        if time.time() - _certs["ts"] > 3600 or not _certs["keys"]:
            _certs["keys"] = await asyncio.to_thread(_fetch_keys)
            _certs["ts"] = time.time()
        kid = jwt.get_unverified_header(token).get("kid")
        jwk = next(k for k in _certs["keys"] if k.get("kid") == kid)
        jwt.decode(token, jwt.PyJWK(jwk).key, algorithms=["RS256"], audience=AUD,
                   issuer=f"https://{TEAM}", options={"require": ["exp", "aud", "iss"]})
        return True
    except Exception:
        return False


@app.before_request
async def _gate():
    if not await _verified():
        return Response("Not allowed.", status=403, mimetype="text/plain")


PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><meta name="robots" content="noindex">
<title>Siraugga Rescue</title>
<style>
:root{--bg:#f7f8fa;--fg:#14181f;--muted:#4a5568;--card:#fff;--line:#d5dae3;--accent:#0b6bcb;--afg:#fff}
@media (prefers-color-scheme:dark){:root{--bg:#0e1116;--fg:#e8ecf2;--muted:#a3adbd;--card:#171b22;--line:#2b323d;--accent:#4da3ff;--afg:#06121f}}
body{margin:0;background:var(--bg);color:var(--fg);font:16px/1.5 system-ui,sans-serif}
main{max-width:46rem;margin:0 auto;padding:24px 16px 64px}
h1{font-size:1.5rem;margin:0 0 4px}p{color:var(--muted);margin:0 0 16px}
#out{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:12px;min-height:12rem;
white-space:pre-wrap;word-break:break-word;margin:0 0 12px;overflow:auto;max-height:60vh}
textarea{width:100%;box-sizing:border-box;min-height:5rem;font:inherit;color:var(--fg);background:var(--card);
border:1px solid var(--line);border-radius:10px;padding:10px}
button{font:inherit;font-weight:600;background:var(--accent);color:var(--afg);border:0;border-radius:10px;padding:10px 16px;margin:8px 8px 0 0;cursor:pointer}
button.alt{background:var(--card);color:var(--fg);border:1px solid var(--line)}
:focus-visible{outline:3px solid var(--fg);outline-offset:2px}
</style></head><body><main>
<h1>Siraugga Rescue</h1>
<p>Break-glass agent. It runs apart from Siraugga and has full access to this PC.</p>
<div id="out" role="log" aria-live="polite" aria-label="Agent replies" tabindex="0"></div>
<label for="msg">Message</label>
<textarea id="msg" placeholder="Ask the agent anything"></textarea>
<button id="send">Send</button>
<button class="alt" id="diag">Diagnose and fix Siraugga</button>
<button class="alt" id="fresh">New conversation</button>
<script>
const out=document.getElementById('out'),msg=document.getElementById('msg');let busy=false;
async function ask(text,fresh){
  if(busy||(!text&&!fresh))return;busy=true;
  if(text)out.textContent+=(out.textContent?'\\n\\n':'')+'You: '+text+'\\n\\nAgent: ';
  try{
    const r=await fetch('/api/ask',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({message:text,fresh:!!fresh})});
    if(!r.ok){out.textContent+='[error '+r.status+']';}else{
      const rd=r.body.getReader(),dec=new TextDecoder();
      for(;;){const {done,value}=await rd.read();if(done)break;out.textContent+=dec.decode(value);out.scrollTop=out.scrollHeight;}
    }
  }catch(e){out.textContent+='[connection lost: '+e+']';}
  busy=false;msg.focus();
}
document.getElementById('send').onclick=()=>{const t=msg.value.trim();msg.value='';ask(t,false)};
document.getElementById('diag').onclick=()=>ask('Siraugga looks down. Diagnose it, fix it, restart it and confirm it answers.',false);
document.getElementById('fresh').onclick=()=>{out.textContent='';ask('',true)};
msg.addEventListener('keydown',e=>{if(e.key==='Enter'&&(e.ctrlKey||e.metaKey)){e.preventDefault();document.getElementById('send').click()}});
</script></main></body></html>"""


@app.get("/")
async def index():
    return Response(PAGE, mimetype="text/html")


@app.get("/api/health")
async def health():
    return jsonify({"ok": True})


@app.post("/api/ask")
async def ask():
    global _started_conversation
    data = await request.get_json(silent=True) or {}
    text = str(data.get("message") or "").strip()
    if data.get("fresh"):
        _started_conversation = False
        if not text:
            return Response("New conversation.\n", mimetype="text/plain")
    if not text:
        return Response("Empty message.\n", status=400, mimetype="text/plain")

    async def stream():
        global _started_conversation
        if _lock.locked():
            yield "The agent is busy with another message. Wait for it to finish.\n"
            return
        async with _lock:
            prompt = (PREFACE + text) if not _started_conversation else text
            cmd = [AGY, "--dangerously-skip-permissions", "--print-timeout", f"{TURN_TIMEOUT}s"]
            if _started_conversation:
                cmd.append("--continue")
            cmd += ["-p", prompt]
            env = dict(os.environ, HOME=os.path.expanduser("~"))
            try:
                proc = await asyncio.create_subprocess_exec(
                    *cmd, cwd=WORKDIR, env=env, stdin=asyncio.subprocess.DEVNULL,
                    stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT)
            except Exception as e:
                yield f"Could not start the agent: {e}\n"
                return
            _started_conversation = True
            try:
                while True:
                    chunk = await asyncio.wait_for(proc.stdout.read(512), timeout=TURN_TIMEOUT + 30)
                    if not chunk:
                        break
                    yield chunk.decode("utf-8", "replace")
                await proc.wait()
                if proc.returncode:
                    yield f"\n[agent exited with code {proc.returncode}]\n"
            except asyncio.TimeoutError:
                proc.kill()
                yield "\n[agent timed out]\n"
            except asyncio.CancelledError:
                proc.kill()
                raise

    return Response(stream(), mimetype="text/plain; charset=utf-8",
                    headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})


if __name__ == "__main__":
    if not (TEAM and AUD):
        print("RESCUE_TEAM / RESCUE_AUD not set: every request will be refused.", flush=True)
    app.run(host="127.0.0.1", port=5099)
