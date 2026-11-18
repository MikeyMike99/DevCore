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

## Linux Essentials course integration
The course's hands-on steps (`linux_essentials_step_by_step`, 71 commands) run in the learner's own container instead of the
server's sandbox. Course content, predictions, reflections, progress and evidence files are unchanged; only *where the
command runs* changed (`core/lab_cloud.py`, called from `_execute_sandbox_sync` in `core/routes/projects.py`).
- **Off by default.** Turn on by setting `SIRAUGGA_LAB_URL` and `SIRAUGGA_LAB_SECRET` in the Siraugga server's environment
  (locally: `http://127.0.0.1:8788` and `local-dev-only`). If unset or unreachable, the course uses the old sandbox, so it never breaks.
- One container per learner (id = their private sandbox folder, unique even when two learners share a name).
  Their home folder persists between steps; `/tmp` is emptied before each command, exactly like the old sandbox.
- `python labcloud/test_course.py` runs all 71 course commands through the connector (71/71 pass).
- To route another course: add it to `COURSE_LABS` in `core/lab_cloud.py` and a folder under `image/labs/`.

## The permanent audit
`scripts/audit_labcloud.py` audits everything above in 7 stages (image, Worker/config, course connector, secrets/supply chain,
unit tests, live attack probes, tripwire) and logs every FAIL/WARN to `logs/security_violations.jsonl`.
```
python3 scripts/audit_labcloud.py                 # full audit (live stage skips if the stack is not running)
python3 scripts/audit_labcloud.py --no-live       # static + unit tests; what the pre-commit hook runs
python3 scripts/audit_labcloud.py --require-live  # FAIL if the stack is not up (use before a deploy)
python3 scripts/audit_labcloud.py --accept-integrity   # approve a deliberate change to a security-critical file
python3 scripts/audit_labcloud.py --install-hook  # (re)install the pre-commit trigger (git_bootstrap may overwrite hooks)
```
- **Where it runs automatically:** on every commit touching `labcloud/`, `core/lab_cloud.py` or the audit itself (pre-commit hook),
  and inside the normal test suite (`tests/test_audit_labcloud.py`).
- **It is tested too:** that test file breaks a copy of the system in 19 ways (unpinned image, no replay window, internet on,
  weak CSP, secret in the tree, ...) and requires the audit to catch each one, so the audit cannot quietly go blind.
- **Tripwire:** security-critical files are hashed in `labcloud/audit_baseline.json`. After you review a deliberate change,
  run `--accept-integrity` and commit the new baseline. Line endings do not matter.
- **Before going live:** run with the stack up and `--require-live`; then check on Cloudflare the two things local dev cannot
  show (`enableInternet = false`, `max_instances`).

## Add a lab
Make `image/labs/<lab-id>/` with `lab.json` (title, steps, hints), `seed/` (files the learner starts with) and
`checks/<step>.sh` (exit 0 = pass; runs in the learner's home; read `$LAB/seed` for pristine copies). The folders under
`/labs` are root-only in the image, so learners cannot read the checks. Then restart `dev.sh`.

## Safety built in
- Learner runs as a non-root user, no outbound internet (`enableInternet = false`), file-size/open-file limits.
- Containers sleep after 10 idle minutes; `max_instances` (5 now) caps live lab computers on Cloudflare.
- Signed, expiring links; per-learner keys; lab and step names validated; answers are root-only.
- Replay window (5 min), per-learner rate limits (check 30/min, run 120/min, session 20/min), request size limits.

## Known limits
- `max_instances` and `enableInternet = false` are enforced by Cloudflare, **not in local dev** (7 sessions were accepted
  and a container could reach the internet). Check both on the first real deploy.
- Not deployed. Going live needs the Workers Paid plan, a route (e.g. `lab.mikeytech.dev`), `LAB_MASTER_SECRET` as a Worker
  secret, and the `lab_progress` table (`lab_schema.sql`) applied to D1. Then `npx wrangler deploy --config wrangler.jsonc`.
- Containers are per learner+lab, so a learner's files persist only while the container lives (10 idle minutes).
- Chat-page integration (calling `/lab/session` from the Siraugga backend) is not wired in yet.
