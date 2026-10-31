# Claude Brain — First-Time Setup

The Siraugga agent can use Claude as its brain. It **auto-detects** how to
connect, so you only set up once. No per-use configuration.

## How it chooses a backend (automatic)

On every call, `run_claude_model` picks the first available option:

1. **API key** — if `ANTHROPIC_API_KEY` (or `ANTHROPIC_AUTH_TOKEN`) is set, or an
   `ant auth login` profile exists → uses the billed Anthropic API.
2. **Your Claude subscription** — otherwise, drives the authenticated `claude`
   CLI (`claude -p`). Bring-your-own-subscription; no API key needed.
3. **Not set up** → returns a clear message telling you what to do.

## First-time setup (pick ONE)

### Option A — Bring your own subscription (recommended, personal use)
One interactive login, then it's automatic forever:
```bash
claude /login      # sign in with your Claude Pro/Max subscription
```
That's it. Select **"Claude Opus 5.5 (Cloud)"** in the model dropdown.

> Note: this uses your personal Claude Code session. It is intended for
> single-user / personal deployments, not for serving many portal visitors.

### Option B — API key (billed, good for multi-user)
Easiest: open **`/ai_agent/setup`** (admin only) and paste the key. It is stored
**encrypted** via DevCore's credential vault (`security/ai_credentials.json`,
AES-GCM keyed off `.devcore_master.key` — see
`security/README_ai_credentials.md`) and applied live, no restart. The key is
never written to disk in plaintext.

Alternatively, set `ANTHROPIC_API_KEY` in the environment (e.g. `e_profile/.env`),
which **overrides** the vault. The host loads env once at startup
(`config.py` → `load_dotenv`).

## Verify
```bash
curl http://localhost:<port>/ai_agent/api/ai/selftest
# ok:true + a short response  => working
# 503 + a [LOCAL_BRAIN_UNAVAILABLE] message => follow the message
```

## Dependencies
`anthropic>=0.69` and `python-dotenv>=1.0` (in `requirements.txt`) for the API
path; the `claude` CLI for the subscription path.
