"""Course structure (JSON before ARM, agent practice cards, skippable tool checks) and the agent-card handlers."""
import json
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.routes import projects as proj_mod  # noqa: E402

CID = "alp_phase2_bicep_course"

GOOD_TEMPLATE = {
    "$schema": "https://schema.management.azure.com/schemas/2019-04-01/deploymentTemplate.json#",
    "contentVersion": "1.0.0.0",
    "parameters": {"storageName": {"type": "string"}},
    "resources": [{
        "type": "Microsoft.Storage/storageAccounts", "apiVersion": "2023-01-01",
        "name": "[parameters('storageName')]", "location": "southafricanorth",
        "sku": {"name": "Standard_LRS"}, "kind": "StorageV2",
        "properties": {"supportsHttpsTrafficOnly": True, "minimumTlsVersion": "TLS1_2", "allowBlobPublicAccess": False},
    }],
}


@pytest.fixture()
def learner(monkeypatch, tmp_path):
    monkeypatch.setattr(proj_mod, "COURSE_SANDBOXES_ROOT", str(tmp_path / "boxes"))
    monkeypatch.setattr(proj_mod, "_course_learner_key", lambda: "agentlearner01")
    # the real recorder shells out to `asciinema cat`, which can block here; the plain-text fallback is enough
    monkeypatch.setattr(proj_mod.os.path, "isfile", proj_mod.os.path.isfile)
    real_run = proj_mod.subprocess.run

    def no_asciinema(cmd, *a, **k):
        if cmd and "asciinema" in str(cmd[0]):
            raise OSError("asciinema disabled in tests")
        return real_run(cmd, *a, **k)

    monkeypatch.setattr(proj_mod.subprocess, "run", no_asciinema)
    course, prog = proj_mod._load_course_and_progress(CID)
    prog["terms_accepted"] = {"accepted": True, "version": proj_mod.COURSE_TERMS_VERSION}
    prog["registration"] = {"registered": True, "verified": True, "full_name": "Ada Lovelace", "email": "ada@example.org"}
    secs = proj_mod._ordered_sections(course)
    return course, prog, [s for _, s in secs]


def _unlock_until(prog, sections, step_id):
    done = []
    for s in sections:
        if s["id"] == step_id:
            break
        done.append(s["id"])
    prog["completed_steps"] = done
    prog["reflections"] = {i: {"reflection_done": True} for i in done}
    proj_mod._save_progress_sync(CID, prog)


def test_json_comes_before_arm_and_codes_are_in_order(learner):
    course, _, sections = learner
    m1 = [m for m in course["modules"] if m["module_number"] == 1][0]["sections"]
    ids = [s["id"] for s in m1]
    assert ids.index("m1_json1") < ids.index("m1_json2") < ids.index("m1_learn2") < ids.index("m1_arm_syntax") < ids.index("m1_s1")
    assert ids.index("m1_s4") < ids.index("m1_agent_storage") < ids.index("m1_agent_vm") < ids.index("m1_agent_scope") < ids.index("m1_agent_build") < ids.index("m1_s5")
    assert [s["section_code"] for s in m1] == [f"Section 1.{i}" for i in range(1, len(m1) + 1)]
    for s in m1:
        if s["task_type"] == "multiple_choice":
            assert 0 <= s["correct_index"] < len(s["options"])
    assert len({s["id"] for s in sections}) == len(sections)


def test_tool_checks_are_skippable_and_no_personal_env_name(learner):
    course, _, sections = learner
    checks = [s for s in sections if s["id"].startswith("m0_t_")]
    assert len(checks) == 7 and all(s.get("skippable") for s in checks)
    blob = json.dumps(course)
    assert "alp-env" not in blob


def test_agent_ask_accept_and_limits(learner, monkeypatch):
    course, prog, sections = learner
    step = "m1_agent_storage"
    _unlock_until(prog, sections, step)
    calls = []

    def fake_model(system_prompt, user_prompt, **kw):
        calls.append((system_prompt, user_prompt, kw))
        return "I made a locked-down storage account.\n```json\n" + json.dumps(GOOD_TEMPLATE, indent=2) + "\n```"

    import core.local_model_service as lms
    monkeypatch.setattr(lms, "run_claude_model", fake_model)

    status, res = proj_mod._handle_agent_sync(CID, "agent_ask", {"step_id": step, "message": "Make me a secure storage account"})
    assert status == 200 and res["ok"] and res["problems"] == []
    assert json.loads(res["code"])["resources"][0]["type"] == "Microsoft.Storage/storageAccounts"
    # the agent is called without tools or an identity, and the learner text is fenced
    assert calls[0][2]["is_admin"] is False and calls[0][2]["user"] is None
    assert "<<<REQUEST" in calls[0][1]
    turns = res["progress"]["agent_turns"][step]
    assert [t["role"] for t in turns] == ["learner", "agent"]

    # recorded in the evidence log
    cast = list(Path(proj_mod._course_sandbox_dir()).glob("evidence/*/*.txt"))
    assert cast and "AGENT REQUEST" in cast[0].read_text(encoding="utf-8")

    # invalid JSON is refused, a secret written into the file is refused
    status, res = proj_mod._handle_agent_sync(CID, "agent_accept", {"step_id": step, "code": "{ not json"})
    assert status == 200 and res["ok"] is False
    bad = json.loads(json.dumps(GOOD_TEMPLATE))
    bad["resources"][0]["properties"]["adminPassword"] = "Hunter2Hunter2"
    status, res = proj_mod._handle_agent_sync(CID, "agent_accept", {"step_id": step, "code": json.dumps(bad)})
    assert res["ok"] is False and "secret" in res["output"].lower()

    status, res = proj_mod._handle_agent_sync(CID, "agent_accept", {"step_id": step, "code": json.dumps(GOOD_TEMPLATE)})
    assert status == 200 and res["ok"] is True
    saved = Path(proj_mod._course_sandbox_dir()) / "step_by_step_tasks" / "practice_storage.json"
    assert json.loads(saved.read_text(encoding="utf-8"))["contentVersion"] == "1.0.0.0"
    assert step in res["progress"]["completed_steps"]

    # per-card request limit
    monkeypatch.setattr(proj_mod, "_AGENT_TURNS_PER_STEP", 3)
    for _ in range(4):
        status, res = proj_mod._handle_agent_sync(CID, "agent_ask", {"step_id": step, "message": "Explain every line"})
        if status == 429:
            break
    assert status == 429


def test_scope_is_saved_and_used_by_build_card(learner, monkeypatch):
    course, prog, sections = learner
    _unlock_until(prog, sections, "m1_agent_scope")
    scope = "1. Build a private storage space.\n2. No virtual machines.\n3. Data stays in South Africa.\n4. Two staff use it."
    status, res = proj_mod._handle_agent_sync(CID, "agent_accept", {"step_id": "m1_agent_scope", "code": scope})
    assert status == 200 and res["ok"] is True
    assert res["progress"]["agent_scope"].startswith("1. Build a private storage space")
    status, res = proj_mod._handle_agent_sync(CID, "agent_accept", {"step_id": "m1_agent_scope", "code": "too short"})
    assert res["ok"] is False

    build = [s for s in sections if s["id"] == "m1_agent_build"][0]
    _, prog2 = proj_mod._load_course_and_progress(CID)
    prompt = proj_mod._agent_system_prompt(build, proj_mod._learner_profile_from_progress(prog2, True), prog2)
    assert "No virtual machines" in prompt


def test_agent_steps_are_locked_in_order_and_skip_needs_flag(learner):
    course, prog, sections = learner
    prog["completed_steps"], prog["reflections"] = [], {}
    proj_mod._save_progress_sync(CID, prog)
    status, res = proj_mod._handle_agent_sync(CID, "agent_ask", {"step_id": "m1_agent_build", "message": "hello agent"})
    assert status == 403
    status, res = proj_mod._handle_agent_sync(CID, "skip", {"step_id": "m0_s1"})
    assert status in (400, 403)  # locked and not skippable
    _unlock_until(prog, sections, "m0_s1")
    status, res = proj_mod._handle_agent_sync(CID, "skip", {"step_id": "m0_s1"})
    assert status == 400  # unlocked, but not a tool check
    status, res = proj_mod._handle_agent_sync(CID, "skip", {"step_id": "m0_t_bash"})
    assert status == 200 and res["ok"] and "m0_t_bash" in res["progress"]["completed_steps"]
    assert res["progress"]["reflections"]["m0_t_bash"]["reflection_done"] is True


def test_agent_reply_with_no_block_or_unavailable_agent(learner, monkeypatch):
    course, prog, sections = learner
    _unlock_until(prog, sections, "m1_agent_vm")
    import core.local_model_service as lms
    monkeypatch.setattr(lms, "run_claude_model", lambda *a, **k: "[LOCAL_BRAIN_UNAVAILABLE] nope")
    status, res = proj_mod._handle_agent_sync(CID, "agent_ask", {"step_id": "m1_agent_vm", "message": "Create a VM please"})
    assert status == 503 and res["ok"] is False
    monkeypatch.setattr(lms, "run_claude_model", lambda *a, **k: "A VM is a computer in the cloud.")
    status, res = proj_mod._handle_agent_sync(CID, "agent_ask", {"step_id": "m1_agent_vm", "message": "What is a VM?"})
    assert status == 200 and res["code"] == "" and "computer" in res["reply"]


def test_saved_work_feeds_profile_and_later_modules(learner):
    course, prog, sections = learner
    # beginner foundation comes first in Module 1
    m1 = [m for m in course["modules"] if m["module_number"] == 1][0]["sections"]
    assert [s["id"] for s in m1[:2]] == ["m1_cloud0", "m1_cloud1"]
    # later modules read the profile fields the agent cards fill in
    later = {s["id"]: s for m in course["modules"] for s in m["sections"]}
    assert "{{boilerplate_resources}}" in json.dumps(later["m4_s1"]["concept_bullets"])
    assert "{{scope_summary}}" in json.dumps(later["m5_s1"]["concept_bullets"])

    _unlock_until(prog, sections, "m1_agent_scope")
    scope = "1. Build a private storage space.\n2. No virtual machines.\n3. Data stays in South Africa.\n4. Two staff use it."
    status, res = proj_mod._handle_agent_sync(CID, "agent_accept", {"step_id": "m1_agent_scope", "code": scope})
    assert res["ok"] and "No virtual machines" in res["progress"]["learner_profile"]["scope_summary"]

    _unlock_until(prog, sections, "m1_agent_build")
    tpl = json.loads(json.dumps(GOOD_TEMPLATE))
    tpl["resources"].append({"type": "Microsoft.KeyVault/vaults", "apiVersion": "2023-02-01", "name": "kv1", "location": "x"})
    status, res = proj_mod._handle_agent_sync(CID, "agent_accept", {"step_id": "m1_agent_build", "code": json.dumps(tpl)})
    assert res["ok"]
    assert res["progress"]["learner_profile"]["boilerplate_resources"] == "a storage account and a key vault"
    assert proj_mod._interpolate_vars("holds {{boilerplate_resources}}", proj_mod._learner_profile_from_progress(res["progress"], True)) == "holds a storage account and a key vault"
