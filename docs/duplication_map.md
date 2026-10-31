# Duplication Map: DevCore ↔ e_profile

_Scope: agent integration (DevCore as a plugin of e_profile, and as a standalone component). Generated 2026-10-31. Excludes vendored libs (venv, Cryptodome), the `scripts/` cluster, and non-code `content/`._

## Architecture (confirmed)

One agent core, two adapters:

| Mode | Entry point | Framework | Wraps |
|---|---|---|---|
| Standalone | `DevCore/core/server.py` | Quart (async) | `agents/`, `core/`, `security/` |
| Plugin | `DevCore/ai_plugin.py` → exposes `ai_bp` | Flask Blueprint | same packages |

Host side is already centralized: `e_profile/content/projects/engines/antigravity_agent/{ai_plugin,main}.py`
are **forwarders** that locate DevCore via `DEVCORE_PATH → ../DevCore → ~/DevCore` and re-export. The agent
engine lives only in DevCore and is *mounted*, not copied.

## 1. Cross-repo shared files

| File | DevCore | e_profile | Verdict |
|---|---|---|---|
| `sensitivity_engine.py` | ✓ | ✓ | IDENTICAL → move to `shared/` |
| `audit_doc_structure.py` | ✓ | ✓ | IDENTICAL → move to `shared/` |
| `security_audit.py` | 10,613 b | 35,131 b | GENUINELY DRIFTED → reconcile, then `shared/` |
| `ai_plugin.py` | 44,732 b | 624 b | BY DESIGN — 624 b is the forwarder shim. Not drift. |
| `server.py` | Quart standalone | Flask host | BY DESIGN — two adapters, not a copy to merge. |

True `shared/` candidates: `sensitivity_engine`, `audit_doc_structure`, `security_audit` (after reconcile).

## 2. DevCore/core/backups/ — drift trap (primary target)

37 stale snapshots shadowing live modules by name. 17 have drifted. See
`docs/backups_drift.md` for the per-file report.

Severe divergence:
- `local_brain_broker.py` backup 26,222 b vs live 47,788 b (-45%)
- `security_audit.py` backup 29,657 b vs live 10,613 b (+179%)
- `ai_plugin.py` backup 35,566 b vs live 44,732 b (-21%)
- `generate_raugusmap.py` backup 14,543 b vs live 20,792 b (-30%)

## 3. Data-quality flags

- `security_audit.py` exists in ≥3 divergent versions (DevCore `security/` 10.6 KB, backup 29.7 KB,
  e_profile 35.1 KB). Reconcile by hand before giving it a single home.
- Multiple unrelated `server.py` files exist; canonical standalone = `DevCore/core/server.py`.

## 4. Recommended sequence

1. Reconcile + delete `core/backups/`; git-ignore it. (highest value)
2. Create `shared/` package; replace copies in both repos with re-export shims.
3. Factor the DevCore-locator snippet into one helper used by all 4 call sites.
