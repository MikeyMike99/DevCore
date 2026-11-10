// api.mikeytech.dev: the JOSHY server, running entirely on Cloudflare (Worker + D1).
//
// Public (used by the JOSHY desktop app, see Audio_pllayback_suite/demo_license.py):
//   GET/POST /api/audio_suite/handshake   demo-license check + update info
//   GET/POST /api/audio_suite/feedback    in-app bug reports / suggestions
// Same behaviour as e-profile's server.py handlers, with D1 instead of JSON files.
// If D1 itself fails, the request is forwarded to FALLBACK_URL (PythonAnywhere).
//
// Admin (Authorization: Bearer ADMIN_SECRET), used by the PC's e-profile sync and CyberBrief:
//   GET  /admin/export?feedback_since=TS&calibration_after=ID&downloads_after=ID
//   GET  /admin/newsletter-queue        signups/unsubscribes stored while the PC was off
//   POST /admin/newsletter-queue/done   body = {ids: [...]}
//   POST /admin/releases            body = audio_suite_releases.json
//   POST /admin/licenses/merge      body = {records: [...]}  (usage: min first_run /
//                                   max last_seen; admin fields from the PC)

const DEFAULT_RELEASE = {
  version: "1.0.1",
  download_url: "https://github.com/MikeyMike99/JOSHY/releases/tag/v1.0.1",
  changelog: "",
  stage_status: "PUBLISHED",
};
const SA_OFFSET = "+02:00"; // release dates are written in South Africa time (no DST)

const json = (status, body) => new Response(JSON.stringify(body), {
  status, headers: { "content-type": "application/json", "cache-control": "no-store" },
});

// Same as Python: [int(x) for x in re.sub(r"[^0-9.]", "", v).split(".") if x], list compare.
function parseVer(v) {
  return String(v || "").replace(/[^0-9.]/g, "").split(".").filter(Boolean).map(Number);
}
export function isNewerVersion(latest, current) {
  const a = parseVer(latest), b = parseVer(current);
  for (let i = 0; i < Math.min(a.length, b.length); i++) {
    if (a[i] !== b[i]) return a[i] > b[i];
  }
  return a.length > b.length;
}

export function isReleasePublic(rel, nowMs = Date.now()) {
  const stage = String(rel.stage_status || "PUBLISHED").trim().toUpperCase();
  if (stage === "PUBLISHED") return true;
  if (stage !== "SCHEDULED") return false;
  const when = String(rel.scheduled_date || rel.release_date || "").trim().replace(" ", "T");
  if (!when) return false;
  const iso = when.length === 10 ? `${when}T00:00:00` : when.length === 16 ? `${when}:00` : when;
  const t = Date.parse(/[zZ]|[+-]\d\d:\d\d$/.test(iso) ? iso : iso + SA_OFFSET);
  return Number.isFinite(t) && nowMs >= t;
}

async function getReleases(env) {
  const row = await env.DB.prepare("SELECT value FROM settings WHERE key = 'joshy_releases'").first();
  try { return row ? { ...DEFAULT_RELEASE, ...JSON.parse(row.value) } : DEFAULT_RELEASE; }
  catch { return DEFAULT_RELEASE; }
}

async function handshake(request, env) {
  const rel = await getReleases(env);
  const released = isReleasePublic(rel);
  if (request.method === "GET") {
    return json(200, { service: "Audio Playback Suite Attestation & Update Service", status: "ONLINE",
      latest_version: rel.version, download_url: rel.download_url });
  }
  let data = {};
  try { data = await request.json(); } catch { data = {}; }
  if (!data || !data.hwid) return json(400, { error: "Missing hardware identifier" });

  const hwid = String(data.hwid).trim();
  const appVersion = String(data.app_version ?? "1.0.0").trim();
  const lfr = typeof data.local_first_run === "number" ? Math.trunc(data.local_first_run) : null;
  const now = Math.floor(Date.now() / 1000);

  let rec = await env.DB.prepare("SELECT * FROM joshy_licenses WHERE hwid = ?").bind(hwid).first();
  if (!rec) {
    rec = { hwid, first_run: lfr && lfr > 0 && lfr <= now ? lfr : now, last_seen: now,
            duration_days: 14, app_version: appVersion, remote_revoked: 0 };
  } else {
    if (lfr && lfr > 0 && lfr < rec.first_run) rec.first_run = lfr;
    rec.last_seen = now;
    rec.app_version = appVersion;
  }
  const duration = rec.duration_days ?? 14;
  const expiresAt = rec.first_run + duration * 86400;
  const revoked = Boolean(rec.remote_revoked);
  const status = revoked ? "REVOKED" : now >= expiresAt ? "EXPIRED" : "ACTIVE";

  await env.DB.prepare(
    `INSERT INTO joshy_licenses (hwid, first_run, last_seen, duration_days, app_version, remote_revoked, status)
     VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7)
     ON CONFLICT(hwid) DO UPDATE SET first_run = ?2, last_seen = ?3, app_version = ?5, status = ?7`,
  ).bind(hwid, rec.first_run, now, duration, appVersion, revoked ? 1 : 0, status).run();

  return json(200, {
    status, hwid, server_time: now, first_run: rec.first_run, expires_at: expiresAt,
    duration_days: duration,
    days_remaining: status === "ACTIVE" ? Math.max(0, Math.ceil((expiresAt - now) / 86400)) : 0,
    remote_revoked: revoked,
    update_available: released ? isNewerVersion(rel.version, appVersion) : false,
    latest_version: rel.version, download_url: rel.download_url, changelog: rel.changelog || "",
  });
}

function saTime(ts) {
  return new Date((ts + 7200) * 1000).toISOString().replace("T", " ").slice(0, 19);
}

async function feedback(request, env) {
  if (request.method === "GET") return json(200, { service: "Audio Playback Suite Feedback Service", status: "ONLINE" });
  let data = {};
  try { data = await request.json(); } catch { data = {}; }
  const message = String(data.message ?? "").trim();
  if (!message) return json(400, { error: "Message content is required" });
  let type = String(data.type ?? "bug").trim().toLowerCase();
  if (!["bug", "suggestion", "general"].includes(type)) type = "general";
  const now = Math.floor(Date.now() / 1000);
  const id = crypto.randomUUID().slice(0, 8);
  await env.DB.prepare(
    "INSERT INTO joshy_feedback (id, hwid, type, subject, message, app_version, timestamp, formatted_time) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
  ).bind(id, String(data.hwid ?? "UNKNOWN").trim().slice(0, 200), type,
         String(data.subject ?? "Untitled Report").trim().slice(0, 300), message.slice(0, 10000),
         String(data.app_version ?? "1.0.0").trim().slice(0, 40), now, saTime(now)).run();
  return json(200, { success: true, id, status: "RECEIVED" });
}

function isAdmin(request, env) {
  const got = (request.headers.get("authorization") || "").replace(/^Bearer\s+/i, "");
  if (!env.ADMIN_SECRET || got.length !== env.ADMIN_SECRET.length) return false;
  let diff = 0;
  for (let i = 0; i < got.length; i++) diff |= got.charCodeAt(i) ^ env.ADMIN_SECRET.charCodeAt(i);
  return diff === 0;
}

async function admin(request, env, url) {
  if (!isAdmin(request, env)) return json(404, { success: false, error: "Not found" });
  const p = url.pathname;
  if (p === "/admin/export" && request.method === "GET") {
    const fbSince = Number(url.searchParams.get("feedback_since") || 0);
    const calAfter = Number(url.searchParams.get("calibration_after") || 0);
    const dlAfter = Number(url.searchParams.get("downloads_after") || 0);
    const [lic, fb, cal, dl] = await env.DB.batch([
      env.DB.prepare("SELECT * FROM joshy_licenses"),
      env.DB.prepare("SELECT * FROM joshy_feedback WHERE timestamp >= ? ORDER BY timestamp").bind(fbSince),
      env.DB.prepare("SELECT * FROM echos_calibration WHERE id > ? ORDER BY id LIMIT 5000").bind(calAfter),
      env.DB.prepare("SELECT * FROM joshy_downloads WHERE id > ? ORDER BY id LIMIT 5000").bind(dlAfter),
    ]);
    return json(200, { licenses: lic.results, feedback: fb.results, calibration: cal.results, downloads: dl.results });
  }
  if (p === "/admin/newsletter-queue" && request.method === "GET") {
    const rows = await env.DB.prepare(
      "SELECT id, created_at, action, payload FROM newsletter_queue WHERE processed_at IS NULL ORDER BY id LIMIT 200").all();
    return json(200, { items: rows.results });
  }
  if (p === "/admin/newsletter-queue/done" && request.method === "POST") {
    const { ids = [] } = await request.json();
    const now = Math.floor(Date.now() / 1000);
    const stmts = ids.filter(Number.isFinite).map((id) =>
      env.DB.prepare("UPDATE newsletter_queue SET processed_at = ? WHERE id = ?").bind(now, id));
    for (let i = 0; i < stmts.length; i += 50) await env.DB.batch(stmts.slice(i, i + 50));
    return json(200, { success: true, done: stmts.length });
  }
  if (p === "/admin/releases" && request.method === "POST") {
    const rel = await request.json();
    if (!rel || !rel.version) return json(400, { error: "version required" });
    await env.DB.prepare("INSERT INTO settings (key, value) VALUES ('joshy_releases', ?1) ON CONFLICT(key) DO UPDATE SET value = ?1")
      .bind(JSON.stringify(rel)).run();
    return json(200, { success: true, version: rel.version });
  }
  if (p === "/admin/licenses/merge" && request.method === "POST") {
    const { records = [] } = await request.json();
    const stmts = records.filter((r) => r && r.hwid && Number.isFinite(Number(r.first_run))).map((r) =>
      env.DB.prepare(
        `INSERT INTO joshy_licenses (hwid, first_run, last_seen, duration_days, app_version, remote_revoked, status)
         VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7)
         ON CONFLICT(hwid) DO UPDATE SET
           first_run = MIN(first_run, ?2),
           app_version = CASE WHEN ?3 > last_seen THEN ?5 ELSE app_version END,
           status = CASE WHEN ?3 > last_seen THEN ?7 ELSE status END,
           last_seen = MAX(last_seen, ?3),
           duration_days = ?4,
           remote_revoked = ?6`,
      ).bind(String(r.hwid), Number(r.first_run), Number(r.last_seen || r.first_run),
             Number(r.duration_days || 14), r.app_version ?? null, r.remote_revoked ? 1 : 0, r.status ?? null));
    for (let i = 0; i < stmts.length; i += 50) await env.DB.batch(stmts.slice(i, i + 50));
    return json(200, { success: true, merged: stmts.length });
  }
  return json(404, { success: false, error: "Not found" });
}

async function fallback(request, env, url, body) {
  if (!env.FALLBACK_URL) throw new Error("no fallback");
  const h = new Headers(request.headers);
  h.delete("host");
  return fetch(new URL(url.pathname + url.search, env.FALLBACK_URL),
    { method: request.method, headers: h, body, signal: AbortSignal.timeout(8000) });
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const p = url.pathname;
    if (p === "/" || p === "/health") return json(200, { service: "JOSHY API", ok: true });
    if (p.startsWith("/admin/")) return admin(request, env, url);
    const handler = p === "/api/audio_suite/handshake" ? handshake : p === "/api/audio_suite/feedback" ? feedback : null;
    if (!handler) return json(404, { success: false, error: "Not found" });

    const body = ["GET", "HEAD"].includes(request.method) ? null : await request.clone().arrayBuffer();
    try {
      return await handler(request, env);
    } catch (err) {
      try {
        const r = await fallback(request, env, url, body);
        return new Response(r.body, r);
      } catch {
        return json(503, { success: false, error: "License server temporarily unavailable" });
      }
    }
  },
};
