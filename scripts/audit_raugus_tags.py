#!/usr/bin/env python3
"""
=============================================================================
   RAUGUS TAG AUDITOR (audit_raugus_tags.py)
=============================================================================
Every file we keep or create (source, documents, projects, courses) is registered in security/raugus_map.json with
a stable ID, a tier (who may see/use it), a content hash and a version. This audit proves that is applied correctly
and stays that way, and tells you - in the audit results AND in logs/security_violations.jsonl + the SIEM log -
when something is out of place:

  TAG-01  the map loads and every entry has an id
  TAG-02  no two entries share an id
  TAG-03  every file has a version (1, 2, 3 ...)
  TAG-04  every file on disk is registered            (an unregistered file has no ID and no tier)
  TAG-05  every registered file still exists          (stale entry)
  TAG-06  the hash on disk matches the map            (changed since the last sync: version bump pending)
  TAG-07  source files keep their tier floor           (tier 5 unless deliberately marked sensitive)
  Against the last committed map (git HEAD):
  TAG-10  an ID never changes
  TAG-11  a version never goes down
  TAG-12  a changed hash always comes with a higher version
  TAG-13  a tier is never lowered and "sensitive" is never switched off
  TAG-14  a file that still exists was not dropped from the map

Usage:
  python3 scripts/audit_raugus_tags.py              # full audit (reads the files on disk)
  python3 scripts/audit_raugus_tags.py --quick      # continuity checks only; what the pre-commit hook runs
  python3 scripts/audit_raugus_tags.py --json
  python3 scripts/audit_raugus_tags.py --repair-ids     # put back the committed id of any entry whose id changed
  python3 scripts/audit_raugus_tags.py --install-hook   # run the quick audit on every commit (warns, never blocks)
Exit code 1 if anything FAILs. Every FAIL/WARN is appended to logs/security_violations.jsonl and the SIEM log.
=============================================================================
"""
import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from collections import Counter

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
MAP_REL = "security/raugus_map.json"
VIOLATIONS_REL = "logs/security_violations.jsonl"
HOOK_MARK = "raugus-tags-audit"

# the same walk rules as generate_raugusmap.py
IGNORE_DIRS = {".git", "__pycache__", "venv", "node_modules", ".venv", "scratch", ".pytest_cache", "desktop_app.dist", "build", "dist"}
IGNORE_FILES = {".DS_Store", "raugus_map.json"}
# changes constantly or is not ours: checked for continuity but not for coverage/drift
VOLATILE = ("logs/", "data/", "playground/", ".playwright-mcp/", ".runtime/", "archives/", "backups/", "tmp/", "Central_Docs/")
SOURCE_DIRS = ("core/", "security/", "agents/", "services/", "scripts/", ".agents/", "labcloud/")
MAX_HASH_BYTES = 20_000_000
FILE_TYPES = ("file", "plan")


def _alias(rel: str) -> str:
    return "devcore." + rel.replace("/", ".")


def _hash_file(path: str) -> str:
    """Same as generate_raugusmap.py: sha256 of the text, first 12 characters."""
    try:
        if os.path.getsize(path) > MAX_HASH_BYTES:
            return ""
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return hashlib.sha256(f.read().encode("utf-8")).hexdigest()[:12]
    except OSError:
        return ""


def load_map(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def load_baseline(root, ref="HEAD"):
    """The last committed map, or None when git or the file is not available."""
    try:
        out = subprocess.run(["git", "-C", root, "show", f"{ref}:{MAP_REL}"], capture_output=True, timeout=60)
        if out.returncode == 0 and out.stdout:
            return json.loads(out.stdout.decode("utf-8"))
    except (OSError, ValueError, subprocess.TimeoutExpired):
        pass
    return None


def _files(m, root=None):
    """File entries; with `root`, only those inside the project (entries for files elsewhere are not ours to version)."""
    out = {k: v for k, v in m.items() if v.get("type") in FILE_TYPES}
    if root is not None:
        out = {k: v for k, v in out.items() if not _rel_from_entry(root, v).startswith("..")}
    return out


def _transient(alias):
    """core/patches/ holds temporary patched copies: they come and go by design, so their ids are not tracked."""
    return ".patches." in alias


def _rel_from_entry(root, entry):
    try:
        return os.path.relpath(entry["real_path"], root).replace("\\", "/")
    except (KeyError, ValueError):
        return ""


def _in_scope(rel: str) -> bool:
    return not rel.startswith(VOLATILE) and "/cache/" not in rel and not rel.endswith((".pyc", ".log"))


def disk_files(root):
    """Relative paths of files the generator would register, limited to what we create (not volatile)."""
    found = {}
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in IGNORE_DIRS]
        for name in filenames:
            if name in IGNORE_FILES:
                continue
            rel = os.path.relpath(os.path.join(dirpath, name), root).replace("\\", "/")
            if _in_scope(rel):
                found[rel] = os.path.join(dirpath, name)
    return found


# ------------------------------------------------------------------ the checks (pure: easy to test)
def check_internal(m, root=ROOT):
    out = []
    no_id = [k for k, v in m.items() if not v.get("id")]
    out.append(("TAG-01", "FAIL", f"{len(no_id)} entries have no id, e.g. {no_id[:2]}") if no_id else
               ("TAG-01", "PASS", f"map loaded: {len(m)} entries, all with an id"))
    dup = [i for i, n in Counter(v.get("id") for v in m.values() if v.get("id")).items() if n > 1]
    out.append(("TAG-02", "FAIL", f"{len(dup)} ids are shared by more than one entry, e.g. {dup[:2]}") if dup else
               ("TAG-02", "PASS", "every id is unique"))
    no_ver = [k for k, v in _files(m, root).items() if not isinstance(v.get("version"), int) or v["version"] < 1]
    out.append(("TAG-03", "FAIL", f"{len(no_ver)} files have no version (run the Raugus sync), e.g. {no_ver[:2]}") if no_ver else
               ("TAG-03", "PASS", f"all {len(_files(m, root))} files carry a version"))
    low = []
    for k, v in _files(m, root).items():
        rel = _rel_from_entry(root, v)
        if rel.startswith(SOURCE_DIRS) and int(v.get("required_tier", 5)) < 5 and not v.get("sensitive"):
            low.append(rel)
    out.append(("TAG-07", "FAIL", f"{len(low)} source files are below their tier floor (5), e.g. {low[:3]}") if low else
               ("TAG-07", "PASS", "source files keep their tier floor"))
    return out



def check_continuity(m, base):
    """Compare with the last committed map: IDs, versions, hashes and tiers may only move forward."""
    out, changed_id, went_down, no_bump, lowered, dropped = [], [], [], [], [], []
    for alias, old in base.items():
        if _transient(alias):
            continue
        new = m.get(alias)
        if new is None:
            if old.get("type") in FILE_TYPES and os.path.exists(old.get("real_path", "")):
                dropped.append(alias)
            continue
        if old.get("id") and new.get("id") != old["id"]:
            changed_id.append(alias)
        if int(new.get("required_tier", 0)) < int(old.get("required_tier", 0)) or (old.get("sensitive") and not new.get("sensitive")):
            lowered.append(alias)
        if old.get("type") in FILE_TYPES:
            ov, nv = old.get("version"), new.get("version")
            if isinstance(ov, int) and isinstance(nv, int):
                if nv < ov:
                    went_down.append(alias)
                elif old.get("content_hash") != new.get("content_hash") and nv <= ov:
                    no_bump.append(alias)
    fmt = lambda xs: [a.replace("devcore.", "", 1) for a in xs[:3]]  # noqa: E731
    for cid, items, bad, good in (
        ("TAG-10", changed_id, "ids changed (an id must never change)", "no id changed since the last commit"),
        ("TAG-11", went_down, "versions went DOWN", "no version went down"),
        ("TAG-12", no_bump, "files changed content but their version was not raised", "every changed file has a higher version"),
        ("TAG-13", lowered, "entries had their tier lowered or 'sensitive' switched off", "no tier was lowered"),
    ):
        out.append((cid, "FAIL", f"{len(items)} {bad}, e.g. {fmt(items)}") if items else (cid, "PASS", good))
    out.append(("TAG-14", "WARN", f"{len(dropped)} existing files were dropped from the map, e.g. {fmt(dropped)}") if dropped else
               ("TAG-14", "PASS", "no existing file was dropped from the map"))
    return out


def check_disk(root, m):
    """Compare the map with the files actually on disk."""
    out = []
    on_disk = disk_files(root)
    reg = {}
    for alias, v in _files(m, root).items():
        rel = _rel_from_entry(root, v)
        if rel and _in_scope(rel):
            reg[rel] = v
    missing = sorted(set(on_disk) - set(reg))
    gone = sorted(r for r in reg if not os.path.exists(os.path.join(root, r)))
    drift = sorted(r for r in reg if r in on_disk and reg[r].get("content_hash") and _hash_file(on_disk[r]) not in ("", reg[r]["content_hash"]))
    top = lambda xs: dict(Counter(x.split("/")[0] if "/" in x else "(top level)" for x in xs).most_common(4))  # noqa: E731
    out.append(("TAG-04", "FAIL", f"{len(missing)} files are not registered (no id, no tier): {top(missing)} e.g. {missing[:3]}") if missing else
               ("TAG-04", "PASS", f"all {len(on_disk)} files on disk are registered"))
    out.append(("TAG-05", "WARN", f"{len(gone)} map entries point to files that are gone, e.g. {gone[:3]}") if gone else
               ("TAG-05", "PASS", "no stale entries"))
    out.append(("TAG-06", "WARN", f"{len(drift)} files changed since the last sync (version bump pending): {top(drift)} e.g. {drift[:3]}") if drift else
               ("TAG-06", "PASS", "every file matches its recorded hash"))
    return out


def repair_ids(m, base):
    """Put back the committed id of every entry whose id changed (the content is the same entry). Returns how many."""
    fixed = 0
    for alias, old in base.items():
        new = m.get(alias)
        if new is None or _transient(alias) or not old.get("id") or new.get("id") == old["id"]:
            continue
        new["id"] = old["id"]
        fixed += 1
    return fixed


def run_audit(root=ROOT, map_obj=None, baseline=None, quick=False):
    m = map_obj if map_obj is not None else load_map(os.path.join(root, MAP_REL))
    results = [("1 Tags in the map", *r) for r in check_internal(m, root)]
    if baseline is not None:
        results += [("2 Against the last commit", *r) for r in check_continuity(m, baseline)]
    if not quick:
        results += [("3 Against the files on disk", *r) for r in check_disk(root, m)]
    return results


# ------------------------------------------------------------------ logging: audit results + SIEM + violations log
def log_problems(results, root=ROOT, siem=True):
    bad = [r for r in results if r[2] in ("FAIL", "WARN")]
    if not bad:
        return
    path = os.path.join(root, VIOLATIONS_REL)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        for stage, cid, level, msg in bad:
            f.write(json.dumps({"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "source": "audit_raugus_tags",
                                "stage": stage, "id": cid, "level": level, "message": msg}) + "\n")
    if not siem:
        return
    try:
        sys.path.insert(0, root)
        from security.central_logger import log_siem_event
        for stage, cid, level, msg in bad:
            log_siem_event(level="ERROR" if level == "FAIL" else "WARNING",
                           message=f"[SECURITY_AUDIT] [RAUGUS_TAGS] {cid} {level}: {msg}"[:900],
                           module_name="audit_raugus_tags", logger_name="security.raugus_tags")
    except Exception:
        pass


def install_hook(root=ROOT) -> str:
    hook = os.path.join(root, ".git", "hooks", "pre-commit")
    if not os.path.isfile(hook):
        return "no .git/hooks/pre-commit found (run scripts/git_bootstrap.py first)"
    txt = open(hook, encoding="utf-8").read()
    if HOOK_MARK in txt:
        return "hook already installed"
    block = f"""
# >>> {HOOK_MARK} (installed by scripts/audit_raugus_tags.py --install-hook)
echo "🔒 [PRE-COMMIT] Checking Raugus tags (ids, tiers, versions)..."
python3 "$(git rev-parse --show-toplevel)/scripts/audit_raugus_tags.py" --quick --warn-only
# <<< {HOOK_MARK}
"""
    with open(hook, "a", encoding="utf-8", newline="\n") as f:
        f.write(block)
    os.chmod(hook, 0o755)
    return "hook installed: every commit now checks (and logs) the Raugus tags; it warns, it never blocks"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Raugus tag auditor")
    ap.add_argument("--quick", action="store_true", help="continuity checks only (no disk walk)")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--warn-only", action="store_true", help="print and log problems but always exit 0 (the commit hook)")
    ap.add_argument("--repair-ids", action="store_true", help="restore the committed id of every entry whose id changed, then audit")
    ap.add_argument("--install-hook", action="store_true")
    args = ap.parse_args(argv)
    if args.install_hook:
        print(install_hook())
        return 0
    if args.repair_ids:
        base = load_baseline(ROOT)
        if base is None:
            print("no committed map to repair from")
            return 1
        path = os.path.join(ROOT, MAP_REL)
        m = load_map(path)
        n = repair_ids(m, base)
        if n:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(m, f, indent=4)
        print(f"restored {n} committed id(s) in {MAP_REL}")
    try:
        results = run_audit(ROOT, baseline=load_baseline(ROOT), quick=args.quick)
    except (OSError, ValueError) as e:
        print(f"cannot read {MAP_REL}: {e}")
        return 1
    log_problems(results)
    if args.json:
        print(json.dumps({"summary": {s: sum(1 for r in results if r[2] == s) for s in ("PASS", "WARN", "FAIL")},
                          "results": [{"stage": a, "id": b, "status": c, "message": d} for a, b, c, d in results]}, indent=1))
    else:
        last = None
        for stage, cid, level, msg in results:
            if stage != last:
                print(f"\n=== {stage} ===")
                last = stage
            print(f"  [{level:<4}] {cid:<7} {msg}")
        n = lambda s: sum(1 for r in results if r[2] == s)  # noqa: E731
        print("\n" + "=" * 70)
        print(f"  RAUGUS TAG AUDIT: {n('PASS')} pass, {n('WARN')} warn, {n('FAIL')} FAIL")
        print("=" * 70)
    fails = [r for r in results if r[2] == "FAIL"]
    if args.quick:
        fails = [r for r in fails if r[1] in ("TAG-02", "TAG-10", "TAG-11", "TAG-12", "TAG-13")]
    if fails and args.warn_only:
        print(f"  ({len(fails)} problem(s) logged to {VIOLATIONS_REL}; --warn-only: not blocking this commit)")
        return 0
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
