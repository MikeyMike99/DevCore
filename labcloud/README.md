# Siraugga Lab Cloud

Real Linux labs for learners, with **nothing to install**. Each learner gets their own Debian container (started on demand,
shut down when idle), a web terminal, and **server-side grading**. Runs on Cloudflare Containers; for now it runs **locally only**.

```
Siraugga chat page ──(iframe)──►  /app/<token>  ──►  Worker ──►  one container per learner+lab
   (backend signs /lab/session)      tasks + terminal            ├─ ttyd  (terminal, runs as non-root "learner")
                                     + Check buttons             └─ grader (root-only; answers never reach the learner)
```

## Run it locally (WSL, Docker running)
```
bash labcloud/dev.sh                 # starts the Worker + real containers on http://localhost:8788
python labcloud/test_local.py        # 15 end-to-end checks (use a second terminal)
```
Local only: no Cloudflare account, domain or secret is used. The dev secret `local-dev-only` is for this machine.

## How a lab session works
1. Siraugga's backend calls `POST /lab/session {"lab":"linux-basics-01"}`, signed with the learner's key
   (`key = HMAC-SHA256(LAB_MASTER_SECRET, learnerId)`, see `issue_key.py`). It gets back `{app, terminal, expires}`.
2. The learner's browser opens `app` (or the chat embeds it in an iframe). The link is signed and expires after 4 hours.
3. The learner works in the terminal. **Check** runs the step's check script inside the container as root; a pass is saved
   once per learner+lab+step in D1 (`lab_progress`).

## Add a lab
Make `image/labs/<lab-id>/` with `lab.json` (title, steps, hints), `seed/` (files the learner starts with) and
`checks/<step>.sh` (exit 0 = pass; runs in the learner's home; read `$LAB/seed` for pristine copies). The folders under
`/labs` are root-only in the image, so learners cannot read the checks. Then restart `dev.sh`.

## Safety built in
- Learner runs as a non-root user, no outbound internet (`enableInternet = false`), file-size/open-file limits.
- Containers sleep after 10 idle minutes; `max_instances` (5 now) caps live lab computers on Cloudflare.
- Signed, expiring links; per-learner keys; lab and step names validated; answers are root-only.

## Known limits
- `max_instances` is enforced by Cloudflare, **not in local dev** (7 sessions were accepted locally).
- Not deployed. Going live needs the Workers Paid plan, a route (e.g. `lab.mikeytech.dev`), `LAB_MASTER_SECRET` as a Worker
  secret, and the `lab_progress` table (`lab_schema.sql`) applied to D1. Then `npx wrangler deploy --config wrangler.jsonc`.
- Containers are per learner+lab, so a learner's files persist only while the container lives (10 idle minutes).
- Chat-page integration (calling `/lab/session` from the Siraugga backend) is not wired in yet.
