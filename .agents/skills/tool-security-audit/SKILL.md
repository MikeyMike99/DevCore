---
name: tool-security-audit
description: >-
  Executes the 5-Stage Workspace Tool Security Audit against DevCore tools,
  plugins, skills, and the Raugus Sensitive Vault. Verifies RBAC tiers,
  PreToolUse hook interceptions, AST static code hygiene, DLP canary scrubbing,
  and SIEM/MAQ logging.
---

# Workspace Tool Security Audit Skill

## Overview
Use this skill whenever the user asks you to run a security audit against workspace tools, skills, plugins (such as the Exam Application or Local Brain Broker), or types `/audit`.

## Workflow

### 1. Execute the Automated 5-Stage Auditor
Run the standalone auditor script via `run_command`:
```bash
python3 /mnt/c/Users/michael/Documents/DevCore/security/tool_security_auditor.py --target all
```
*(If the user specifies a particular script or plugin path, pass `--target <path>`).*

### 2. What the 6 Stages Verify (27 Automated Checks)
1. **Stage 1 — Raugus Map, OneDrive Discovery & RBAC Tier Verification**: Checks `security/raugus_map.json` and `RaugusResolver` to verify `"sensitive": true` vault locks, automatic OneDrive sync-root detection (`discover_onedrive_roots()` regardless of folder name via `.849C9593-D756-4E56-8D6E-42412F2A707B` and `desktop.ini`), read-only UI blueprints, and Tier 3 vs. Tier 5 access boundaries.
2. **Stage 2 — PreToolUse Hook & Bypass Simulation**: Pipes synthetic payloads into `.agents/raugus_hook.py` to test blocks on `view_file`, `grep_search`, `list_dir`, raw `run_command`, Windows/WSL OneDrive paths, shell-chaining (`;`), and Rule 8 markdown feedback loops, while confirming clean `local_brain_broker.py` calls are allowed.
3. **Stage 3 — AST Static Code & Subprocess Hygiene Scan**: Parses tool Python files via `ast` to guarantee zero external cloud HTTP imports in offline vault scripts, no `shell=True` subprocess calls, and no `eval()`/`exec()`.
4. **Stage 4 — POPIA DLP & Anti-Exfiltration Canary Testing**: Passes 10 synthetic PII/secret canaries (South African 13-digit ID numbers, `+27` cellphone numbers, landline numbers, physical street addresses, student numbers, `AIzaSy...`, `sk-...`, emails, IPs, passwords), verbatim extraction queries, and >60-char source lines through `security/local_brain_broker.py` to verify 100% offline redaction and blocking.
5. **Stage 5 — Anti-Tamper, 64-Bit Inode Fingerprinting & Script Evasion**: Verifies self-protection locks on `.agents/raugus_hook.py` and broker files, wildcard glob & relative-path folder rename blocks (`mv con*`), string-splitting (`'One'+'Drive'`) & `base64 -d | bash` decode blocks, two-step sneaky script write blocks, and 64-bit hardware inode (`st_ino`) anti-rename fingerprinting.
6. **Stage 6 — SIEM & Master Alert Queue Verification**: Confirms all simulated violations are logged to `logs/devcore_master.jsonl` (`SECURITY_AUDIT`) and `logs/master_alert_queue.jsonl` (`NGPF_INTRUSION`), then automatically purges synthetic canary entries to keep production logs clean.

### 3. Present the Audit Scorecard
Format the JSON results into a concise, screen-reader-friendly summary grouped by stage (`PASS` / `FAIL`) with clickable `file://` links to all audited modules.


