// Server side of the lab kit: POST /lab/exec on api.mikeytech.dev (route it next to joshy-api).
// NOT deployed yet. Only commands a lab marks "remote" ever arrive here.
//
// Secrets/bindings: LAB_MASTER_SECRET (Worker secret), DB (D1, table lab_progress - see lab_schema.sql).
// Per-learner key = HMAC-SHA256(LAB_MASTER_SECRET, learnerId). Issue one with issue_key.py.
// One leaked learner key can only act as that learner.

const ALLOWED = { labctl: ["complete", "status"] };   // server-side allowlist: never trust the client
const ID_RE = /^[A-Za-z0-9_.@-]{1,64}$/;

const enc = new TextEncoder();
async function hmacHex(secret, data) {
  const key = await crypto.subtle.importKey("raw", enc.encode(secret),
    { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
  const sig = await crypto.subtle.sign("HMAC", key, enc.encode(data));
  return [...new Uint8Array(sig)].map(b => b.toString(16).padStart(2, "0")).join("");
}
function safeEqual(a, b) {
  if (a.length !== b.length) return false;
  let d = 0;
  for (let i = 0; i < a.length; i++) d |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return d === 0;
}
const json = (o, status = 200) => Response.json(o, { status });

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (request.method !== "POST" || url.pathname !== "/lab/exec") return json({ error: "not found" }, 404);
    if (!env.LAB_MASTER_SECRET) return json({ error: "server not configured" }, 503);

    const learner = request.headers.get("X-Lab-Learner") || "";
    if (!ID_RE.test(learner)) return json({ error: "bad learner" }, 401);
    const raw = await request.text();
    if (raw.length > 4096) return json({ error: "too large" }, 400);
    const learnerKey = await hmacHex(env.LAB_MASTER_SECRET, learner);
    const want = await hmacHex(learnerKey, raw);
    if (!safeEqual(request.headers.get("X-Lab-Signature") || "", want)) return json({ error: "bad signature" }, 401);

    let p;
    try { p = JSON.parse(raw); } catch { return json({ error: "bad json" }, 400); }
    if (p.learner !== learner || !/^[0-9a-f]{32}$/.test(p.id || "")) return json({ error: "bad request" }, 400);
    const [cmd, sub] = String(p.command || "").trim().split(/\s+/);
    if (!ALLOWED[cmd] || !ALLOWED[cmd].includes(sub)) return json({ error: "command not allowed" }, 403);

    // INSERT OR IGNORE on the request id: a replayed (offline-queued) request is counted once.
    const r = await env.DB.prepare(
      "INSERT OR IGNORE INTO lab_progress (id, learner, lab, step, command, client_ts, replayed, received_at) " +
      "VALUES (?, ?, ?, ?, ?, ?, ?, ?)")
      .bind(p.id, learner, String(p.lab).slice(0, 64), String(p.step).slice(0, 16),
            `${cmd} ${sub}`, Number(p.ts) || 0, p.replayed ? 1 : 0, Math.floor(Date.now() / 1000)).run();
    const fresh = (r.meta && r.meta.changes) > 0;
    return json({ output: `${cmd}: registered lab '${p.lab}'${fresh ? "" : " (already recorded)"}` });
  },
};
