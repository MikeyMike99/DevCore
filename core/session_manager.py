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
            with open(self.meta_file, 'w', encoding='utf-8') as f:
                json.dump(self.ownership, f, indent=2)
        except Exception as e:
            print(f"[SessionManager] Failed to save session ownership: {e}")

    def register_session_owner(self, conv_id: str, username: str, project_name: str = None):
        if not conv_id or not username:
            return
        if conv_id not in self.ownership:
            self.ownership[conv_id] = {
                "owner": username,
                "project": project_name,
                "created_at": os.path.getmtime(os.path.join(self.brain_dir, conv_id)) if os.path.exists(os.path.join(self.brain_dir, conv_id)) else 0
            }
            self._save_ownership()

    def can_user_access_session(self, conv_id: str, user: dict = None) -> bool:
        if not user:
            return False
        # Admin can access all sessions
        if user.get("role") == "admin":
            return True

        # Check recorded ownership
        record = self.ownership.get(conv_id)
        if record:
            return record.get("owner") == user.get("username")

        # Unclaimed legacy sessions are restricted to admin only
        return False

    def list_conversations(self, project_name=None, user=None):
        valid_ids = []
        is_admin = user and user.get("role") == "admin"
        
        for conv_id, meta in self.ownership.items():
            # If admin, show active project AND archived sessions
            if is_admin:
                if project_name and meta.get("project") != project_name and meta.get("project") != "archived_deletions":
                    continue
            else:
                if project_name and meta.get("project") != project_name:
                    continue
                if meta.get("owner") != user.get("username"):
                    continue
            valid_ids.append(conv_id)

        results = []
        for conv_id in valid_ids:
            title = f"Session {conv_id[:6]}"
            transcript_path = os.path.join(self.brain_dir, conv_id, ".system_generated", "logs", "transcript.jsonl")
            if os.path.exists(transcript_path):
                try:
                    with open(transcript_path, 'r', encoding='utf-8') as f:
                        for line in f:
                            data = json.loads(line)
                            if data.get("type") == "USER_INPUT":
                                snippet = data.get("content", "").replace("<USER_REQUEST>", "").replace("</USER_REQUEST>", "").strip()[:30]
                                if snippet:
                                    title = f"{snippet}..."
                                break
                except Exception:
                    pass
            results.append({"id": conv_id, "title": title})
        return results

    def delete_project_sessions(self, project_name, user):
        import shutil
        to_delete = []
        for conv_id, meta in list(self.ownership.items()):
            if meta.get("project") == project_name:
                if user.get("role") == "admin" or meta.get("owner") == user.get("username"):
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
                            items.append({"sender": "user", "text": data.get("content", "")})
                        elif data.get("type") == "PLANNER_RESPONSE":
                            items.append({"sender": "agent", "markdown": data.get("content", "")})
                    except Exception:
                        pass
        except Exception as e:
            print(f"[SessionManager] Error reading transcript for {conv_id}: {e}")

        return items[-50:]
