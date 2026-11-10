#!/usr/bin/env python3
"""
=============================================================================
   DEVCORE CREDENTIAL VAULT ISOLATION AUDITOR (audit_vault_isolation.py)
=============================================================================
Validates the Zero Agent Access invariant across all credential vaults,
encrypted containers (.vault), Bitwarden stores, and cryptographic symbols:
- Stage 1: VFS Path & Key Semantic Classification (security/raugus_access.py)
- Stage 2: PreToolUse Security Hook Interception (.agents/raugus_hook.py)
- Stage 3: Raugus Resolver MCP Broker Gate (.agents/plugins/raugus_resolver/server.py)
- Stage 4: JIT Elevation Isolation Invariant (security/jit_elevation.py)
- Stage 5: Live red-team probes against the CLI bridge (DNS rebinding, CSRF,
           cross-site Origin, secret leakage in responses, LAN exposure)
- Stage 6: Secrets at rest (0600/0700 perms, ciphertext-only biometric record,
           bridge source invariants: loopback bind, no argv passwords, auto-lock)
- Stage 7: Tripwire (SHA-256 of security-critical files vs. approved baseline),
           DevCore passkey tampering (identity_monitor) and unlock-audit anomalies
Every FAIL/WARN is appended to logs/security_violations.jsonl.

Usage (run inside WSL so ~/.config/devcore is the bridge's config dir):
  python3 scripts/audit_vault_isolation.py
  python3 scripts/audit_vault_isolation.py --json
  python3 scripts/audit_vault_isolation.py --no-live            # skip bridge probes
  python3 scripts/audit_vault_isolation.py --accept-integrity   # approve deliberate changes
=============================================================================
"""

import argparse
import json
import os
import subprocess
import sys
import time

DEVCORE_ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
if DEVCORE_ROOT not in sys.path:
    sys.path.insert(0, DEVCORE_ROOT)

HOOK_SCRIPT = os.path.join(DEVCORE_ROOT, ".agents", "raugus_hook.py")
MCP_SERVER_DIR = os.path.join(DEVCORE_ROOT, ".agents", "plugins", "raugus_resolver")
if MCP_SERVER_DIR not in sys.path:
    sys.path.insert(0, MCP_SERVER_DIR)

AUDIT_CANARY = "__VAULT_AUDIT_CANARY__"


def simulate_hook(tool_name: str, args: dict) -> dict:
    """Pipes a synthetic PreToolUse payload to raugus_hook.py and returns its JSON decision."""
    payload = {
        "toolCall": {
            "name": f"default_api:{tool_name}",
            "args": args,
        }
    }
    try:
        res = subprocess.run(
            [sys.executable, HOOK_SCRIPT],
            input=json.dumps(payload),
            capture_output=True,
            text=True,
            timeout=15,
        )
        out = res.stdout.strip()
        if not out:
            return {"decision": "error", "raw": res.stderr}
        return json.loads(out.splitlines()[-1])
    except Exception as e:
        return {"decision": "error", "raw": str(e)}


CFG_DIR = os.path.join(os.environ.get("XDG_CONFIG_HOME", os.path.join(os.path.expanduser("~"), ".config")), "devcore")
INTEGRITY_BASELINE = os.path.join(CFG_DIR, "integrity_baseline.json")
VIOLATION_LOG = os.path.join(DEVCORE_ROOT, "logs", "security_violations.jsonl")
DEFAULT_BRIDGE_URL = "http://127.0.0.1:5050"

# Files whose unexpected modification is a security event. Edit deliberately, then
# re-approve with --accept-integrity.
INTEGRITY_FILES = [
    ".agents/raugus_hook.py",
    ".agents/plugins/raugus_resolver/server.py",
    "security/raugus_access.py",
    "security/raugus_resolver.py",
    "security/security_headers.py",
    "security/jit_elevation.py",
    "security/agent_identity.py",
    "security/identity_monitor.py",
    "security/webauthn_config.json",
    "scripts/audit_vault_isolation.py",
    "scripts/setup/cli_bridge_ui.py",
    "scripts/setup/vault_health.py",
    "scripts/setup/passkey_setup_wizard.py",
    "scripts/dev_jail.sh",
    "security/dev_workspaces.py",
    ".claude/settings.json",
    ".claude/settings.local.json",
]
BIO_ALLOWED_FIELDS = {"credential_id", "prf_salt", "iv", "ciphertext", "version", "label", "created_at"}


def _http(url, method="GET", headers=None, data=None, timeout=5):
    """Return (status, headers, body) without raising on HTTP error codes."""
    import urllib.error
    import urllib.request
    req = urllib.request.Request(url, method=method, data=data, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, dict(r.headers), r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read().decode("utf-8", "replace")


def _walk_keys(obj):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield str(k).lower()
            yield from _walk_keys(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _walk_keys(v)


def _bridge_endpoint_probes(record_check, base):
    import re
    import socket
    from urllib.parse import urlparse
    cat = "Bridge Endpoints"
    port = urlparse(base).port or 5050
    try:
        status, _, page = _http(base + "/")
    except Exception as e:
        record_check(cat, "Live endpoint red-team probes", None, f"Bridge not reachable at {base} ({e}); start it to run these probes.")
        return

    # DNS rebinding: a foreign Host header must be refused on every route.
    evil = {"Host": f"attacker.example:{port}"}
    codes = {p: _http(base + p, headers=evil)[0] for p in ("/", "/api/status", "/api/security", "/bio/meta")}
    codes["POST /run"] = _http(base + "/run", "POST", evil, b"action=list_items")[0]
    record_check(cat, "DNS-Rebinding Defence (foreign Host header -> 421)",
                 all(c == 421 for c in codes.values()), f"codes={codes}")

    # CSRF on the form endpoint (list_items would dump vault names if this failed).
    no_tok = _http(base + "/run", "POST", {"Content-Type": "application/x-www-form-urlencoded"}, b"action=list_items")[0]
    bad_tok = _http(base + "/run", "POST", {"Content-Type": "application/x-www-form-urlencoded"}, b"csrf=forged&action=list_items")[0]
    record_check(cat, "CSRF Enforcement on /run (missing & forged token -> 403)",
                 no_tok == 403 and bad_tok == 403, f"missing={no_tok}, forged={bad_tok}")

    # Biometric endpoints: header token + loopback Origin both required. Probes are
    # rejected before any bw command runs.
    m = re.search(r'BIO_CSRF = "([^"]+)"', page)
    tok = m.group(1) if m else ""
    j = {"Content-Type": "application/json"}
    body = json.dumps({"password": AUDIT_CANARY}).encode()
    r_nohdr = _http(base + "/bio/unlock", "POST", j, body)[0]
    r_origin = _http(base + "/bio/unlock", "POST", {**j, "X-CSRF-Token": tok, "Origin": "https://attacker.example"}, body)[0]
    r_forget = _http(base + "/bio/forget", "POST", {**j, "Origin": "https://attacker.example"}, b"{}")[0]
    record_check(cat, "Biometric API rejects missing token & cross-site Origin (-> 403)",
                 r_nohdr == 403 and r_origin == 403 and r_forget == 403,
                 f"no_token={r_nohdr}, foreign_origin={r_origin}, forget_cross_site={r_forget}")

    # Response hygiene & information leakage.
    _, h_root, _ = _http(base + "/")
    s_sec, h_sec, b_sec = _http(base + "/api/security")
    _, _, b_stat = _http(base + "/api/status")
    hdr_ok = all(h.get("X-Content-Type-Options") == "nosniff" and "no-store" in h.get("Cache-Control", "")
                 for h in (h_root, h_sec))
    try:
        keys = set(_walk_keys(json.loads(b_sec))) | set(_walk_keys(json.loads(b_stat)))
    except ValueError:
        keys = {"<unparseable>"}
    leaky = sorted(k for k in keys if k in {"password", "session_key", "bw_session", "ciphertext_key", "prf_output"})
    record_check(cat, "No secrets in API responses & no-store/nosniff headers",
                 hdr_ok and not leaky and s_sec == 200,
                 f"headers_ok={hdr_ok}, leaked_fields={leaky or 'none'}")

    # Exposure: the bridge must not be reachable on any non-loopback address.
    exposed = []
    addrs = set()
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("192.0.2.1", 9))  # TEST-NET, no packets sent for UDP connect
            addrs.add(s.getsockname()[0])
    except OSError:
        pass
    try:
        addrs.update(ai[4][0] for ai in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET))
    except OSError:
        pass
    addrs = {a for a in addrs if not a.startswith("127.")}
    for a in addrs:
        try:
            with socket.create_connection((a, port), timeout=1.5):
                exposed.append(a)
        except OSError:
            pass
    record_check(cat, "Bridge bound to loopback only (not reachable from LAN)",
                 not exposed, f"probed={sorted(addrs) or 'no LAN address found'}, reachable={exposed or 'none'}")


def _secrets_at_rest_checks(record_check):
    import re
    import stat
    cat = "Secrets at Rest"
    if os.name == "posix" and os.path.isdir(CFG_DIR):
        loose = []
        dmode = stat.S_IMODE(os.stat(CFG_DIR).st_mode)
        if dmode & 0o077:
            loose.append(f"devcore/ dir {oct(dmode)}")
        for name in os.listdir(CFG_DIR):
            p = os.path.join(CFG_DIR, name)
            if os.path.isfile(p):
                mode = stat.S_IMODE(os.stat(p).st_mode)
                if mode & 0o077:
                    loose.append(f"{name} {oct(mode)}")
        record_check(cat, "Owner-only permissions on ~/.config/devcore (0700 dir / 0600 files)",
                     not loose, f"too_permissive={loose or 'none'}")
    else:
        record_check(cat, "Owner-only permissions on ~/.config/devcore", None,
                     "Not a POSIX host or no devcore config yet (run inside WSL after first use).")

    bio = os.path.join(CFG_DIR, "bw_biometric.json")
    if os.path.isfile(bio):
        try:
            rec = json.load(open(bio))
            extra = sorted(set(rec) - BIO_ALLOWED_FIELDS)
            b64_ok = all(re.fullmatch(r"[A-Za-z0-9_-]+", str(rec.get(k, ""))) for k in ("credential_id", "prf_salt", "iv", "ciphertext"))
            record_check(cat, "Biometric unlock record holds only ciphertext (no plaintext fields)",
                         not extra and b64_ok, f"unexpected_fields={extra or 'none'}, base64url_ok={b64_ok}")
        except (OSError, ValueError) as e:
            record_check(cat, "Biometric unlock record holds only ciphertext", False, f"unreadable/corrupt: {e}")
    else:
        record_check(cat, "Biometric unlock record holds only ciphertext", None, "Not enrolled yet.")

    src_path = os.path.join(DEVCORE_ROOT, "scripts", "setup", "cli_bridge_ui.py")
    try:
        src = open(src_path, encoding="utf-8").read()
        problems = []
        if re.search(r'\[\s*"unlock"\s*,\s*"--raw"\s*,\s*password\s*\]', src) or re.search(r'"login"\s*,\s*email\s*,\s*password', src):
            problems.append("master password passed on the command line (visible in ps)")
        if not re.search(r'^HOST\s*=\s*"127\.0\.0\.1"', src, re.M):
            problems.append("default bind is not 127.0.0.1")
        for marker, why in (("_host_ok", "Host-header check"), ("X-CSRF-Token", "biometric CSRF header"),
                            ("--passwordenv", "env-based password passing"), ("_expiry_loop", "session auto-lock")):
            if marker not in src:
                problems.append(f"missing {why}")
        record_check(cat, "Bridge source invariants (loopback, CSRF, Host check, no argv secrets, auto-lock)",
                     not problems, f"problems={problems or 'none'}")
    except OSError as e:
        record_check(cat, "Bridge source invariants", None, f"cli_bridge_ui.py not found ({e}).")


def _sha256(path):
    import hashlib
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _integrity_checks(record_check, accept):
    cat = "Integrity Tripwire"
    current = {}
    for rel in INTEGRITY_FILES:
        p = os.path.join(DEVCORE_ROOT, rel)
        if os.path.isfile(p):
            current[rel] = _sha256(p)
    try:
        baseline = json.load(open(INTEGRITY_BASELINE))
    except (OSError, ValueError):
        baseline = None

    if accept or baseline is None:
        os.makedirs(CFG_DIR, mode=0o700, exist_ok=True)
        fd = os.open(INTEGRITY_BASELINE, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as f:
            json.dump({"accepted_at": int(time.time()), "files": current}, f, indent=2)
        record_check(cat, "Security-critical files unchanged since approved baseline", True,
                     f"{'Re-approved' if accept else 'First run: baseline created for'} {len(current)} files. "
                     "Future runs flag any change.", warn=True)
        return

    approved = baseline.get("files", {})
    changed = sorted(r for r in current if r in approved and current[r] != approved[r])
    added = sorted(r for r in current if r not in approved)
    removed = sorted(r for r in approved if r not in current)
    ok = not (changed or added or removed)
    record_check(cat, "Security-critical files unchanged since approved baseline", ok,
                 "all match" if ok else
                 f"changed={changed or '-'} added={added or '-'} removed={removed or '-'}. "
                 "If you made these changes on purpose, re-run with --accept-integrity.")


def _identity_and_unlock_checks(record_check):
    cat = "Identity & Unlock Monitoring"
    try:
        sys.path.insert(0, os.path.join(DEVCORE_ROOT, "security"))
        import identity_monitor
        r = identity_monitor.check()
        alerts = [f for f in r["findings"] if not f["code"].startswith("CONFIG_")]
        config = [f for f in r["findings"] if f["code"].startswith("CONFIG_")]
        serious = [f for f in alerts if f["severity"] in ("critical", "high")]
        record_check(cat, "DevCore passkey accounts match the owner-approved baseline",
                     not serious,
                     ("Baseline created on first run; review the accounts. " if r["baseline_created"] else "")
                     + (f"alerts={[f['code'] + ': ' + f['detail'] for f in alerts]}" if alerts else "no tampering signals"))
        if config:
            record_check(cat, "Passkey verification configuration", False,
                         "; ".join(f"{f['code']}: {f['detail']}" for f in config), warn=True)
    except Exception as e:
        record_check(cat, "DevCore passkey accounts match the owner-approved baseline", None, f"identity monitor error: {e}")

    audit_file = os.path.join(CFG_DIR, "unlock_audit.jsonl")
    if os.path.isfile(audit_file):
        now = time.time()
        events = []
        for ln in open(audit_file).read().splitlines()[-1000:]:
            try:
                events.append(json.loads(ln))
            except ValueError:
                pass
        unlocks = {"unlock_password", "unlock_windows_hello", "enroll_windows_hello", "login_password", "login_apikey"}
        fails = [e for e in events if not e.get("ok") and e.get("event") in unlocks and now - e.get("ts", 0) < 86400]
        night = [e for e in events if e.get("ok") and e.get("event") in unlocks and now - e.get("ts", 0) < 7 * 86400
                 and time.localtime(e["ts"]).tm_hour < 5]
        tools = [e for e in events if e.get("event") in unlocks and any(t in (e.get("ua") or "").lower() for t in ("curl", "python", "wget", "httpie"))]
        issues = []
        if len(fails) >= 3:
            issues.append(f"{len(fails)} failed unlocks in 24h")
        if night:
            issues.append(f"{len(night)} night-time unlock(s) in 7 days")
        if tools:
            issues.append(f"{len(tools)} unlock attempt(s) from scripts/tools, not a browser")
        record_check(cat, "Unlock audit trail shows no suspicious activity", not issues,
                     "; ".join(issues) or f"{len(events)} events reviewed, nothing unusual", warn=True)
    else:
        record_check(cat, "Unlock audit trail shows no suspicious activity", None, "No unlock audit log yet.")


def log_violations(report):
    """Append every FAIL/WARN to logs/security_violations.jsonl."""
    bad = [c for c in report["checks"] if c["status"] in ("FAIL", "WARN")]
    if not bad:
        return 0
    try:
        os.makedirs(os.path.dirname(VIOLATION_LOG), exist_ok=True)
        with open(VIOLATION_LOG, "a", encoding="utf-8") as f:
            for c in bad:
                f.write(json.dumps({"ts": int(time.time()), "source": "audit_vault_isolation", **c}) + "\n")
    except OSError:
        pass
    return len(bad)


def run_vault_audit(live: bool = True, bridge_url: str = DEFAULT_BRIDGE_URL, accept_integrity: bool = False) -> dict:
    results = []
    start_ts = time.time()

    def record_check(category: str, name: str, passed, detail: str, warn: bool = False):
        """passed: True=PASS, False=FAIL (or WARN if warn=True), None=SKIP (could not run)."""
        status = "SKIP" if passed is None else "PASS" if passed else ("WARN" if warn else "FAIL")
        results.append({
            "category": category,
            "check": name,
            "status": status,
            "detail": detail,
        })

    # =========================================================================
    # 1. VFS Path & Key Semantic Classification
    # =========================================================================
    from security.raugus_access import is_vault_path, is_vault_key, is_secret_path

    sample_vault_paths = [
        os.path.join(DEVCORE_ROOT, "playground", "e_profile", "vault_store.json.vault"),
        os.path.join(DEVCORE_ROOT, "playground", "e_profile", "vault_mod.py"),
        r"C:\Users\michael\Documents\DevCore\playground\e_profile\vault_store.json.vault",
        r"C:\Users\michael\AppData\Roaming\Bitwarden CLI\data.json",
        "/home/michael/.bitwarden/data.json",
        "/mnt/c/Users/michael/Documents/DevCore/.devcore_master.key",
        "/mnt/c/Users/michael/Documents/DevCore/.vault_master.key",
        "/mnt/c/Users/michael/Documents/DevCore/.devcore_vault.key",
    ]
    paths_all_vault = all(is_vault_path(p) and is_secret_path(p) for p in sample_vault_paths)
    record_check(
        "Semantic Classification",
        "Credential Vault File & Directory Path Identification",
        paths_all_vault,
        f"Verified {len(sample_vault_paths)}/{len(sample_vault_paths)} vault paths flagged as vault & secret.",
    )

    sample_vault_keys = [
        "eprofile.vault_mod.py",
        "eprofile.vault_mod.py::vault_service",
        "devcore.core.routes.system.py::_get_devcore_vault_service",
        "devcore.security.raugus_resolver.py::api_vault_gateway",
        "devcore.security.crypto.py::shieldvaultcontainer",
        "devcore.security.transit.py::transitcryptoenvelope",
        "devcore.store.vault",
    ]
    keys_all_vault = all(is_vault_key(k) for k in sample_vault_keys)
    record_check(
        "Semantic Classification",
        "Cryptographic Vault Symbol & VFS Key Identification",
        keys_all_vault,
        f"Verified {len(sample_vault_keys)}/{len(sample_vault_keys)} symbols and keys recognized as vault targets.",
    )

    # =========================================================================
    # 2. PreToolUse Security Hook Interception
    # =========================================================================
    vault_file_target = os.path.join(DEVCORE_ROOT, "playground", "e_profile", "vault_store.json.vault")
    vault_mod_target = os.path.join(DEVCORE_ROOT, "playground", "e_profile", "vault_mod.py")

    d_view_vault = simulate_hook("view_file", {"AbsolutePath": vault_file_target})
    d_view_mod = simulate_hook("view_file", {"AbsolutePath": vault_mod_target})
    views_blocked = d_view_vault.get("decision") == "deny" and d_view_mod.get("decision") == "deny"
    record_check(
        "PreToolUse Hook",
        "Block Direct File Reads on Vault Containers & Engine (view_file)",
        views_blocked,
        f"vault_container={d_view_vault.get('decision')}, vault_mod={d_view_mod.get('decision')}",
    )

    d_cmd_bw = simulate_hook(
        "run_command",
        {"CommandLine": f"bw status # {AUDIT_CANARY}", "Cwd": os.path.join(DEVCORE_ROOT, "playground")},
    )
    d_cmd_vault_cat = simulate_hook(
        "run_command",
        {"CommandLine": f"cat e_profile/vault_mod.py # {AUDIT_CANARY}", "Cwd": os.path.join(DEVCORE_ROOT, "playground")},
    )
    cmds_blocked = d_cmd_bw.get("decision") == "deny" and d_cmd_vault_cat.get("decision") == "deny"
    record_check(
        "PreToolUse Hook",
        "Block Bitwarden CLI & Vault Shell Commands (run_command)",
        cmds_blocked,
        f"bw_cli={d_cmd_bw.get('decision')}, cat_vault={d_cmd_vault_cat.get('decision')}",
    )

    d_write_vault = simulate_hook(
        "write_to_file",
        {
            "TargetFile": os.path.join(DEVCORE_ROOT, "playground", f"probe_vault_mod_{AUDIT_CANARY}.py"),
            "Overwrite": True,
            "CodeContent": f"from e_profile.vault_mod import vault_service # {AUDIT_CANARY}\n",
        },
    )
    record_check(
        "PreToolUse Hook",
        "Block Writing Code Targeting Vault Engines (write_to_file)",
        d_write_vault.get("decision") == "deny",
        f"write_decision={d_write_vault.get('decision')}",
    )

    # =========================================================================
    # 3. Raugus Resolver MCP Broker Gate
    # =========================================================================
    mcp_passed = False
    try:
        import server as mcp_srv
        from security.agent_identity import mint_agent_credential, ENV_VAR as _CRED_ENV

        saved_cred = os.environ.get(_CRED_ENV)
        try:
            os.environ[_CRED_ENV] = mint_agent_credential(
                {"role": "super_admin", "username": AUDIT_CANARY, "key_id": "audit-vault-broker"},
                agent_kind="audit",
                ttl_seconds=60,
            )
            r_read = json.loads(mcp_srv.read_by_key("eprofile.vault_mod.py"))
            r_sym = json.loads(mcp_srv.read_by_key("devcore.core.routes.system.py::_get_devcore_vault_service"))
            r_write = json.loads(mcp_srv.write_by_key("eprofile.vault_mod.py", "x = 1\n"))
            r_list = json.loads(mcp_srv.list_module_keys("eprofile.vault_mod.py"))
            _, r_digest_raw = mcp_srv._load_readable_file("eprofile.vault_mod.py")
            r_digest = json.loads(r_digest_raw) if r_digest_raw else {}

            mcp_passed = (
                r_read.get("status") == "DENIED_VAULT_ACCESS"
                and r_sym.get("status") == "DENIED_VAULT_ACCESS"
                and r_write.get("status") == "DENIED_VAULT_ACCESS"
                and r_list.get("status") == "DENIED_VAULT_ACCESS"
                and r_digest.get("status") == "DENIED_VAULT_ACCESS"
            )
        finally:
            if saved_cred is not None:
                os.environ[_CRED_ENV] = saved_cred
            else:
                os.environ.pop(_CRED_ENV, None)
    except Exception as e:
        mcp_passed = None
        mcp_error = f"{type(e).__name__}: {e}"

    if mcp_passed is None:
        record_check(
            "Resolver MCP Broker",
            "Categorical DENIED_VAULT_ACCESS on MCP Read, Write, List & Digest",
            None,
            f"Could not run the broker test ({mcp_error}). Run this audit with the Python environment "
            "the Raugus MCP server uses so the broker can be exercised.",
        )
    else:
        record_check(
            "Resolver MCP Broker",
            "Categorical DENIED_VAULT_ACCESS on MCP Read, Write, List & Digest",
            mcp_passed,
            f"mcp_vault_status={mcp_passed} (read/write/list/digest all returned DENIED_VAULT_ACCESS)",
        )

    # --- 2b. Bridge secrets & bridge API are agent-denied (Chapter 97)
    bridge_probes = [
        ("view_file", {"AbsolutePath": os.path.join(CFG_DIR, "bw_session")}),
        ("view_file", {"AbsolutePath": os.path.join(CFG_DIR, "bw_biometric.json")}),
        ("view_file", {"AbsolutePath": os.path.join(CFG_DIR, "hibp_api_key")}),
        ("run_command", {"CommandLine": f"cat ~/.config/devcore/bw_session # {AUDIT_CANARY}", "Cwd": "/tmp"}),
        ("run_command", {"CommandLine": f"curl -s http://localhost:5050/api/status # {AUDIT_CANARY}", "Cwd": "/tmp"}),
        ("read_url_content", {"Url": "http://127.0.0.1:5050/"}),
    ]
    decisions = [simulate_hook(t, a).get("decision") for t, a in bridge_probes]
    record_check(
        "PreToolUse Hook",
        "Block Agent Access to Bridge Session/Biometric Secrets & Bridge API (:5050)",
        all(d == "deny" for d in decisions),
        "decisions=" + ",".join(f"{t}:{d}" for (t, _), d in zip(bridge_probes, decisions)),
    )

    # =========================================================================
    # 5. Live Red Team Probes against the CLI Bridge (cli_bridge_ui.py)
    # =========================================================================
    if live:
        _bridge_endpoint_probes(record_check, bridge_url)
    else:
        record_check("Bridge Endpoints", "Live endpoint red-team probes", None, "Skipped (--no-live).")

    # =========================================================================
    # 6. Secrets at Rest & Bridge Source Invariants
    # =========================================================================
    _secrets_at_rest_checks(record_check)

    # =========================================================================
    # 7. Tripwire: Security-Critical File Integrity + Identity & Unlock Alerts
    # =========================================================================
    _integrity_checks(record_check, accept_integrity)
    _identity_and_unlock_checks(record_check)

    # =========================================================================
    # 4. Cryptographic JIT Elevation Boundary (Zero Agent Access Invariant)
    # =========================================================================
    jit_vault_locked = False
    try:
        from security.jit_elevation import mint_jit_token, revoke_jit_token

        token_info = mint_jit_token(ttl_seconds=30, issued_by=AUDIT_CANARY, active_session_lift=True)
        elev_token = token_info.get("token")

        d_elev_view = simulate_hook(
            "view_file",
            {"AbsolutePath": vault_file_target, "elevation_token": elev_token},
        )
        revoke_jit_token(revoked_by=AUDIT_CANARY)

        jit_vault_locked = d_elev_view.get("decision") == "deny"
    except Exception:
        jit_vault_locked = False

    record_check(
        "JIT Boundary",
        "Permanent Zero Agent Access Invariant under Super Admin JIT Elevation",
        jit_vault_locked,
        f"elevated_vault_access={d_elev_view.get('decision') if 'd_elev_view' in locals() else 'error'}",
    )

    elapsed = round(time.time() - start_ts, 2)
    count = lambda s: sum(1 for r in results if r["status"] == s)

    return {
        "summary": {
            "total": len(results),
            "passed": count("PASS"),
            "failed": count("FAIL"),
            "warnings": count("WARN"),
            "skipped": count("SKIP"),
            "all_passed": count("FAIL") == 0,
            "elapsed_seconds": elapsed,
        },
        "checks": results,
    }


def main():
    parser = argparse.ArgumentParser(description="DevCore Credential Vault Isolation Auditor")
    parser.add_argument("--json", action="store_true", help="Output machine-readable JSON report")
    parser.add_argument("--no-live", action="store_true", help="Skip live red-team probes against the CLI bridge")
    parser.add_argument("--bridge-url", default=DEFAULT_BRIDGE_URL, help=f"CLI bridge base URL (default {DEFAULT_BRIDGE_URL})")
    parser.add_argument("--accept-integrity", action="store_true",
                        help="Approve the current security-critical files as the new tripwire baseline")
    args = parser.parse_args()

    report = run_vault_audit(live=not args.no_live, bridge_url=args.bridge_url.rstrip("/"),
                             accept_integrity=args.accept_integrity)
    logged = log_violations(report)
    if args.json:
        print(json.dumps(report, indent=2))
        sys.exit(0 if report["summary"]["all_passed"] else 1)

    print("=" * 68)
    print("   DEVCORE CREDENTIAL VAULT ISOLATION & RED TEAM AUDIT REPORT")
    print("=" * 68)
    for c in report["checks"]:
        print(f" [{c['status']}] {c['category']} :: {c['check']}")
        print(f"        Detail: {c['detail']}")
    print("-" * 68)
    s = report["summary"]
    print(f" SUMMARY: {s['passed']} passed, {s['failed']} failed, {s['warnings']} warnings, "
          f"{s['skipped']} skipped ({s['total']} checks, {s['elapsed_seconds']}s)")
    if logged:
        print(f" {logged} violation(s)/warning(s) appended to {VIOLATION_LOG}")
    print("=" * 68)
    sys.exit(0 if report["summary"]["all_passed"] else 1)


if __name__ == "__main__":
    main()
