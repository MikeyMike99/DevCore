#!/usr/bin/env python3
"""
DevCore Identity Monitor — detect tampering with DevCore's own WebAuthn accounts.

Compares security/webauthn_credentials.json against an owner-accepted baseline
(kept outside the repo in ~/.config/devcore/identity_baseline.json) and flags:

  NEW_ACCOUNT       an account with passkeys that the owner never approved
  NEW_PASSKEY       a passkey added to an existing account
  REMOVED_PASSKEY   an approved passkey disappeared
  KEY_SWAPPED       same credential ID, different public key (direct file tampering)
  COUNTER_ROLLBACK  sign counter went backwards since last check (file restored or a
                    cloned authenticator was used to overwrite state)
  ODD_HOUR_USE      a passkey was used between 00:00 and 05:00 local time
  CONFIG_*          static weaknesses in the passkey verification code

Usage:
  python3 security/identity_monitor.py            # check, print report
  python3 security/identity_monitor.py --accept   # approve current state as the new baseline
  python3 security/identity_monitor.py --json
"""

import argparse
import hashlib
import json
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CREDS_FILE = REPO_ROOT / "security" / "webauthn_credentials.json"
CONFIG_FILE = REPO_ROOT / "security" / "webauthn_config.json"
WIZARD_FILE = REPO_ROOT / "scripts" / "setup" / "passkey_setup_wizard.py"
ALERT_LOG = REPO_ROOT / "logs" / "identity_alerts.jsonl"
CFG_DIR = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "devcore"
BASELINE_FILE = CFG_DIR / "identity_baseline.json"
ODD_HOURS = range(0, 5)

SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}


def _write_private(path, text):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        os.chmod(path.parent, 0o700)
    except OSError:
        pass
    fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(text)


def _fmt_ts(ts):
    try:
        return datetime.fromtimestamp(int(ts)).strftime("%Y-%m-%d %H:%M")
    except (TypeError, ValueError, OSError):
        return "unknown"


def load_current(creds_file=CREDS_FILE):
    """Flatten the credential store to {credential_id: record}."""
    data = json.loads(Path(creds_file).read_text())
    out = {}
    for uname, urec in (data.get("users") or {}).items():
        for c in urec.get("credentials", []) or []:
            cid = c.get("credential_id")
            if not cid:
                continue
            out[cid] = {
                "user": uname,
                "label": c.get("device_label", "Passkey"),
                "aaguid": c.get("aaguid", ""),
                "pk_hash": hashlib.sha256(str(c.get("public_key", "")).encode()).hexdigest(),
                "sign_count": int(c.get("sign_count") or 0),
                "created_at": c.get("created_at"),
                "last_used_at": c.get("last_used_at"),
            }
    return out


def static_config_findings(wizard_file=WIZARD_FILE, config_file=CONFIG_FILE):
    findings = []
    try:
        src = Path(wizard_file).read_text(encoding="utf-8")
        if re.search(r"expected_origin\s*=\s*self\.headers\.get\(\s*[\"']Origin", src):
            findings.append({
                "code": "CONFIG_ORIGIN_FROM_REQUEST", "severity": "medium",
                "detail": "passkey_setup_wizard.py checks WebAuthn responses against the request's own Origin header "
                          "instead of the allow-list in webauthn_config.json, which weakens phishing protection.",
            })
        if re.search(r"require_user_verification\s*=\s*False", src):
            findings.append({
                "code": "CONFIG_UV_NOT_REQUIRED", "severity": "medium",
                "detail": "Passkey sign-in does not require user verification (fingerprint/face/PIN), so a "
                          "passkey can be used with just a tap/presence check.",
            })
    except OSError:
        pass
    try:
        cfg = json.loads(Path(config_file).read_text())
        if cfg.get("user_verification") != "required":
            findings.append({
                "code": "CONFIG_UV_PREFERRED", "severity": "low",
                "detail": f"webauthn_config.json sets user_verification to '{cfg.get('user_verification')}' rather than 'required'.",
            })
    except (OSError, ValueError):
        pass
    return findings


def check(creds_file=CREDS_FILE, baseline_file=BASELINE_FILE, update_last_seen=True, now=None):
    now = now or time.time()
    current = load_current(creds_file)
    findings = []

    try:
        baseline = json.loads(Path(baseline_file).read_text())
    except (OSError, ValueError):
        baseline = None

    if baseline is None:
        accept(creds_file, baseline_file, current=current)
        return {
            "checked_at": int(now), "baseline_created": True,
            "accounts": sorted({c["user"] for c in current.values()}),
            "passkeys": len(current),
            "findings": static_config_findings(),
            "message": "First run: current accounts were saved as the trusted baseline. "
                       "Review them below; if anything is unfamiliar, investigate before trusting it.",
            "inventory": _inventory(current),
        }

    approved = baseline.get("creds", {})
    last_seen = baseline.get("last_seen", {})
    approved_users = {c["user"] for c in approved.values()}

    for cid, cur in current.items():
        ref = approved.get(cid)
        if ref is None:
            new_user = cur["user"] not in approved_users
            findings.append({
                "code": "NEW_ACCOUNT" if new_user else "NEW_PASSKEY", "severity": "high",
                "detail": (f"Unapproved account '{cur['user']}'" if new_user else f"New passkey on '{cur['user']}'")
                          + f" — device '{cur['label']}', created {_fmt_ts(cur['created_at'])}. "
                          "If you didn't add it, delete it and rotate access.",
            })
            continue
        if ref.get("pk_hash") != cur["pk_hash"]:
            findings.append({"code": "KEY_SWAPPED", "severity": "critical",
                             "detail": f"Passkey '{cur['label']}' on '{cur['user']}' kept its ID but its public key changed. "
                                       "This only happens if the credentials file was edited."})
        seen = last_seen.get(cid, {})
        if cur["sign_count"] < int(seen.get("sign_count", 0)):
            findings.append({"code": "COUNTER_ROLLBACK", "severity": "critical",
                             "detail": f"Sign counter for '{cur['label']}' on '{cur['user']}' went from "
                                       f"{seen.get('sign_count')} back to {cur['sign_count']}. The credentials file "
                                       "was restored or overwritten; a cloned passkey is possible."})
        lu = cur.get("last_used_at")
        if lu and lu != seen.get("last_used_at"):
            try:
                if datetime.fromtimestamp(int(lu)).hour in ODD_HOURS:
                    findings.append({"code": "ODD_HOUR_USE", "severity": "low",
                                     "detail": f"'{cur['label']}' on '{cur['user']}' was used at {_fmt_ts(lu)}. Was this you?"})
            except (ValueError, OSError):
                pass

    for cid, ref in approved.items():
        if cid not in current:
            findings.append({"code": "REMOVED_PASSKEY", "severity": "medium",
                             "detail": f"Approved passkey '{ref.get('label')}' on '{ref.get('user')}' is gone."})

    findings += static_config_findings()
    findings.sort(key=lambda f: SEVERITY_ORDER[f["severity"]])

    if update_last_seen:
        merged = {}
        for cid, cur in current.items():
            prev = last_seen.get(cid, {})
            merged[cid] = {"sign_count": max(cur["sign_count"], int(prev.get("sign_count", 0))),
                           "last_used_at": cur.get("last_used_at")}
        baseline["last_seen"] = merged
        baseline["last_checked_at"] = int(now)
        _write_private(Path(baseline_file), json.dumps(baseline, indent=2))

    alerts = [f for f in findings if not f["code"].startswith("CONFIG_")]
    if alerts:
        try:
            ALERT_LOG.parent.mkdir(parents=True, exist_ok=True)
            with open(ALERT_LOG, "a", encoding="utf-8") as f:
                for a in alerts:
                    f.write(json.dumps({"ts": int(now), **a}) + "\n")
        except OSError:
            pass

    return {
        "checked_at": int(now), "baseline_created": False,
        "baseline_accepted_at": baseline.get("accepted_at"),
        "accounts": sorted({c["user"] for c in current.values()}),
        "passkeys": len(current),
        "findings": findings,
        "message": "No signs of account tampering." if not alerts else f"{len(alerts)} identity alert(s) need review.",
        "inventory": _inventory(current),
    }


def _inventory(current):
    return [{"user": c["user"], "label": c["label"], "created": _fmt_ts(c["created_at"]),
             "last_used": _fmt_ts(c["last_used_at"]), "sign_count": c["sign_count"]}
            for c in sorted(current.values(), key=lambda c: (c["user"], c["label"]))]


def accept(creds_file=CREDS_FILE, baseline_file=BASELINE_FILE, current=None):
    current = current if current is not None else load_current(creds_file)
    baseline = {
        "accepted_at": int(time.time()),
        "creds": current,
        "last_seen": {cid: {"sign_count": c["sign_count"], "last_used_at": c["last_used_at"]} for cid, c in current.items()},
    }
    _write_private(Path(baseline_file), json.dumps(baseline, indent=2))
    return baseline


def format_report(r):
    lines = [f"DevCore identity check — {_fmt_ts(r['checked_at'])}",
             f"Accounts: {', '.join(r['accounts']) or 'none'}   Passkeys: {r['passkeys']}",
             r["message"], ""]
    for f in r["findings"]:
        lines.append(f"[{f['severity'].upper():8}] {f['code']}: {f['detail']}")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--accept", action="store_true", help="approve the current accounts/passkeys as the baseline")
    ap.add_argument("--json", action="store_true", help="print the report as JSON")
    args = ap.parse_args()
    if args.accept:
        b = accept()
        print(f"Baseline accepted: {len(b['creds'])} passkey(s) saved to {BASELINE_FILE}")
        return 0
    r = check()
    print(json.dumps(r, indent=2) if args.json else format_report(r))
    return 1 if any(f["severity"] in ("critical", "high") for f in r["findings"]) else 0


if __name__ == "__main__":
    sys.exit(main())
