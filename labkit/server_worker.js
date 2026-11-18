// Server side of the lab kit: POST /lab/exec on api.mikeytech.dev (route it next to joshy-api).
// NOT deployed yet - prototype. Only commands the lab marks "remote" ever arrive here.
//
// Needs Worker secret LAB_TOKEN_SECRET. Production should use a per-learner token (issued at
// enrolment) instead of one shared secret; the client signs the body with HMAC-SHA256.

const ALLOWED = { labctl: ["complete", "status"] };   // server-side allowlist, never trust the client

async function hmacHex(secret, body) {
  const key = await crypto.subtle.importKey("raw", new TextEncoder().encode(secret),
    { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
  const sig = await crypto.subtle.sign("HMAC", key, new TextEncoder().encode(body));
  return [...new Uint8Array(sig)].map(b => b.toString(16).padStart(2, "0")).join("");
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (request.method !== "POST" || url.pathname !== "/lab/exec")
      return new Response("not found", { status: 404 });
    const raw = await request.text();
    const want = await hmacHex(env.LAB_TOKEN_SECRET || "", raw);
    if ((request.headers.get("X-Lab-Signature") || "") !== want)
      return Response.json({ error: "bad signature" }, { status: 401 });
    let p;
    try { p = JSON.parse(raw); } catch { return Response.json({ error: "bad json" }, { status: 400 }); }
    const [cmd, sub] = String(p.command || "").trim().split(/\s+/);
    if (!ALLOWED[cmd] || !ALLOWED[cmd].includes(sub))
      return Response.json({ error: "command not allowed" }, { status: 403 });
    // TODO: write to D1 (lab_progress: lab, step, ts, replayed) - idempotent on (lab, step, ts).
    return Response.json({ output: `${cmd}: registered lab '${p.lab}'` });
  },
};
