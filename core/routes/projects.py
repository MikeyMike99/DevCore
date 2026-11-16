import asyncio
import contextvars
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import time
import zipfile
from quart import Blueprint, request, jsonify, current_app, Response, render_template_string
from core.routes.auth import get_current_user

projects_bp = Blueprint('projects_bp', __name__)

_DEVCORE_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ADMIN_COURSE_SANDBOX = '/home/michael/alp-env/temp_phase2_sandbox'
COURSE_SANDBOXES_ROOT = os.path.join(_DEVCORE_ROOT, 'playground', '.course_sandboxes')
COURSE_JAIL = os.path.join(_DEVCORE_ROOT, 'scripts', 'course_jail.sh')
_COURSE_BOX = contextvars.ContextVar('devcore_course_box', default=None)


def _course_learner_key():
    """None for the Tier 5 super admin; otherwise a stable, non-reversible key for this learner."""
    from core.routes.system import _is_tier5_request, _request_user
    if _is_tier5_request():
        return None
    user = _request_user()
    ident = str(user.get('username') or user.get('name') or '') if isinstance(user, dict) else ''
    if not ident:
        from security import guest_session
        ident = guest_session.session_from_headers(request.headers) or ('ip:' + (request.remote_addr or ''))
    return hashlib.sha256(('course-learner:' + ident).encode('utf-8')).hexdigest()[:24]


def _ensure_learner_box(key: str) -> str:
    box = os.path.join(COURSE_SANDBOXES_ROOT, key)
    if not os.path.isdir(box):
        tmp = box + '.tmp'
        shutil.rmtree(tmp, ignore_errors=True)
        shutil.copytree(ADMIN_COURSE_SANDBOX, tmp, ignore=shutil.ignore_patterns(
            'evidence', 'course_progress_*', 'EVIDENCE_MANIFEST.md'))
        os.makedirs(os.path.join(tmp, 'evidence', 'michael'), exist_ok=True)
        os.replace(tmp, box)
    return box


@projects_bp.before_request
async def _bind_course_sandbox():
    """Security invariant: only the Tier 5 super admin works in the real alp-env course sandbox.
    Every other visitor of the course API is bound to a private copy under
    playground/.course_sandboxes, and their commands run inside scripts/course_jail.sh."""
    if not request.path.startswith('/api/course/'):
        return
    key = _course_learner_key()
    box = ADMIN_COURSE_SANDBOX if key is None else await asyncio.to_thread(_ensure_learner_box, key)
    _COURSE_BOX.set(box)


def _course_sandbox_dir() -> str:
    box = _COURSE_BOX.get()
    if box:
        return box
    key = _course_learner_key()
    box = ADMIN_COURSE_SANDBOX if key is None else _ensure_learner_box(key)
    _COURSE_BOX.set(box)
    return box


def _is_learner_box(box: str) -> bool:
    return os.path.realpath(box) != os.path.realpath(ADMIN_COURSE_SANDBOX)


@projects_bp.route('/api/projects', methods=['GET'])
async def list_projects():
    user = get_current_user()
    current_app.project_mgr.get_active_workspace_path()
    projects = current_app.project_mgr.list_projects(user=user) if user else []
    active = current_app.project_mgr.active_project
    root_name = "Workspaces"
    return jsonify({"projects": projects, "active": active, "root_name": root_name})


@projects_bp.route('/api/projects', methods=['POST'])
async def create_project():
    user = get_current_user()
    if not current_app.security_mgr.can_create_project(user):
        return jsonify({"error": "Access Denied: only the Super Admin can create projects"}), 403
    data = await request.get_json() or {}
    name = (data.get('name') or '').strip()
    from core.roles import tier_for_role
    try:
        current_app.project_mgr.create_project(name, user_tier=tier_for_role(user.get("role")))
        return jsonify({"success": True, "project": name})
    except (ValueError, FileExistsError, PermissionError) as e:
        return jsonify({"error": str(e)}), 400


@projects_bp.route('/api/projects/active', methods=['POST'])
async def set_active_project():
    user = get_current_user()
    data = await request.get_json() or {}
    name = data.get('name')
    if name:
        name = name.strip()
    if not current_app.security_mgr.can_switch_project(user, name):
        return jsonify({"error": "Access Denied: You do not have permission for this project"}), 403
    from core.roles import tier_for_role
    try:
        p = current_app.project_mgr.set_active_project(name, user_tier=tier_for_role(user.get("role")))
        return jsonify({"success": True, "active": current_app.project_mgr.active_project, "path": p})
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@projects_bp.route('/api/conversations', methods=['GET'])
async def list_conversations():
    user = get_current_user()
    if not user:
        return jsonify({"error": "Unauthorized"}), 401

    limit = request.args.get('limit', default=10, type=int)
    current_app.project_mgr.get_active_workspace_path()
    convos, has_more = await asyncio.to_thread(
        current_app.session_mgr.list_conversations,
        current_app.project_mgr.active_project,
        user,
        limit
    )
    return jsonify({"conversations": convos, "has_more": has_more})


@projects_bp.route('/api/conversations/<conv_id>', methods=['GET'])
async def get_conversation(conv_id):
    user = get_current_user()
    if not user:
        return jsonify({"error": "Unauthorized"}), 401
    rename_to = request.args.get('rename')
    if rename_to is not None:
        ok = await asyncio.to_thread(current_app.session_mgr.rename_session, conv_id, rename_to, user)
        if not ok:
            return jsonify({"error": "Failed to rename session"}), 400
        return jsonify({"success": True, "title": rename_to.strip()})
    try:
        items = await asyncio.to_thread(current_app.session_mgr.get_conversation_transcript, conv_id, user)
        rollover = await asyncio.to_thread(current_app.session_mgr.get_rollover_info, conv_id, user)
        return jsonify({"items": items, "rollover": rollover})
    except PermissionError as e:
        return jsonify({"error": str(e)}), 403
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@projects_bp.route('/api/conversations/<conv_id>/rename', methods=['POST'])
async def rename_conversation(conv_id):
    user = get_current_user()
    if not user:
        return jsonify({"error": "Unauthorized"}), 401
    data = await request.get_json() or {}
    new_title = (data.get('title') or data.get('name') or '').strip()
    if not new_title:
        return jsonify({"error": "Title is required"}), 400
    try:
        ok = await asyncio.to_thread(current_app.session_mgr.rename_session, conv_id, new_title, user)
        if ok:
            return jsonify({"success": True, "title": new_title})
        return jsonify({"error": "Access Denied or invalid session"}), 403
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@projects_bp.route('/api/conversations/<conv_id>', methods=['DELETE'])
async def delete_conversation(conv_id):
    user = get_current_user()
    if not user:
        return jsonify({"error": "Unauthorized"}), 401
    try:
        success = await asyncio.to_thread(current_app.session_mgr.delete_session, conv_id, user)
        if success:
            return jsonify({"success": True})
        else:
            return jsonify({"error": "Failed to delete"}), 403
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@projects_bp.route('/api/projects/active/conversations', methods=['DELETE'])
async def clear_project_sessions():
    user = get_current_user()
    if not user:
        return jsonify({"error": "Unauthorized"}), 401

    current_app.project_mgr.get_active_workspace_path()
    active_proj = current_app.project_mgr.active_project

    try:
        await asyncio.to_thread(current_app.session_mgr.delete_project_sessions, active_proj, user)
        return jsonify({"success": True, "project": active_proj})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


def _course_repo_root() -> str:
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _safe_course_id(raw_id: str) -> str:
    cleaned = re.sub(r'[^A-Za-z0-9_.-]', '', (raw_id or 'alp_phase2_bicep_course').strip())
    if cleaned.endswith('.json'):
        cleaned = cleaned[:-5]
    return cleaned or 'alp_phase2_bicep_course'


def _progress_paths(course_id: str) -> list:
    box = _course_sandbox_dir()
    if _is_learner_box(box):
        return [os.path.join(box, f'course_progress_{course_id}.json')]
    repo_root = _course_repo_root()
    courses_dir = os.path.join(repo_root, 'sandbox', 'static', 'courses')
    os.makedirs(courses_dir, exist_ok=True)
    paths = [os.path.join(courses_dir, f'progress_{course_id}.json')]
    wsl_sandbox = '/home/michael/alp-env/temp_phase2_sandbox'
    if os.path.isdir(wsl_sandbox):
        paths.insert(0, os.path.join(wsl_sandbox, f'course_progress_{course_id}.json'))
    return paths


def _load_course_and_progress(course_id: str) -> tuple:
    repo_root = _course_repo_root()
    cid = _safe_course_id(course_id)
    candidates = [
        os.path.join(repo_root, 'sandbox', 'static', f'{cid}.json'),
        os.path.join(repo_root, 'sandbox', 'static', 'courses', f'{cid}.json'),
        os.path.join(repo_root, 'sandbox', 'static', 'exams', f'{cid}.json'),
    ]
    course_obj = None
    for p in candidates:
        if os.path.isfile(p):
            try:
                with open(p, 'r', encoding='utf-8') as f:
                    course_obj = json.load(f)
                break
            except Exception:
                pass
    progress_obj = {
        "current_step_index": 0,
        "completed_steps": [],
        "step_outputs": {},
        "reflections": {},
        "step_requirements": {},
        "env_lock_sha256": "",
        "activity_log": [],
        "learner_name": "learner" if _is_learner_box(_course_sandbox_dir()) else "michael"
    }
    for pp in _progress_paths(cid):
        if os.path.isfile(pp):
            try:
                with open(pp, 'r', encoding='utf-8') as pf:
                    progress_obj.update(json.load(pf))
                break
            except Exception:
                pass
    return course_obj, progress_obj


def _save_progress_sync(course_id: str, progress: dict) -> None:
    cid = _safe_course_id(course_id)
    to_write = progress
    if isinstance(progress, dict) and progress.get('encrypted_workspace_id'):
        to_write = {
            "encrypted_workspace_id": progress.get("encrypted_workspace_id"),
            "zero_knowledge_mode": True,
            "current_step_index": 0,
            "completed_steps": [],
            "step_outputs": {},
            "reflections": {},
            "step_requirements": {},
            "activity_log": [],
            "learner_name": "encrypted-member"
        }
    for pp in _progress_paths(cid):
        try:
            with open(pp, 'w', encoding='utf-8') as pf:
                json.dump(to_write, pf, indent=2, ensure_ascii=False)
        except Exception:
            pass


def _generate_evidence_manifest(course_id: str, learner_override: str = None) -> tuple:
    sandbox_dir = _course_sandbox_dir()
    os.makedirs(sandbox_dir, exist_ok=True)
    course_obj, progress = _load_course_and_progress(course_id)
    jailed = _is_learner_box(sandbox_dir)
    default_learner = 'learner' if jailed else 'michael'
    learner = (learner_override or progress.get('learner_name') or default_learner).strip() or default_learner
    env_label = "Private Siraugga course sandbox (isolated, runs on the server)" if jailed else f"`{sandbox_dir}` (`/home/michael/alp-env`)"
    env_intro = ("This course uses an interactive structured learning environment paired with a private, isolated Siraugga sandbox and `asciinema` terminal recorder:"
                 if jailed else
                 "This course uses an interactive structured learning environment paired with a real WSL `alp-env` sandbox and `asciinema` terminal recorder:")
    env_where = "inside their private course sandbox" if jailed else "inside `/home/michael/alp-env/temp_phase2_sandbox`"
    now_str = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())

    sections = []
    if course_obj and isinstance(course_obj.get('modules'), list):
        for mod in course_obj.get('modules', []):
            for sec in mod.get('sections', []):
                sections.append((mod, sec))

    completed = progress.get('completed_steps') or []
    reflections = progress.get('reflections') or {}
    outputs = progress.get('step_outputs') or {}
    activity_log = progress.get('activity_log') or []

    reflected_count = sum(1 for s_id, r in reflections.items() if isinstance(r, dict) and r.get('reflection_done'))
    total_pastes = sum(int(r.get('paste_attempts') or 0) for r in reflections.values() if isinstance(r, dict))
    total_runs = sum(int(r.get('run_count') or 0) for r in reflections.values() if isinstance(r, dict))

    lines = [
        "# Verifiable Learning & Authorship Evidence Manifest",
        "",
        f"- **Learner / Assignee**: {learner}",
        f"- **Course ID**: `{_safe_course_id(course_id)}`",
        f"- **Course Title**: {(course_obj or {}).get('title', 'ALP Phase 2 Interactive Practical Course')}",
        f"- **Sandbox Environment**: {env_label}",
        f"- **Generated Timestamp (UTC)**: `{now_str}`",
        "",
        "## 1. Transparent AI Tool Usage & Authorship Disclosure",
        "",
        env_intro,
        "1. **Pre-Execution Prediction**: Before executing any terminal command or compiling any `.bicep` template, the learner was required to type a prediction in their own words explaining what the step would do and why.",
        f"2. **Hands-On Execution & Asciinema Capture**: Every command and `.bicep` compilation was triggered by the learner {env_where} and recorded into `.cast` and `.txt` transcripts under `evidence/`.",
        "3. **Continuous Post-Run Reflection & Troubleshooting**: After observing the live compiler/CLI output, the learner wrote an explanation of the result and how to diagnose/fix anticipated common errors for that step.",
        "4. **Anti-Copy-Paste Verification**: Clipboard paste events into prediction and reflection fields were blocked at the UI layer and logged below.",
        "",
        "## 2. Completion & Verification Metrics",
        "",
        f"- **Sections Completed**: {len(completed)} of {len(sections)}",
        f"- **Verified Own-Words Reflections Saved**: {reflected_count} of {len(sections)}",
        f"- **Total Live Sandbox Executions Recorded**: {total_runs}",
        f"- **Blocked Clipboard Paste Attempts**: {total_pastes}",
        "",
        "## 3. Step-by-Step Predictions, Commands, Outputs & Reflections",
        ""
    ]

    for mod, sec in sections:
        sid = sec.get('id', '')
        scode = sec.get('section_code', '')
        stitle = sec.get('title', sid)
        rec_name = sec.get('recording_name') or mod.get('recording_name') or 'session'
        r = reflections.get(sid) if isinstance(reflections.get(sid), dict) else {}
        out = outputs.get(sid) if isinstance(outputs.get(sid), dict) else {}
        is_done = sid in completed
        is_reflected = bool(r.get('reflection_done'))

        lines.extend([
            f"### {scode}: {stitle} (`{sid}`)",
            f"- **Step Status**: {'Completed' if is_done else 'In Progress'} | **Reflection Verified**: {'Yes' if is_reflected else 'No'}",
            f"- **Asciinema Evidence File**: `evidence/michael/{rec_name}.cast` (`{rec_name}.txt`)",
            f"- **Command / Task Executed**: `{r.get('command_run') or sec.get('expected_command') or sec.get('task_type', 'interactive')}`",
            f"- **Execution Attempts**: {r.get('run_count', 0)} (Failed Runs: {r.get('failed_runs', 0)}, Check Attempts: {r.get('check_attempts', 0)}, Blocked Pastes: {r.get('paste_attempts', 0)})",
        ])
        if r.get('predicted_at'):
            lines.append(f"- **Predicted At**: `{r.get('predicted_at')}`")
        if r.get('reflected_at'):
            lines.append(f"- **Reflected At**: `{r.get('reflected_at')}`")
        if r.get('predict'):
            lines.extend(["", "**Learner Pre-Run Prediction (Own Words):**", f"> {str(r.get('predict')).strip().replace(chr(10), ' ')}"])
        if out.get('stdout'):
            snippet = str(out.get('stdout')).strip()[:1200]
            lines.extend(["", "**Recorded WSL Sandbox Output:**", "```text", snippet, "```"])
        if r.get('explain'):
            lines.extend(["", "**Learner Post-Run Explanation (Own Words):**", f"> {str(r.get('explain')).strip().replace(chr(10), ' ')}"])
        if r.get('common_error_note'):
            lines.extend(["", "**Learner Common Error Diagnosis & Fix (Own Words):**", f"> {str(r.get('common_error_note')).strip().replace(chr(10), ' ')}"])
        lines.append("")

    lines.extend([
        "## 4. Oral Walkthrough / Viva Readiness Questions",
        "",
        "Use these questions during a live code review or grading walkthrough to verify the learner's mastery of the deployed boilerplate:",
        "1. **Variables vs Parameters (`step1` & `step2`)**: Why did we use `@allowed(['dev', 'prod'])` on `param envName`, and how does string interpolation `'alp-${envName}-rg'` prevent naming drift?",
        "2. **POPIA Section 19 Storage Hardening (`step3`)**: Which three properties on `Microsoft.Storage/storageAccounts` enforce encryption in transit and block anonymous public blob access?",
        "3. **3-Tier Network Segmentation (`step4`)**: How does attaching `dataNsg` to `snet-data` (`10.10.3.0/24`) isolate database workloads from public internet traffic?",
        "4. **Ransomware & Audit Defense (`step5`)**: Why must `enablePurgeProtection: true` and `enableSoftDelete: true` both be active on Azure Key Vault, and why is Log Analytics set to 90 days?",
        "5. **Static Policy Verification (`landing-zone.bicep` & Checkov)**: Why must security remediations always be made in `architecture/landing-zone.bicep` rather than directly editing `landing-zone.json`?",
        "",
        "## 5. Sandbox File Checksums (SHA-256)",
        ""
    ])

    for root, _, files in sorted(os.walk(sandbox_dir)):
        for fn in sorted(files):
            if fn == 'EVIDENCE_MANIFEST.md':
                continue
            full_p = os.path.join(root, fn)
            rel_p = os.path.relpath(full_p, sandbox_dir)
            try:
                with open(full_p, 'rb') as bf:
                    fhash = hashlib.sha256(bf.read()).hexdigest()
                lines.append(f"- `{rel_p}`: `{fhash}`")
            except Exception:
                pass

    lines.extend(["", "## 6. Timestamped Activity Log", ""])
    for ev in activity_log[-200:]:
        if isinstance(ev, dict):
            detail = ev.get('detail') or {}
            cmd_part = f" | cmd=`{detail.get('command')}`" if detail.get('command') else ""
            st_part = f" | {detail.get('status')}" if detail.get('status') else ""
            lines.append(f"- `{ev.get('ts', '')}` | step=`{ev.get('step_id', '')}` | event=`{ev.get('type', '')}`{cmd_part}{st_part}")

    body_without_seal = "\n".join(lines) + "\n"
    manifest_sha = hashlib.sha256(body_without_seal.encode('utf-8')).hexdigest()
    final_body = body_without_seal + f"\n---\n**Manifest Integrity Seal (SHA-256)**: `{manifest_sha}`\n"

    manifest_path = os.path.join(sandbox_dir, 'EVIDENCE_MANIFEST.md')
    try:
        with open(manifest_path, 'w', encoding='utf-8') as mf:
            mf.write(final_body)
    except Exception:
        pass
    return final_body, manifest_sha, manifest_path


@projects_bp.route('/plugin/course', methods=['GET'])
@projects_bp.route('/course', methods=['GET'])
async def course_page():
    """Renders the dedicated Interactive Practical Course Application."""
    repo_root = _course_repo_root()
    course_id = _safe_course_id(request.args.get('course', 'alp_phase2_bicep_course'))
    course_title = request.args.get('title', 'ALP Phase 2 Interactive Practical Course')
    tpl_path = os.path.join(repo_root, 'sandbox', 'templates', 'course_application.html')
    if not os.path.isfile(tpl_path):
        return "Course template not found", 404
    with open(tpl_path, 'r', encoding='utf-8') as f:
        tpl_src = f.read()
    rendered = await render_template_string(tpl_src, course_id=course_id, course_title=course_title)
    return rendered, 200, {'Content-Type': 'text/html; charset=utf-8'}


@projects_bp.route('/api/course/data', methods=['GET'])
async def api_course_data():
    """Loads the structured course JSON and saved user progress."""
    course_id = _safe_course_id(request.args.get('course', 'alp_phase2_bicep_course'))
    course_obj, progress_obj = await asyncio.to_thread(_load_course_and_progress, course_id)
    if not course_obj:
        return jsonify({"ok": False, "error": f"Course '{course_id}' not found"}), 404
    return jsonify({"ok": True, "course": course_obj, "progress": progress_obj})


@projects_bp.route('/api/course/progress', methods=['GET', 'POST'])
async def api_course_progress():
    """Persists step-by-step course progress and updates the evidence manifest."""
    if request.method == 'GET':
        course_id = _safe_course_id(request.args.get('course', 'alp_phase2_bicep_course'))
        _, progress_obj = await asyncio.to_thread(_load_course_and_progress, course_id)
        return jsonify({"ok": True, "progress": progress_obj})

    body = await request.get_json() or {}
    course_id = _safe_course_id(body.get('course_id', 'alp_phase2_bicep_course'))
    progress = body.get('progress')
    if not isinstance(progress, dict):
        return jsonify({"ok": False, "error": "Invalid progress object"}), 400
    await asyncio.to_thread(_save_progress_sync, course_id, progress)
    _, manifest_sha, _ = await asyncio.to_thread(_generate_evidence_manifest, course_id, progress.get('learner_name'))
    return jsonify({"ok": True, "manifest_sha256": manifest_sha})


def _append_asciinema_event(cast_path: str, txt_path: str, rec_name: str, command: str, output_text: str) -> str:
    os.makedirs(os.path.dirname(cast_path), exist_ok=True)
    now_ts = int(time.time())
    date_str = time.strftime('%Y-%m-%d %H:%M:%S')
    if not os.path.isfile(cast_path) or os.path.getsize(cast_path) == 0:
        header = {
            "version": 2,
            "width": 110,
            "height": 32,
            "timestamp": now_ts,
            "title": f"ALP Phase 2 Sandbox - {rec_name}",
            "env": {"SHELL": "/bin/bash", "TERM": "xterm-256color"}
        }
        banner = (
            "======================================================\r\n"
            + (f"Assignee: learner  |  Session: {rec_name}  |  Date: {date_str}\r\n"
               "Environment: private Siraugga course sandbox (isolated, runs on the server)\r\n"
               if _is_learner_box(os.path.dirname(os.path.dirname(os.path.dirname(cast_path)))) else
               f"Assignee: michael  |  Session: {rec_name}  |  Date: {date_str}\r\n"
               "Environment: /home/michael/alp-env  |  Folder: /home/michael/alp-env/temp_phase2_sandbox\r\n")
            + "======================================================\r\n"
        )
        with open(cast_path, 'w', encoding='utf-8') as cf:
            cf.write(json.dumps(header) + '\n')
            cf.write(json.dumps([0.1, "o", banner]) + '\n')

    existing_lines = []
    try:
        with open(cast_path, 'r', encoding='utf-8') as cf:
            existing_lines = [ln for ln in cf.read().splitlines() if ln.strip()]
    except Exception:
        pass
    last_time = 0.2
    if len(existing_lines) > 1:
        try:
            last_ev = json.loads(existing_lines[-1])
            if isinstance(last_ev, list) and last_ev:
                last_time = float(last_ev[0])
        except Exception:
            pass

    t_cmd = round(last_time + 0.4, 3)
    t_out = round(last_time + 0.9, 3)
    norm_out = (output_text or '').replace('\r\n', '\n').replace('\n', '\r\n')
    if norm_out and not norm_out.endswith('\r\n'):
        norm_out += '\r\n'

    with open(cast_path, 'a', encoding='utf-8') as cf:
        cf.write(json.dumps([t_cmd, "o", f"$ {command}\r\n"]) + '\n')
        if norm_out:
            cf.write(json.dumps([t_out, "o", norm_out]) + '\n')

    asciinema_bin = '/home/michael/alp-env/bin/asciinema'
    transcript = ''
    if os.path.isfile(asciinema_bin):
        try:
            r = subprocess.run([asciinema_bin, 'cat', cast_path], capture_output=True, text=True, timeout=15)
            transcript = r.stdout
        except Exception:
            pass
    if not transcript:
        parts = []
        for ln in existing_lines[1:]:
            try:
                ev = json.loads(ln)
                if isinstance(ev, list) and len(ev) >= 3:
                    parts.append(str(ev[2]))
            except Exception:
                pass
        parts.append(f"$ {command}\n{output_text or ''}\n")
        transcript = ''.join(parts)

    try:
        with open(txt_path, 'w', encoding='utf-8') as tf:
            tf.write(transcript)
    except Exception:
        pass
    return transcript


def _execute_sandbox_sync(recording_name: str, command: str, bicep_file: str = None, bicep_code: str = None, prediction: str = None, learner_name: str = None) -> dict:
    sandbox_dir = _course_sandbox_dir()
    jailed = _is_learner_box(sandbox_dir)
    evidence_dir = os.path.join(sandbox_dir, 'evidence', 'michael')
    os.makedirs(evidence_dir, exist_ok=True)
    rec_name = re.sub(r'[^A-Za-z0-9_.-]', '', (recording_name or 'mod1_task1_variables').strip())
    if rec_name.endswith('.cast'):
        rec_name = rec_name[:-5]
    cast_path = os.path.join(evidence_dir, f'{rec_name}.cast')
    txt_path = os.path.join(evidence_dir, f'{rec_name}.txt')

    if bicep_file and bicep_code is not None:
        real_box = os.path.realpath(sandbox_dir)
        target_path = os.path.realpath(os.path.join(sandbox_dir, bicep_file))
        if os.path.commonpath([target_path, real_box]) != real_box:
            return {"ok": False, "returncode": 1, "output": "Denied path outside sandbox.", "transcript": ""}
        os.makedirs(os.path.dirname(target_path), exist_ok=True)
        with open(target_path, 'w', encoding='utf-8') as bf:
            bf.write(bicep_code)

    cmd = (command or '').strip()
    if prediction and not cmd.startswith('read-sandbox'):
        who = (learner_name or 'michael').strip() or 'michael'
        pred_clean = str(prediction).strip().replace('\r', ' ').replace('\n', ' ')
        _append_asciinema_event(
            cast_path,
            txt_path,
            rec_name,
            f"echo '[PRE-RUN PREDICTION by {who}]'",
            f"Prediction: {pred_clean}"
        )

    if cmd.startswith('rec-sandbox'):
        parts = cmd.split()
        if len(parts) > 1:
            rec_name = re.sub(r'[^A-Za-z0-9_.-]', '', parts[1])
            cast_path = os.path.join(evidence_dir, f'{rec_name}.cast')
            txt_path = os.path.join(evidence_dir, f'{rec_name}.txt')
        if os.path.isfile(cast_path):
            os.remove(cast_path)
        msg = (
            f"TEMPORARY SANDBOX RECORDING ACTIVE\n"
            f"Cast File : {os.path.relpath(cast_path, sandbox_dir) if jailed else cast_path}\n"
            f"Text Log  : {os.path.relpath(txt_path, sandbox_dir) if jailed else txt_path}\n"
            f"Watermark : Assignee: {'learner' if jailed else 'michael'} | Session: {rec_name}\n"
        )
        transcript = _append_asciinema_event(cast_path, txt_path, rec_name, cmd, msg)
        return {"ok": True, "returncode": 0, "output": msg, "transcript": transcript}

    if cmd.startswith('read-sandbox'):
        parts = cmd.split()
        if len(parts) > 1:
            rec_name = re.sub(r'[^A-Za-z0-9_.-]', '', parts[1])
            cast_path = os.path.join(evidence_dir, f'{rec_name}.cast')
            txt_path = os.path.join(evidence_dir, f'{rec_name}.txt')
        transcript = ''
        if os.path.isfile(txt_path):
            with open(txt_path, 'r', encoding='utf-8') as tf:
                transcript = tf.read()
        elif os.path.isfile(cast_path):
            r = subprocess.run(['/home/michael/alp-env/bin/asciinema', 'cat', cast_path], capture_output=True, text=True, timeout=15)
            transcript = r.stdout
        else:
            transcript = f"No recording found yet for {rec_name}. Run a step first to create {rec_name}.cast."
        return {"ok": True, "returncode": 0, "output": transcript, "transcript": transcript}

    wrapped_cmd = f"source {ADMIN_COURSE_SANDBOX}/sandbox_env.sh >/dev/null 2>&1 || true; {cmd}"
    if jailed:
        env = {'PATH': '/usr/bin:/bin', 'DEVCORE_COURSE_SANDBOX': os.path.realpath(sandbox_dir)}
        argv = [COURSE_JAIL, '/bin/bash', '-c', wrapped_cmd]
    else:
        env = os.environ.copy()
        env['VIRTUAL_ENV'] = '/home/michael/alp-env'
        env['PATH'] = f"/home/michael/alp-env/bin:/home/michael/.local/bin:/home/michael/.azure/bin:{env.get('PATH', '')}"
        argv = ['/bin/bash', '-c', wrapped_cmd]
    proc = subprocess.run(
        argv,
        cwd=sandbox_dir,
        env=env,
        capture_output=True,
        text=True,
        timeout=75
    )
    combined_out = (proc.stdout or '') + (('\n' + proc.stderr) if proc.stderr else '')
    combined_out = combined_out.strip() or '(Command completed with exit code 0 and no console output)'
    transcript = _append_asciinema_event(cast_path, txt_path, rec_name, cmd, combined_out)
    return {
        "ok": proc.returncode == 0,
        "returncode": proc.returncode,
        "output": combined_out,
        "transcript": transcript
    }


@projects_bp.route('/api/course/execute', methods=['POST'])
async def api_course_execute():
    """Runs one course step command inside WSL alp-env and records it to asciinema.

    Security invariant: this endpoint is publicly reachable, so it only runs commands defined in
    the course JSON (plus rec-sandbox / read-sandbox with a safe recording name), and Bicep code may
    only be written to a step's own bicep_file. Anything else is rejected before reaching a shell."""
    body = await request.get_json() or {}
    course_id = _safe_course_id(body.get('course_id', 'alp_phase2_bicep_course'))
    rec_name = body.get('recording_name') or 'mod1_task1_variables'
    command = ' '.join(str(body.get('command') or '').split())
    bicep_file = body.get('bicep_file')
    bicep_code = body.get('bicep_code')
    prediction = body.get('prediction')
    learner_name = body.get('learner_name')

    course_obj, _ = await asyncio.to_thread(_load_course_and_progress, course_id)
    sections = [s for m in (course_obj or {}).get('modules', []) for s in m.get('sections', [])]
    allowed_cmds = {' '.join(str(s['expected_command']).split()) for s in sections if s.get('expected_command')}
    allowed_files = {s['bicep_file'] for s in sections if s.get('bicep_file')}
    is_builtin = re.fullmatch(r'(?:rec|read)-sandbox [A-Za-z0-9_.-]{1,64}', command) is not None
    if not (command in allowed_cmds or is_builtin) or (bicep_file and bicep_file not in allowed_files):
        return jsonify({
            "ok": False,
            "returncode": 1,
            "output": "That command isn't part of this course step. Use the command shown for the step and press Run again.",
            "transcript": ""
        }), 403

    try:
        res = await asyncio.to_thread(
            _execute_sandbox_sync,
            rec_name,
            command,
            bicep_file,
            bicep_code,
            prediction,
            learner_name
        )
        return jsonify(res)
    except Exception as e:
        return jsonify({"ok": False, "returncode": 1, "output": str(e), "transcript": ""}), 500


def _record_reflection_sync(body: dict) -> dict:
    course_id = _safe_course_id(body.get('course_id', 'alp_phase2_bicep_course'))
    step_id = (body.get('step_id') or '').strip()
    rec_name = re.sub(r'[^A-Za-z0-9_.-]', '', (body.get('recording_name') or 'mod1_task1_variables').strip())
    if rec_name.endswith('.cast'):
        rec_name = rec_name[:-5]
    learner = (body.get('learner_name') or 'michael').strip() or 'michael'
    predict_txt = (body.get('predict') or '').strip()
    explain_txt = (body.get('explain') or '').strip()
    error_txt = (body.get('common_error_note') or '').strip()

    sandbox_dir = _course_sandbox_dir()
    evidence_dir = os.path.join(sandbox_dir, 'evidence', 'michael')
    os.makedirs(evidence_dir, exist_ok=True)
    cast_path = os.path.join(evidence_dir, f'{rec_name}.cast')
    txt_path = os.path.join(evidence_dir, f'{rec_name}.txt')

    reflection_summary = (
        f"[POST-RUN REFLECTION SAVED | Step: {step_id} | Learner: {learner}]\n"
        f"  Prediction : {predict_txt}\n"
        f"  Explanation: {explain_txt}\n"
        f"  Error & Fix: {error_txt}"
    )
    transcript = _append_asciinema_event(
        cast_path,
        txt_path,
        rec_name,
        f"echo '[REFLECTION VERIFIED: {step_id}]'",
        reflection_summary
    )

    progress = body.get('progress')
    if not isinstance(progress, dict):
        _, progress = _load_course_and_progress(course_id)
    progress['learner_name'] = learner
    reflections = progress.setdefault('reflections', {})
    step_ref = reflections.setdefault(step_id, {})
    if predict_txt:
        step_ref['predict'] = predict_txt
    step_ref['explain'] = explain_txt
    step_ref['common_error_note'] = error_txt
    step_ref['reflection_done'] = True
    step_ref['reflected_at'] = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
    _save_progress_sync(course_id, progress)

    _, manifest_sha, manifest_path = _generate_evidence_manifest(course_id, learner)
    return {
        "ok": True,
        "step_id": step_id,
        "manifest_sha256": manifest_sha,
        "manifest_path": manifest_path,
        "transcript": transcript
    }


@projects_bp.route('/api/course/reflect', methods=['POST'])
async def api_course_reflect():
    """Records a learner step reflection to the asciinema evidence log and updates EVIDENCE_MANIFEST.md."""
    body = await request.get_json() or {}
    try:
        res = await asyncio.to_thread(_record_reflection_sync, body)
        return jsonify(res)
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


def _build_export_bundle_sync(course_id: str, learner_name: str = None) -> tuple:
    sandbox_dir = _course_sandbox_dir()
    manifest_body, manifest_sha, _ = _generate_evidence_manifest(course_id, learner_name)
    mem_zip = io.BytesIO()
    cid = _safe_course_id(course_id)
    root_folder = f"{cid}_boilerplate_and_evidence"
    with zipfile.ZipFile(mem_zip, mode='w', compression=zipfile.ZIP_DEFLATED) as zf:
        for root, _, files in sorted(os.walk(sandbox_dir)):
            for fn in sorted(files):
                full_p = os.path.join(root, fn)
                rel_p = os.path.relpath(full_p, sandbox_dir)
                arcname = os.path.join(root_folder, rel_p)
                try:
                    zf.write(full_p, arcname=arcname)
                except Exception:
                    pass
    mem_zip.seek(0)
    return mem_zip.getvalue(), manifest_body, manifest_sha


@projects_bp.route('/api/course/export', methods=['GET', 'POST'])
async def api_course_export():
    """Exports the complete sandbox environment boilerplate, asciinema recordings, and EVIDENCE_MANIFEST.md."""
    if request.method == 'POST':
        body = await request.get_json() or {}
        course_id = _safe_course_id(body.get('course_id', 'alp_phase2_bicep_course'))
        learner_name = body.get('learner_name')
        fmt = (body.get('format') or 'zip').lower()
        progress = body.get('progress')
        if isinstance(progress, dict):
            await asyncio.to_thread(_save_progress_sync, course_id, progress)
    else:
        course_id = _safe_course_id(request.args.get('course', 'alp_phase2_bicep_course'))
        learner_name = request.args.get('learner')
        fmt = (request.args.get('format') or 'zip').lower()

    zip_bytes, manifest_body, manifest_sha = await asyncio.to_thread(_build_export_bundle_sync, course_id, learner_name)
    if fmt in ('md', 'markdown', 'manifest'):
        headers = {
            'Content-Type': 'text/markdown; charset=utf-8',
            'Content-Disposition': f'attachment; filename="EVIDENCE_MANIFEST_{course_id}.md"',
            'X-Evidence-SHA256': manifest_sha
        }
        return Response(manifest_body, status=200, headers=headers)

    headers = {
        'Content-Type': 'application/zip',
        'Content-Disposition': f'attachment; filename="{course_id}_boilerplate_and_evidence.zip"',
        'X-Evidence-SHA256': manifest_sha
    }
    return Response(zip_bytes, status=200, headers=headers)


@projects_bp.route('/api/course/requirements', methods=['POST'])
async def api_course_requirements():
    """Validates per-step requirements and builds deterministic requirements.lock.txt and VM specs."""
    from core import course_vault
    body = await request.get_json() or {}
    status_code, payload = await asyncio.to_thread(course_vault.dispatch, 'requirements', body)
    return jsonify(payload), status_code


@projects_bp.route('/api/course/workspace/<op>', methods=['POST'])
async def api_course_workspace(op: str):
    """Zero-knowledge E2EE group workspace endpoint (ciphertext, salts, and wrapped keys only)."""
    from core import course_vault
    body = await request.get_json() or {}
    status_code, payload = await asyncio.to_thread(course_vault.dispatch, op, body)
    return jsonify(payload), status_code


@projects_bp.route('/api/cards/triggers', methods=['GET'])
async def api_cards_triggers():
    """Returns command triggers handled directly by backend response cards."""
    from core import response_cards
    return jsonify(response_cards.get_triggers())


@projects_bp.route('/api/cards/resolve', methods=['POST'])
async def api_cards_resolve():
    """Resolves a prompt or topic into a complete server-rendered response card payload."""
    from core import response_cards
    body = await request.get_json(silent=True) or {}
    headers_copy = dict(request.headers)
    remote_addr = request.remote_addr or ''
    status_code, payload = await asyncio.to_thread(
        response_cards.resolve_card,
        body,
        current_app.security_mgr,
        headers_copy,
        remote_addr,
    )
    return jsonify(payload), status_code


@projects_bp.route('/api/cards/featured', methods=['GET'])
async def api_cards_featured():
    """Returns the featured response card payload from server configuration."""
    from core import response_cards
    payload = await asyncio.to_thread(response_cards.build_featured_card)
    return jsonify(payload)
