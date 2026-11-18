"""The Raugus tags (id / tier / version) must be applied correctly and stay that way. These tests build a small project,
generate its Raugus map, then break it on purpose in every way the audit is supposed to notice."""
import copy
import json
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import generate_raugusmap as G  # noqa: E402
import audit_raugus_tags as A  # noqa: E402


def write(root, rel, text):
    path = os.path.join(root, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    return path


@pytest.fixture()
def project(tmp_path):
    root = str(tmp_path)
    write(root, "core/app.py", "def main():\n    return 1\n")
    write(root, "security/guard.py", "def check():\n    return True\n")
    write(root, "docs/guide.md", "# Guide\n\nHello.\n")
    write(root, "workspaces/learner1/proj/notes.md", "# My project\n")
    return root


def gen(root, existing=None):
    m = G.generate_raugusmap(root, existing_map=existing)
    return {k: v for k, v in m.items() if not k.startswith("external.")}      # ignore machine-specific OneDrive roots


def entry(m, rel):
    return m["devcore." + rel.replace("/", ".")]


def verdicts(results):
    return {cid: level for _, cid, level, _ in results}


def audit(root, m, base=None, quick=False):
    return verdicts(A.run_audit(root, map_obj=m, baseline=base, quick=quick))


# ---------------------------------------------------------------- the generator: id stays, version follows the hash
def test_every_file_gets_an_id_a_tier_and_version_one(project):
    m = gen(project)
    for rel in ("core/app.py", "docs/guide.md", "workspaces/learner1/proj/notes.md"):
        e = entry(m, rel)
        assert e["id"] and e["version"] == 1 and e["required_tier"] in (2, 3, 5) and e["content_hash"]


def test_id_stays_and_version_rises_only_when_the_hash_changes(project):
    m1 = gen(project)
    m_same = gen(project, existing=m1)
    assert entry(m_same, "docs/guide.md")["version"] == 1                       # nothing changed
    write(project, "docs/guide.md", "# Guide\n\nHello, changed.\n")
    m2 = gen(project, existing=m_same)
    a, b = entry(m1, "docs/guide.md"), entry(m2, "docs/guide.md")
    assert b["id"] == a["id"] and b["version"] == 2 and b["content_hash"] != a["content_hash"]
    write(project, "docs/guide.md", "# Guide\n\nHello, changed again.\n")
    m3 = gen(project, existing=m2)
    assert entry(m3, "docs/guide.md")["version"] == 3 and entry(m3, "docs/guide.md")["id"] == a["id"]
    assert entry(m3, "core/app.py")["version"] == 1                              # untouched files keep their version


def test_a_clean_project_passes_the_audit(project):
    m1 = gen(project)
    write(project, "docs/guide.md", "# Guide v2\n")
    m2 = gen(project, existing=m1)
    v = audit(project, m2, base=m1)
    assert "FAIL" not in v.values() and "WARN" not in v.values(), v


# ---------------------------------------------------------------- things out of place: each must be noticed
def test_unregistered_new_file_is_flagged(project):
    m = gen(project)
    write(project, "docs/new_document.md", "# created after the last sync\n")
    assert audit(project, m)["TAG-04"] == "FAIL"


def test_file_changed_since_the_last_sync_is_flagged(project):
    m = gen(project)
    write(project, "core/app.py", "def main():\n    return 2\n")
    assert audit(project, m)["TAG-06"] == "WARN"


def test_stale_entry_for_a_deleted_file_is_flagged(project):
    m = gen(project)
    os.remove(os.path.join(project, "docs/guide.md"))
    assert audit(project, m)["TAG-05"] == "WARN"


def test_missing_version_is_flagged(project):
    m = gen(project)
    del entry(m, "core/app.py")["version"]
    assert audit(project, m)["TAG-03"] == "FAIL"


def test_duplicate_id_is_flagged(project):
    m = gen(project)
    entry(m, "core/app.py")["id"] = entry(m, "docs/guide.md")["id"]
    assert audit(project, m)["TAG-02"] == "FAIL"


def test_missing_id_is_flagged(project):
    m = gen(project)
    del entry(m, "docs/guide.md")["id"]
    assert audit(project, m)["TAG-01"] == "FAIL"


def test_source_file_below_its_tier_floor_is_flagged(project):
    m = gen(project)
    entry(m, "security/guard.py")["required_tier"] = 2
    assert audit(project, m)["TAG-07"] == "FAIL"


def test_sensitive_source_may_use_the_broker_tier(project):
    m = gen(project)
    e = entry(m, "security/guard.py")
    e["required_tier"], e["sensitive"] = 3, True
    assert audit(project, m)["TAG-07"] == "PASS"


# ---------------------------------------------------------------- continuity against the last commit
def test_a_changed_id_is_flagged(project):
    base = gen(project)
    m = copy.deepcopy(base)
    entry(m, "docs/guide.md")["id"] = "not-the-same-id"
    assert audit(project, m, base=base)["TAG-10"] == "FAIL"


def test_a_version_going_down_is_flagged(project):
    base = gen(project)
    write(project, "docs/guide.md", "# changed\n")
    base = gen(project, existing=base)                                          # version 2 is now the committed one
    m = copy.deepcopy(base)
    entry(m, "docs/guide.md")["version"] = 1
    assert audit(project, m, base=base)["TAG-11"] == "FAIL"


def test_a_changed_hash_without_a_version_bump_is_flagged(project):
    base = gen(project)
    m = copy.deepcopy(base)
    entry(m, "core/app.py")["content_hash"] = "deadbeef0000"                     # content "changed", version left alone
    assert audit(project, m, base=base)["TAG-12"] == "FAIL"


def test_a_lowered_tier_is_flagged(project):
    base = gen(project)
    m = copy.deepcopy(base)
    entry(m, "core/app.py")["required_tier"] = 3
    assert audit(project, m, base=base)["TAG-13"] == "FAIL"


def test_switching_sensitive_off_is_flagged(project):
    base = gen(project)
    entry(base, "docs/guide.md")["sensitive"] = True
    m = copy.deepcopy(base)
    entry(m, "docs/guide.md")["sensitive"] = False
    assert audit(project, m, base=base)["TAG-13"] == "FAIL"


def test_a_file_dropped_from_the_map_is_flagged(project):
    base = gen(project)
    m = copy.deepcopy(base)
    del m["devcore.docs.guide.md"]
    assert audit(project, m, base=base)["TAG-14"] == "WARN"


def test_quick_mode_skips_the_disk_walk(project):
    m = gen(project)
    write(project, "docs/another.md", "# new\n")
    v = audit(project, m, quick=True)
    assert "TAG-04" not in v and "TAG-06" not in v


# ---------------------------------------------------------------- ids must survive a file that is broken for a moment
def test_ids_survive_a_file_that_cannot_be_parsed_for_a_moment(project):
    """The bug found on 2026-11-18: a sync that ran while a file had a syntax error dropped its entries, and they came
    back with brand-new ids once the file was fixed."""
    write(project, "core/tools.py", "def alpha():\n    return 1\n\n\ndef beta():\n    return 2\n")
    m1 = gen(project)
    ids_before = {k: v["id"] for k, v in m1.items() if k.startswith("devcore.core.tools.py::")}
    assert len(ids_before) == 2
    write(project, "core/tools.py", "def alpha(:\n    return 1\n")                # broken mid-edit
    m2 = gen(project, existing=m1)
    assert {k: m2[k]["id"] for k in ids_before} == ids_before                       # still there, same ids (marked stale)
    assert all(m2[k].get("stale") for k in ids_before)
    write(project, "core/tools.py", "def alpha():\n    return 1\n\n\ndef beta():\n    return 2\n")     # fixed
    m3 = gen(project, existing=m2)
    assert {k: m3[k]["id"] for k in ids_before} == ids_before                       # the same ids as at the start
    assert not any(m3[k].get("stale") for k in ids_before)
    assert verdicts(A.run_audit(project, map_obj=m3, baseline=m1))["TAG-10"] == "PASS"


def test_repair_restores_committed_ids_and_nothing_else(project):
    base = gen(project)
    m = copy.deepcopy(base)
    entry(m, "docs/guide.md")["id"] = "not-the-same-id"
    entry(m, "core/app.py")["content_hash"] = "deadbeef0000"
    assert audit(project, m, base=base)["TAG-10"] == "FAIL"
    assert A.repair_ids(m, base) == 1
    assert entry(m, "docs/guide.md")["id"] == entry(base, "docs/guide.md")["id"]
    assert entry(m, "core/app.py")["content_hash"] == "deadbeef0000"               # content/version are left alone
    assert audit(project, m, base=base)["TAG-10"] == "PASS"
    assert A.repair_ids(m, base) == 0                                               # idempotent


def test_volatile_runtime_files_do_not_count(project):
    m = gen(project)
    write(project, ".runtime/stream_events.json", "{}")
    m = gen(project)
    write(project, ".runtime/stream_events.json", '{"changed": true}')
    v = audit(project, m)
    assert v["TAG-06"] == "PASS" and v["TAG-04"] == "PASS"


def test_temporary_patch_copies_are_not_tracked_for_id_changes(project):
    write(project, "core/patches/hotfix.py", "x = 1\n")
    base = gen(project)
    m = copy.deepcopy(base)
    entry(m, "core/patches/hotfix.py")["id"] = "a-new-id"
    assert audit(project, m, base=base)["TAG-10"] == "PASS"


def test_files_outside_the_project_are_not_required_to_have_versions(project):
    m = gen(project)
    m["devcore.brain.plan.abc.plan"] = {"type": "plan", "real_path": "/somewhere/else/plan.md", "required_tier": 3,
                                        "sensitive": False, "id": "plan-1", "content_hash": "abc"}
    assert audit(project, m)["TAG-03"] == "PASS"


def test_warn_only_never_blocks_but_normal_mode_does(project, monkeypatch, capsys):
    base = gen(project)
    m = copy.deepcopy(base)
    entry(m, "docs/guide.md")["id"] = "changed-id"
    monkeypatch.setattr(A, "ROOT", project)
    monkeypatch.setattr(A, "load_map", lambda p: m)
    monkeypatch.setattr(A, "load_baseline", lambda root, ref="HEAD": base)
    monkeypatch.setattr(A, "log_problems", lambda *a, **k: None)
    assert A.main(["--quick"]) == 1
    assert A.main(["--quick", "--warn-only"]) == 0
    assert "TAG-10" in capsys.readouterr().out


# ---------------------------------------------------------------- logs
def test_problems_are_written_to_the_violations_log(project):
    m = gen(project)
    write(project, "docs/new_document.md", "# new\n")
    results = A.run_audit(project, map_obj=m)
    A.log_problems(results, root=project, siem=False)
    lines = [json.loads(x) for x in open(os.path.join(project, A.VIOLATIONS_REL), encoding="utf-8")]
    assert any(x["source"] == "audit_raugus_tags" and x["id"] == "TAG-04" and x["level"] == "FAIL" for x in lines)
    assert all({"ts", "source", "stage", "id", "level", "message"} <= set(x) for x in lines)


def test_a_clean_audit_writes_nothing(project):
    m = gen(project)
    A.log_problems(A.run_audit(project, map_obj=m), root=project, siem=False)
    assert not os.path.exists(os.path.join(project, A.VIOLATIONS_REL))


def test_hook_install_is_idempotent(tmp_path):
    os.makedirs(tmp_path / ".git" / "hooks")
    hook = tmp_path / ".git" / "hooks" / "pre-commit"
    hook.write_text("#!/usr/bin/env bash\nset -e\n")
    assert "installed" in A.install_hook(str(tmp_path))
    first = hook.read_text()
    assert "audit_raugus_tags.py" in first and "--quick" in first
    assert "already installed" in A.install_hook(str(tmp_path))
    assert hook.read_text() == first


# ---------------------------------------------------------------- the real project: ids/versions/tiers only move forward
def test_real_map_only_moves_forward_from_the_last_commit():
    live_path = os.path.join(ROOT, A.MAP_REL)
    base = A.load_baseline(ROOT)
    if base is None or not os.path.isfile(live_path):
        pytest.skip("no git baseline available")
    v = verdicts(A.run_audit(ROOT, baseline=base, quick=True))
    # Ids/tiers that already changed BEFORE this audit existed (TAG-10/13) are reported by the audit itself and logged;
    # they cannot be undone here. This test guards what must never get worse: duplicate ids and versions.
    broken = {k: lvl for k, lvl in v.items() if k in ("TAG-02", "TAG-11", "TAG-12") and lvl == "FAIL"}
    assert not broken, f"the Raugus map regressed against the last commit: {broken} (run scripts/audit_raugus_tags.py for details)"
