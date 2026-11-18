// Siraugga Lab Cloud: one real-Linux container per learner+lab, a web terminal, and server-side grading.
//
//   POST /lab/session          (signed by the Siraugga backend with the learner's key) -> {app, terminal, expires}
//   POST /lab/run              (signed likewise) {"lab","command"} -> {returncode, output}; one command as the learner
//   GET  /app/<token>          the lab page (tasks + terminal + Check buttons)
//   GET  /lab/info/<token>     lab description (no answers)
//   POST /lab/check/<token>    {"step":"1"} -> grader inside the container; a pass is recorded in D1
//   ANY  /t/<token>/...        the terminal (HTTP + WebSocket) proxied to the learner's container
//
// Secrets: LAB_MASTER_SECRET. Learner key = HMAC(master, learnerId). Browser tokens are signed + expire.
import { Container, getContainer } from "@cloudflare/containers";

const ID_RE = /^[A-Za-z0-9_.@-]{1,64}$/;
const LAB_RE = /^[A-Za-z0-9_-]{1,48}$/;
const TOKEN_TTL = 4 * 3600;
const MAX_SKEW = 300;           // signed backend requests older/newer than 5 min are refused (replay window)
const enc = new TextEncoder();

export class LabContainer extends Container {
  defaultPort = 7681;          // ttyd (terminal)
  requiredPorts = [7681, 8080]; // 8080 = grader
  sleepAfter = "10m";          // idle containers are shut down (and cost nothing)
  enableInternet = false;      // learners get no outbound network

  async startLab(labId) {
    const st = await this.getState();
    if (st.status !== "running" && st.status !== "healthy") {
      await this.startAndWaitForPorts({ startOptions: { envVars: { LAB_ID: labId } }, ports: [7681, 8080] });
    }
  }
  async grader(path, init) {
    return this.containerFetch(new Request("http://grader" + path, init), 8080);
  }
  // Sliding-window rate limit. Each learner+lab has exactly one of these coordinators, so it counts their requests.
  rate(kind, limit, windowMs) {
    const now = Date.now();
    this.hits ??= {};
    const recent = (this.hits[kind] || []).filter(t => now - t < windowMs);
    const allowed = recent.length < limit;
    if (allowed) recent.push(now);
    this.hits[kind] = recent;
    return allowed;
  }
}

// ---------- crypto helpers
async function hmacHex(secret, data) {
  const key = await crypto.subtle.importKey("raw", enc.encode(secret), { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
  const sig = await crypto.subtle.sign("HMAC", key, enc.encode(data));
  return [...new Uint8Array(sig)].map(b => b.toString(16).padStart(2, "0")).join("");
}
function safeEqual(a, b) {
  if (a.length !== b.length) return false;
  let d = 0;
  for (let i = 0; i < a.length; i++) d |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return d === 0;
}
const b64u = s => btoa(s).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
const unb64u = s => atob(s.replace(/-/g, "+").replace(/_/g, "/"));
const SEC_HEADERS = { "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff", "Referrer-Policy": "no-referrer" };
const json = (o, status = 200) => Response.json(o, { status, headers: SEC_HEADERS });

async function mintToken(env, learner, lab) {
  const payload = b64u(JSON.stringify({ l: learner, b: lab, e: Math.floor(Date.now() / 1000) + TOKEN_TTL }));
  return `${payload}.${await hmacHex(env.LAB_MASTER_SECRET, "token:v1." + payload)}`;
}
async function readToken(env, token) {
  const [payload, sig] = String(token).split(".");
  if (!payload || !sig) return null;
  if (!safeEqual(sig, await hmacHex(env.LAB_MASTER_SECRET, "token:v1." + payload))) return null;
  try {
    const t = JSON.parse(unb64u(payload));
    if (t.e < Date.now() / 1000 || !ID_RE.test(t.l) || !LAB_RE.test(t.b)) return null;
    return { learner: t.l, lab: t.b, exp: t.e };
  } catch { return null; }
}
// Per learner+lab limits (requests, per milliseconds). Generous for a person typing, tight for a script.
const LIMITS = { check: [30, 60000], run: [120, 60000], session: [20, 60000] };
async function limited(env, t, kind) {
  const [limit, windowMs] = LIMITS[kind];
  const stub = getContainer(env.LAB, `${t.learner}~${t.lab}`);
  if (await stub.rate(kind, limit, windowMs)) return null;
  return Response.json({ error: "too many requests, slow down" }, { status: 429, headers: { ...SEC_HEADERS, "Retry-After": String(Math.ceil(windowMs / 1000)) } });
}
async function containerFor(env, t) {
  const stub = getContainer(env.LAB, `${t.learner}~${t.lab}`);
  await stub.startLab(t.lab);
  return stub;
}

// ---------- routes
// A request from the Siraugga backend: body signed with the learner's key. Returns {learner, p} or {error: Response}.
async function verifySigned(request, env, maxLen) {
  const learner = request.headers.get("X-Lab-Learner") || "";
  if (!ID_RE.test(learner)) return { error: json({ error: "bad learner" }, 401) };
  const raw = await request.text();
  if (raw.length > maxLen) return { error: json({ error: "too large" }, 400) };
  const key = await hmacHex(env.LAB_MASTER_SECRET, "learner:" + learner);
  if (!safeEqual(request.headers.get("X-Lab-Signature") || "", await hmacHex(key, raw))) return { error: json({ error: "bad signature" }, 401) };
  let p;
  try { p = JSON.parse(raw); } catch { return { error: json({ error: "bad json" }, 400) }; }
  if (!LAB_RE.test(p.lab || "")) return { error: json({ error: "bad lab" }, 400) };
  const ts = Number(p.ts);
  if (!Number.isFinite(ts) || Math.abs(Date.now() / 1000 - ts) > MAX_SKEW) return { error: json({ error: "stale or missing timestamp" }, 401) };
  return { learner, p };
}

// Runs ONE command as the learner inside their container (used by course steps). Returns {returncode, output}.
async function run(request, env) {
  const v = await verifySigned(request, env, 4096);
  if (v.error) return v.error;
  const cmd = v.p.command;
  if (typeof cmd !== "string" || !cmd.trim() || cmd.length > 2000) return json({ error: "bad command" }, 400);
  const rl = await limited(env, { learner: v.learner, lab: v.p.lab }, "run");
  if (rl) return rl;
  let c;
  try { c = await containerFor(env, { learner: v.learner, lab: v.p.lab }); }
  catch (e) { return json({ error: "no capacity or unknown lab" }, 503); }
  const r = await c.grader("/exec", { method: "POST", body: JSON.stringify({ command: cmd }) });
  return json(await r.json(), r.status);
}

async function session(request, env) {
  const v = await verifySigned(request, env, 1024);
  if (v.error) return v.error;
  const { learner, p } = v;
  const rl = await limited(env, { learner, lab: p.lab }, "session");
  if (rl) return rl;
  const token = await mintToken(env, learner, p.lab);
  const t = await readToken(env, token);
  try { await containerFor(env, t); }                       // warm it so the terminal opens fast
  catch (e) { return json({ error: "no capacity or unknown lab", detail: String(e.message || e).slice(0, 120) }, 503); }
  return json({ app: `/app/${token}`, terminal: `/t/${token}/`, expires: t.exp });
}

async function check(request, env, t) {
  const rl = await limited(env, t, "check");
  if (rl) return rl;
  const raw = await request.text();
  if (raw.length > 256) return json({ error: "too large" }, 400);
  let step;
  try { ({ step } = JSON.parse(raw)); } catch { return json({ error: "bad json" }, 400); }
  const c = await containerFor(env, t);
  const r = await c.grader("/check", { method: "POST", body: JSON.stringify({ step: String(step) }) });
  const out = await r.json();
  if (out.passed) {                                        // deterministic id => repeating a pass is recorded once
    await env.DB.prepare(
      "INSERT OR IGNORE INTO lab_progress (id, learner, lab, step, command, client_ts, replayed, received_at) VALUES (?,?,?,?,?,?,?,?)")
      .bind(`${t.learner}:${t.lab}:${String(step).slice(0, 3)}`, t.learner, t.lab, String(step).slice(0, 3), "grader-pass",
            0, 0, Math.floor(Date.now() / 1000)).run();
  }
  return json(out, r.status);
}

export default {
  async fetch(request, env) {
    if (!env.LAB_MASTER_SECRET) return json({ error: "server not configured" }, 503);
    const url = new URL(request.url);
    const parts = url.pathname.split("/").filter(Boolean);

    if (request.method === "POST" && url.pathname === "/lab/session") return session(request, env);
    if (request.method === "POST" && url.pathname === "/lab/run") return run(request, env);

    const kind = parts[0] === "lab" ? parts[1] : parts[0];   // app | info | check | t
    const token = parts[0] === "lab" ? parts[2] : parts[1];
    if (!["app", "info", "check", "t"].includes(kind) || !token) return json({ error: "not found" }, 404);
    const t = await readToken(env, token);
    if (!t) return json({ error: "link expired or invalid" }, 401);

    if (kind === "app") {
      const nonce = btoa(String.fromCharCode(...crypto.getRandomValues(new Uint8Array(16))));
      const csp = `default-src 'none'; script-src 'nonce-${nonce}'; style-src 'nonce-${nonce}'; connect-src 'self'; frame-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors ${env.EMBED_ORIGINS || "'self'"}`;   // EMBED_ORIGINS = the Siraugga site(s) allowed to embed this page
      return new Response(APP_HTML(token, nonce), { headers: { ...SEC_HEADERS, "Content-Type": "text/html; charset=utf-8", "Content-Security-Policy": csp } });
    }
    if (kind === "info") { const c = await containerFor(env, t); return c.grader("/info"); }
    if (kind === "check" && request.method === "POST") return check(request, env, t);
    if (kind === "t") {
      const stub = await containerFor(env, t);
      const target = new URL(request.url);
      target.pathname = "/" + parts.slice(2).join("/");   // /t/<token>/ws -> /ws
      return stub.fetch(new Request(target, request));   // Container.fetch proxies HTTP and WebSocket to ttyd
    }
    return json({ error: "not found" }, 404);
  },
};

const APP_HTML = (token, nonce) => `<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Siraugga Lab</title><style nonce="${nonce}">
:root{--bg:#0f1115;--fg:#e8eaf0;--mut:#9aa3b2;--card:#171a21;--ok:#3fb950;--bad:#f85149;--acc:#58a6ff}
@media(prefers-color-scheme:light){:root{--bg:#f6f7f9;--fg:#1b1f27;--mut:#5b6573;--card:#fff;--acc:#0969da}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:15px system-ui,sans-serif;display:flex;height:100vh}
aside{width:340px;padding:16px;overflow:auto;border-right:1px solid #8884}main{flex:1}iframe{width:100%;height:100%;border:0;background:#000}
h1{font-size:18px;margin:0 0 12px}.step{background:var(--card);border-radius:10px;padding:12px;margin-bottom:10px}
.step.done{outline:2px solid var(--ok)}button{background:var(--acc);color:#fff;border:0;border-radius:8px;padding:6px 12px;cursor:pointer}
.mut{color:var(--mut);font-size:13px}.msg{margin-top:6px;font-size:13px}.msg.bad{color:var(--bad)}.msg.ok{color:var(--ok)}
@media(max-width:800px){body{flex-direction:column;height:auto}aside{width:auto;border:0}main{height:70vh}}</style></head><body>
<aside><h1 id="t">Loading…</h1><div id="s"></div><p class="mut">Type commands in the terminal, then press Check.</p></aside>
<main><iframe src="/t/${token}/" title="Lab terminal"></iframe></main>
<script nonce="${nonce}">
const T=${JSON.stringify(token)};
fetch('/lab/info/'+T).then(r=>r.json()).then(lab=>{
 document.getElementById('t').textContent=lab.title;
 const box=document.getElementById('s');
 lab.steps.forEach(st=>{const d=document.createElement('div');d.className='step';
  const p=document.createElement('div');p.textContent='Step '+st.id+': '+st.task;
  const b=document.createElement('button');b.textContent='Check';
  const h=document.createElement('button');h.textContent='Hint';h.style.cssText='margin-left:6px;background:transparent;color:var(--acc);border:1px solid var(--acc)';
  const m=document.createElement('div');m.className='msg';let hi=0;
  b.onclick=async()=>{b.disabled=true;try{const r=await fetch('/lab/check/'+T,{method:'POST',body:JSON.stringify({step:st.id})});const o=await r.json();
    m.className='msg '+(o.passed?'ok':'bad');m.textContent=o.message||(o.error||'');if(o.passed)d.classList.add('done');}catch(e){m.className='msg bad';m.textContent='Could not reach the lab server.'}b.disabled=false};
  h.onclick=()=>{m.className='msg mut';m.textContent='Hint: '+st.hints[Math.min(hi++,st.hints.length-1)]};
  const row=document.createElement('div');row.style.marginTop='8px';row.append(b,h);d.append(p,row,m);box.append(d)})
}).catch(()=>{document.getElementById('t').textContent='Could not load the lab'});
</script></body></html>`;
