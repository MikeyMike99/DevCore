import os
import json

class SessionManager:
    """
    Manages discovery, isolation, and parsing of Antigravity conversation sessions.
    Enforces multi-tenant data boundaries so non-admin users cannot snoop on
    conversations created by other developers or administrators.
    """
    def __init__(self, brain_dir=None, base_dir=None):
        self.brain_dir = brain_dir or os.path.expanduser("~/.gemini/antigravity-cli/brain")
        self.base_dir = base_dir or os.path.dirname(os.path.abspath(__file__))
        os.makedirs(self.brain_dir, exist_ok=True)
        self.meta_file = os.path.join(self.brain_dir, "session_ownership.json")
        self.ownership = self._load_ownership()

    def reinit(self):
        self.brain_dir = os.path.expanduser("~/.gemini/antigravity-cli/brain")
        self.base_dir = os.path.dirname(os.path.abspath(__file__))
        os.makedirs(self.brain_dir, exist_ok=True)
        self.meta_file = os.path.join(self.brain_dir, "session_ownership.json")
        self.ownership = self._load_ownership()

    def _load_ownership(self):
        if os.path.exists(self.meta_file):
            try:
                with open(self.meta_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                pass
        return {}

    def _save_ownership(self):
        try:
            import sys
            import os
            sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
            from security.mantrap import SemanticMantrap
            import logging
            
            # Utilize the Semantic Mantrap for database concurrency
            with SemanticMantrap.execution_chamber(self.meta_file, "CoreEngine_SessionManager"):
                with open(self.meta_file, 'w', encoding='utf-8') as f:
                    json.dump(self.ownership, f, indent=2)
                    
        except Exception as e:
            import logging
            logging.error(f"[SessionManager] Failed to save session ownership: {e}")

    def _is_admin(self, user: dict = None) -> bool:
        if not user:
            return False
        return user.get("role") in ("admin", "super_admin", "super admin", "Tier5_SysAdmin")

    def _clean_prompt_text(self, text: str) -> str:
        if not text:
            return ""
        import re
        text = re.sub(r'<SYSTEM_MESSAGE>[\s\S]*?</SYSTEM_MESSAGE>', '', text, flags=re.IGNORECASE)
        text = re.sub(r'<ADDITIONAL_METADATA>[\s\S]*?</ADDITIONAL_METADATA>', '', text, flags=re.IGNORECASE)
        text = re.sub(r'<USER_SETTINGS_CHANGE>[\s\S]*?</USER_SETTINGS_CHANGE>', '', text, flags=re.IGNORECASE)
        text = re.sub(r'<MID_TASK_STEERING_UPDATE>[\s\S]*?</MID_TASK_STEERING_UPDATE>', '', text, flags=re.IGNORECASE)
        text = re.sub(r'<CONTEXT_SUMMARY>[\s\S]*?</CONTEXT_SUMMARY>', '', text, flags=re.IGNORECASE)
        text = re.sub(r'</?USER_REQUEST>', '', text, flags=re.IGNORECASE)
        text = re.sub(r'\[(?:STEER_NOW|QUEUE_NEXT)\]', '', text, flags=re.IGNORECASE)
        text = re.sub(r'\s+', ' ', text).strip()
        return text

    def register_session_owner(self, conv_id: str, username: str, project_name: str = None):
        if not conv_id or not username:
            return
        import time
        self.ownership = self._load_ownership()
        now_ts = time.time()
        conv_dir = os.path.join(self.brain_dir, conv_id)
        default_created = os.path.getmtime(conv_dir) if os.path.exists(conv_dir) else now_ts
        if conv_id not in self.ownership:
            self.ownership[conv_id] = {
                "owner": username,
                "project": project_name,
                "created_at": default_created,
                "updated_at": now_ts
            }
        else:
            self.ownership[conv_id]["updated_at"] = now_ts
            if project_name and not self.ownership[conv_id].get("project"):
                self.ownership[conv_id]["project"] = project_name
        self._save_ownership()

    def can_user_access_session(self, conv_id: str, user: dict = None) -> bool:
        self.ownership = self._load_ownership()
        if not user:
            try:
                from core.routes.auth import get_current_user
                user = get_current_user()
            except Exception:
                pass
        if not user:
            return False
        # Admin / Super Admin can access all sessions
        if self._is_admin(user):
            return True

        # Check recorded ownership
        record = self.ownership.get(conv_id)
        if record:
            return record.get("owner") == user.get("username")

        # Unclaimed legacy sessions are restricted to admin only
        return False

    def list_conversations(self, project_name=None, user=None, limit=None):
        self.ownership = self._load_ownership()
        valid_ids = []
        is_admin = self._is_admin(user)
        excluded_projects = {
            'venv', '__pycache__', 'templates', 'static', 'sandbox',
            'node_modules', 'site-packages', 'Cryptodome', 'pyzipper',
            'Zip-Files', 'Offline_Crack_Lab', 'Online_Brute_Lab'
        }
        
        for conv_id, meta in self.ownership.items():
            proj = meta.get("project")
            if proj == "archived_deletions":
                continue
            if proj in excluded_projects:
                proj = None
            if project_name:
                if proj != project_name:
                    continue
            else:
                if proj not in (None, "", "default"):
                    continue
            if not is_admin:
                if not user or meta.get("owner") != user.get("username"):
                    continue
            valid_ids.append(conv_id)

        generic_prompts = {
            "proceed", "continue", "yes", "ok", "okay", "hello", "helllo",
            "hi", "say hello", "hello world", "help"
        }

        scored_results = []
        for conv_id in valid_ids:
            meta = self.ownership.get(conv_id, {})
            title = meta.get("custom_title") or f"Session {conv_id[:6]}"
            summary = "No summary available."
            transcript_path = os.path.join(self.brain_dir, conv_id, ".system_generated", "logs", "transcript.jsonl")
            if not os.path.exists(transcript_path):
                transcript_path = os.path.join(self.brain_dir, conv_id, "transcript.jsonl")

            sort_ts = meta.get("updated_at") or meta.get("created_at") or 0
            if os.path.exists(transcript_path):
                try:
                    file_mtime = os.path.getmtime(transcript_path)
                    if file_mtime > sort_ts:
                        sort_ts = file_mtime
                    user_prompts = []
                    agent_responses = []
                    with open(transcript_path, 'r', encoding='utf-8', errors='replace') as f:
                        for line in f:
                            try:
                                data = json.loads(line)
                            except Exception:
                                continue
                            dtype = data.get("type")
                            if dtype == "USER_INPUT":
                                cleaned = self._clean_prompt_text(data.get("content", ""))
                                if cleaned:
                                    user_prompts.append(cleaned)
                            elif dtype == "PLANNER_RESPONSE":
                                resp_txt = (data.get("content") or "").strip()
                                if resp_txt:
                                    agent_responses.append(resp_txt)

                    if user_prompts and not meta.get("custom_title"):
                        meaningful = [
                            p for p in user_prompts
                            if p.lower().rstrip(".!?") not in generic_prompts
                            and not p.lower().startswith("you asked: heading level")
                            and len(p) > 4
                        ]
                        chosen_prompt = meaningful[0] if meaningful else user_prompts[0]
                        snippet = chosen_prompt[:42].strip()
                        title = f"{snippet}..." if len(chosen_prompt) > 42 else snippet

                    if user_prompts or agent_responses:
                        first_q = user_prompts[0][:120] if user_prompts else "N/A"
                        latest_q = user_prompts[-1][:120] if user_prompts else "N/A"
                        latest_a = agent_responses[-1][:200].replace("\n", " ") if agent_responses else "Awaiting response"
                        summary = (
                            f"Turns: {len(user_prompts)} | "
                            f"Initial Topic: {first_q} | "
                            f"Latest Prompt: {latest_q} | "
                            f"Latest Outcome: {latest_a}"
                        )
                except Exception:
                    pass

            scored_results.append((sort_ts, {
                "id": conv_id,
                "title": title,
                "summary": summary,
                "updated_at": sort_ts,
                "custom_renamed": bool(meta.get("custom_title"))
            }))
            
        # Sort strictly newest-first (most recently active at the top)
        scored_results.sort(key=lambda item: item[0], reverse=True)
        results = [item[1] for item in scored_results]
        
        has_more = False
        if limit is not None and limit > 0:
            has_more = len(results) > limit
            results = results[:limit]
            
        return results, has_more

    def rename_session(self, conv_id: str, new_title: str, user: dict = None) -> bool:
        if not conv_id or not new_title or not new_title.strip():
            return False
        if not self.can_user_access_session(conv_id, user):
            return False
        import time
        self.ownership = self._load_ownership()
        clean_title = self._clean_prompt_text(new_title.strip())
        if not clean_title:
            return False
        if conv_id not in self.ownership:
            self.ownership[conv_id] = {
                "owner": user.get("username", "admin") if user else "admin",
                "project": None,
                "custom_title": clean_title,
                "created_at": time.time(),
                "updated_at": time.time()
            }
        else:
            self.ownership[conv_id]["custom_title"] = clean_title
        self._save_ownership()
        return True

    def delete_session(self, conv_id, user):
        if not self.can_user_access_session(conv_id, user):
            return False
        print(f"[SessionManager] Archiving single session {conv_id} to admin access instead of deleting.")
        if conv_id in self.ownership:
            self.ownership[conv_id]["owner"] = "admin"
            self.ownership[conv_id]["project"] = "archived_deletions"
        else:
            self.ownership[conv_id] = {
                "owner": "admin",
                "project": "archived_deletions"
            }
        self._save_ownership()
        return True

    def delete_project_sessions(self, project_name, user):
        self.ownership = self._load_ownership()
        to_delete = []
        is_admin = self._is_admin(user)
        excluded_projects = {
            'venv', '__pycache__', 'templates', 'static', 'sandbox',
            'node_modules', 'site-packages', 'Cryptodome', 'pyzipper',
            'Zip-Files', 'Offline_Crack_Lab', 'Online_Brute_Lab'
        }
        for conv_id, meta in list(self.ownership.items()):
            proj = meta.get("project")
            if proj == "archived_deletions":
                continue
            if proj in excluded_projects:
                proj = None
            matches_proj = (proj == project_name) if project_name else (proj in (None, "", "default"))
            if matches_proj:
                if is_admin or (user and meta.get("owner") == user.get("username")):
                    to_delete.append(conv_id)

        for conv_id in to_delete:
            # Instead of deleting, we log and protect under admin access
            print(f"[SessionManager] Archiving session {conv_id} to admin access instead of deleting.")
            self.ownership[conv_id]["owner"] = "admin"
            self.ownership[conv_id]["project"] = "archived_deletions"
        self._save_ownership()

    def get_conversation_transcript(self, conv_id: str, user: dict = None):
        if not conv_id or '..' in conv_id or '/' in conv_id or '\\' in conv_id:
            raise ValueError("Invalid conversation ID")

        if not self.can_user_access_session(conv_id, user):
            raise PermissionError("Access Denied: You do not have permission to view this conversation session")

        transcript_path = os.path.join(self.brain_dir, conv_id, ".system_generated", "logs", "transcript.jsonl")
        if not os.path.exists(transcript_path):
            transcript_path = os.path.join(self.brain_dir, conv_id, "transcript.jsonl")

        if not os.path.exists(transcript_path):
            return []

        items = []
        try:
            with open(transcript_path, 'r', encoding='utf-8', errors='replace') as f:
                for line in f:
                    try:
                        data = json.loads(line)
                        if data.get("type") == "USER_INPUT":
                            cleaned_user = self._clean_prompt_text(data.get("content", ""))
                            if cleaned_user:
                                items.append({"sender": "user", "text": cleaned_user})
                        elif data.get("type") == "PLANNER_RESPONSE":
                            md = (data.get("content") or "").strip()
                            if md:
                                items.append({"sender": "agent", "markdown": md})
                    except Exception:
                        pass
        except Exception as e:
            print(f"[SessionManager] Error reading transcript for {conv_id}: {e}")

        return items[-50:]

    def get_session_turn_count(self, conv_id: str) -> int:
        if not conv_id or '..' in conv_id or '/' in conv_id or '\\' in conv_id:
            return 0
        transcript_path = os.path.join(self.brain_dir, conv_id, ".system_generated", "logs", "transcript.jsonl")
        if not os.path.exists(transcript_path):
            transcript_path = os.path.join(self.brain_dir, conv_id, "transcript.jsonl")
        if not os.path.exists(transcript_path):
            return 0
        turns = 0
        try:
            with open(transcript_path, 'r', encoding='utf-8', errors='replace') as f:
                for line in f:
                    if not line.strip():
                        continue
                    try:
                        data = json.loads(line)
                        if data.get("type") == "USER_INPUT":
                            turns += 1
                    except Exception:
                        pass
        except Exception:
            pass
        return turns

    def generate_continuation_briefing(self, conv_id: str, workspace_path: str = None) -> str:
        """
        Extracts key working state, active workspace, recent user intents,
        recently touched files, and operational rules from the expiring session
        without making any external LLM calls.
        """
        if not conv_id:
            return ""
        
        self.ownership = self._load_ownership()
        meta = self.ownership.get(conv_id, {})
        project_name = meta.get("project") or "DevCore"
        
        workspace_dir = workspace_path or "/mnt/c/Users/michael/Documents/DevCore/playground"
        
        transcript_path = os.path.join(self.brain_dir, conv_id, ".system_generated", "logs", "transcript.jsonl")
        if not os.path.exists(transcript_path):
            transcript_path = os.path.join(self.brain_dir, conv_id, "transcript.jsonl")
            
        user_prompts = []
        agent_outcomes = []
        files_touched = set()
        
        if os.path.exists(transcript_path):
            try:
                with open(transcript_path, 'r', encoding='utf-8', errors='replace') as f:
                    for line in f:
                        if not line.strip():
                            continue
                        try:
                            data = json.loads(line)
                        except Exception:
                            continue
                        
                        dtype = data.get("type")
                        if dtype == "USER_INPUT":
                            cleaned = self._clean_prompt_text(data.get("content", ""))
                            if cleaned and len(cleaned) > 3:
                                user_prompts.append(cleaned)
                        elif dtype == "PLANNER_RESPONSE":
                            resp_txt = (data.get("content") or "").strip()
                            if resp_txt and len(resp_txt) > 10:
                                agent_outcomes.append(resp_txt)
                                
                        for call in data.get("tool_calls", []):
                            args = call.get("args") or {}
                            f_cand = (
                                args.get("TargetFile")
                                or args.get("target_file")
                                or args.get("AbsolutePath")
                                or args.get("File")
                            )
                            if f_cand and isinstance(f_cand, str) and not f_cand.endswith((".log", ".tmp")):
                                files_touched.add(os.path.basename(f_cand).replace('"', "").replace("'", "").strip())
            except Exception as e:
                print(f"[SessionManager] Warning during briefing extraction: {e}")
                
        recent_goals_str = ""
        meaningful_prompts = user_prompts[-3:] if user_prompts else ["Continue active software engineering task."]
        for p in meaningful_prompts:
            clean_p = p[:100].strip()
            recent_goals_str += f"  • {clean_p}\n"
            
        recent_files_str = ""
        if files_touched:
            for fn in list(files_touched)[-5:]:
                recent_files_str += f"  • {fn}\n"
        else:
            recent_files_str = "  • None recorded in recent turns.\n"
            
        latest_outcome = "Ready to proceed."
        if agent_outcomes:
            latest_outcome = agent_outcomes[-1][:200].replace("\n", " ").strip()
            
        briefing = (
            "<SESSION_CONTINUATION_CONTEXT>\n"
            "[AUTOMATIC SESSION ROLLOVER: The previous session was archived to maintain peak responsiveness and eliminate token bloat.]\n"
            f"- Active Workspace Directory: {workspace_dir}\n"
            f"- Active Project: {project_name}\n"
            "- Recent Accomplished Goals:\n"
            f"{recent_goals_str}"
            "- Recently Touched Files:\n"
            f"{recent_files_str}"
            f"- Latest Context / Outcome: {latest_outcome}\n"
            "- Operational Rules: Screen-reader optimized responses; concise markdown; clickable file:// links; clean workspace protocol (no lingering scratch files).\n"
            "</SESSION_CONTINUATION_CONTEXT>"
        )
        return briefing


_SYNCING_ROUTES = False

def _sync_live_blueprint_routes():
    global _SYNCING_ROUTES
    if _SYNCING_ROUTES:
        return
    _SYNCING_ROUTES = True
    try:
        import sys
        import importlib
        main_mod = sys.modules.get("__main__") or sys.modules.get("core.server")
        live_app = getattr(main_mod, "app", None) if main_mod else None
        if live_app is None or not hasattr(live_app, "view_functions"):
            return

        # Reload security helper modules if present
        for sec_sub in ("security.raugus_resolver", "security.security_headers", "security.vfs"):
            if sec_sub in sys.modules:
                try:
                    reloaded_mod = importlib.reload(sys.modules[sec_sub])
                    if sec_sub == "security.security_headers" and hasattr(reloaded_mod, "apply_security_headers"):
                        after_funcs = getattr(live_app, "after_request_funcs", {}).get(None, [])
                        for idx, fn in enumerate(after_funcs):
                            if getattr(fn, "__name__", "") == "apply_security_headers":
                                after_funcs[idx] = reloaded_mod.apply_security_headers
                    elif sec_sub == "security.vfs" and hasattr(reloaded_mod, "vfs"):
                        reloaded_mod.vfs.load()
                except Exception:
                    pass

        if "core.routes.system" in sys.modules:
            sys_mod = importlib.reload(sys.modules["core.routes.system"])
            for fn_name in ("trigger_hot_patch", "reload_system", "csp_report", "api_trigger_red_team", "api_bootstrap_preflight"):
                if hasattr(sys_mod, fn_name):
                    live_app.view_functions[f"system_bp.{fn_name}"] = getattr(sys_mod, fn_name)
            if hasattr(sys_mod, "api_bootstrap_preflight") and "system_bp.api_bootstrap_preflight" not in [r.endpoint for r in live_app.url_map.iter_rules()]:
                try:
                    live_app.add_url_rule(
                        '/api/bootstrap/preflight',
                        endpoint='system_bp.api_bootstrap_preflight',
                        view_func=sys_mod.api_bootstrap_preflight,
                        methods=['GET', 'POST']
                    )
                except Exception:
                    pass
            if hasattr(sys_mod, "execute_hot_patch_sequence") and main_mod:
                main_mod.execute_hot_patch_sequence = sys_mod.execute_hot_patch_sequence

        if "core.routes.projects" in sys.modules:
            proj_mod = importlib.reload(sys.modules["core.routes.projects"])
            for fn_name in (
                "list_projects",
                "create_project",
                "set_active_project",
                "list_conversations",
                "get_conversation",
                "delete_conversation",
                "clear_project_sessions",
                "rename_conversation",
            ):
                if hasattr(proj_mod, fn_name):
                    live_app.view_functions[f"projects_bp.{fn_name}"] = getattr(proj_mod, fn_name)
            if "projects_bp.rename_conversation" not in [r.endpoint for r in live_app.url_map.iter_rules()]:
                try:
                    live_app.add_url_rule(
                        '/api/conversations/<conv_id>/rename',
                        endpoint='projects_bp.rename_conversation',
                        view_func=proj_mod.rename_conversation,
                        methods=['POST']
                    )
                except Exception:
                    pass

        if "core.routes.auth" in sys.modules:
            auth_mod = importlib.reload(sys.modules["core.routes.auth"])
            for ep in list(live_app.view_functions.keys()):
                if ep.startswith("auth_bp."):
                    fn_name = ep.split(".", 1)[1]
                    if hasattr(auth_mod, fn_name):
                        live_app.view_functions[ep] = getattr(auth_mod, fn_name)

        if "core.routes.files" in sys.modules:
            files_mod = importlib.reload(sys.modules["core.routes.files"])
            for ep in list(live_app.view_functions.keys()):
                if ep.startswith("files_bp."):
                    fn_name = ep.split(".", 1)[1]
                    if hasattr(files_mod, fn_name):
                        live_app.view_functions[ep] = getattr(files_mod, fn_name)
    except Exception as e:
        print(f"[SessionManager] Route sync warning: {e}")
    finally:
        _SYNCING_ROUTES = False


_sync_live_blueprint_routes()
