import os
import uuid
import time
import mimetypes

class SecurityManager:
    """
    Role-Based Access Control (RBAC) and Path Sandboxing for In-Game Development.
    
    Roles:
      - 'admin': Full access to all projects, core engine scripts, and system logs.
      - 'gamedev': Restricted to assigned game project folders. Cannot view core scripts, logs, or parent paths.
      - 'modder': Read-only access to safe workspace files inside assigned projects.
      
    Tiers:
      - SAFE_WORKSPACE: Game scripts, configs, JSON states, Lua scripts (Read/Write for devs)
      - CORE_ENGINE: Orchestration, server, and security scripts (Admin only)
      - ADMIN_LOG: System and daemon execution logs (Admin only)
      - FORBIDDEN: System files, venv, git, env vars, traversal attempts (Hard blocked)
    """

    ROLE_ADMIN = "admin"
    ROLE_GAMEDEV = "gamedev"
    ROLE_MODDER = "modder"

    TIER_SAFE_WORKSPACE = "safe_workspace"
    TIER_CORE_ENGINE = "core_engine"
    TIER_ADMIN_LOG = "admin_log"
    TIER_FORBIDDEN = "forbidden"

    CORE_FILES = {
        "server.py", "agent_manager.py", "project_manager.py",
        "session_manager.py", "security_manager.py", "apply_upgrade.sh",
        "server_new.py", "test.js", "test_ws.py"
    }

    CORE_DIRECTORIES = {
        "core", "security", "sandbox", "plugins", "docs", 
        "archives", "backups", "scripts"
    }

    ALLOWED_EXTENSIONS = {
        ".py", ".json", ".lua", ".js", ".ts", ".md", ".txt",
        ".yaml", ".yml", ".xml", ".csv", ".ini", ".cfg", ".log", ".html", ".css"
    }

    FORBIDDEN_NAMES = {"venv", "__pycache__", ".git", ".env", ".system_generated"}

    # Test accounts for red teaming
    TEST_USERS = {
        "admin": {
            "password": "admin",
            "role": ROLE_ADMIN,
            "name": "Michael (Admin)",
            "allowed_projects": ["*"]
        },
        "dev": {
            "password": "dev",
            "role": ROLE_GAMEDEV,
            "name": "Game Developer",
            "allowed_projects": ["game_demo", "npc_quest"]
        },
        "dev_tester": {
            "password": "dev",
            "role": ROLE_GAMEDEV,
            "name": "Game Developer",
            "allowed_projects": ["game_demo", "npc_quest"]
        },
        "mod": {
            "password": "mod",
            "role": ROLE_MODDER,
            "name": "Community Modder",
            "allowed_projects": ["game_demo"]
        },
        "modder": {
            "password": "mod",
            "role": ROLE_MODDER,
            "name": "Community Modder",
            "allowed_projects": ["game_demo"]
        }
    }

    def __init__(self, base_dir=None):
        # Resolve to the root of DevCore instead of the security/ folder
        self.base_dir = base_dir or os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        self.sessions = {}  # token -> {"username": ..., "role": ..., "created_at": ...}
        self.sessions_file = os.path.join(self.base_dir, "sessions.json")
        self._local_sec = None
        self._load_sessions()

    def _get_security(self):
        if self._local_sec is None:
            try:
                from local_security import LocalSecurity
                self._local_sec = LocalSecurity()
            except Exception as e:
                print(f"[Security] LocalSecurity init failed. Error: {e}")
                class Dummy:
                    def scrub_text(self, t): return t
                self._local_sec = Dummy()
        return self._local_sec

    def _load_sessions(self):
        if os.path.exists(self.sessions_file):
            try:
                import json
                with open(self.sessions_file, "r", encoding="utf-8") as f:
                    self.sessions = json.load(f)
            except Exception:
                self.sessions = {}

    def _save_sessions(self):
        try:
            import json
            with open(self.sessions_file, "w", encoding="utf-8") as f:
                json.dump(self.sessions, f)
        except Exception:
            pass

    def reinit(self):
        self.base_dir = os.path.dirname(os.path.abspath(__file__))
        self._load_sessions()

    def authenticate(self, username, password):
        """Authenticates a user and issues a bearer session token."""
        user = self.TEST_USERS.get(username)
        if not user or user["password"] != password:
            return None

        token = "sec-" + uuid.uuid4().hex
        session_data = {
            "username": username,
            "role": user["role"],
            "name": user["name"],
            "allowed_projects": user["allowed_projects"],
            "created_at": time.time()
        }
        self.sessions[token] = session_data
        self._save_sessions()
        return {"token": token, "user": session_data}

    def get_user_from_token(self, token):
        """Validates token and returns user details. Returns None if no token provided."""
        if not token:
            return None
        return self.sessions.get(token)

    def logout(self, token):
        if token in self.sessions:
            del self.sessions[token]
            self._save_sessions()
            return True
        return False

    def can_access_project(self, user, project_name):
        if not user:
            return False
        if user["role"] == self.ROLE_ADMIN:
            return True
        if not project_name:
            return False
        return ("*" in user.get("allowed_projects", [])) or (project_name in user.get("allowed_projects", []))

    def can_view_logs(self, user):
        return bool(user and user.get("role") == self.ROLE_ADMIN)

    def can_reload_engine(self, user):
        return bool(user and user.get("role") == self.ROLE_ADMIN)

    def classify_file(self, rel_path: str) -> str:
        norm_path = os.path.normpath(rel_path).replace("\\", "/")
        parts = norm_path.split("/")

        for p in parts[:-1]:  # Check all directory parts
            if p in self.FORBIDDEN_NAMES or p.startswith("."):
                return self.TIER_FORBIDDEN
            if p in self.CORE_DIRECTORIES:
                return self.TIER_CORE_ENGINE
                
        # Check the final file/folder name
        final_part = parts[-1]
        if final_part in self.FORBIDDEN_NAMES or final_part.startswith("."):
            return self.TIER_FORBIDDEN

        filename = os.path.basename(norm_path)
        if filename in self.CORE_FILES:
            return self.TIER_CORE_ENGINE

        if filename.endswith(".log"):
            return self.TIER_ADMIN_LOG

        _, ext = os.path.splitext(filename)
        if ext.lower() in self.ALLOWED_EXTENSIONS or ext == "":
            return self.TIER_SAFE_WORKSPACE

        return self.TIER_FORBIDDEN

    def resolve_safe_path(self, target_base: str, rel_path: str, user: dict = None) -> str:
        """Enforces absolute sandbox boundaries using realpath to prevent symlink escapes."""
        if not rel_path:
            raise ValueError("Empty file path")

        clean_rel = os.path.normpath(rel_path).lstrip("/\\")
        if clean_rel.startswith("..") or "/../" in clean_rel or "\\..\\" in clean_rel:
            raise PermissionError("Access Denied: Path traversal forbidden")

        # Dynamic Anchoring for Dual-Access:
        # If user is not an admin, they are forcefully anchored to the /playground directory
        is_admin = user and user.get("role") == self.ROLE_ADMIN
        if not is_admin:
            target_base = os.path.join(self.base_dir, "playground")
            os.makedirs(target_base, exist_ok=True)
        else:
            # Admins get root visibility of e_profile
            target_base = "/mnt/c/Users/michael/Documents/e_profile"
            
        # Resolve real canonical paths (following symlinks)
        real_base = os.path.realpath(target_base)
        candidate_path = os.path.join(real_base, clean_rel)

        if os.path.lexists(candidate_path):
            real_target = os.path.realpath(candidate_path)
        else:
            parent_dir = os.path.realpath(os.path.dirname(candidate_path))
            real_target = os.path.join(parent_dir, os.path.basename(candidate_path))

        # Check that physical location resides strictly within real_base
        if not real_target.startswith(real_base + os.sep) and real_target != real_base:
            raise PermissionError("Access Denied: Symlink or path escapes sandbox boundary")

        # Role Check: Non-admins can NEVER touch Core Engine or Logs
        if user and user.get("role") != self.ROLE_ADMIN:
            tier = self.classify_file(clean_rel)
            if tier in (self.TIER_CORE_ENGINE, self.TIER_ADMIN_LOG, self.TIER_FORBIDDEN):
                raise PermissionError(f"Access Denied: Role '{user.get('role')}' cannot access {tier} files")

        return real_target

    def list_files(self, project_path: str, user: dict = None):
        """Lists files with role-aware filtering and permission attributes."""
        is_admin = user and user.get("role") == self.ROLE_ADMIN
        is_modder = user and user.get("role") == self.ROLE_MODDER
        effective_base = project_path or self.base_dir
        items = []

        try:
            for root, dirs, files in os.walk(effective_base):
                dirs[:] = [d for d in dirs if d not in self.FORBIDDEN_NAMES and not d.startswith(".")]

                for f in files:
                    full_p = os.path.join(root, f)
                    rel_p = os.path.relpath(full_p, effective_base).replace("\\", "/")
                    tier = self.classify_file(rel_p)

                    if tier == self.TIER_FORBIDDEN:
                        continue

                    # Hide core engine and logs from non-admins
                    if not is_admin and tier in (self.TIER_CORE_ENGINE, self.TIER_ADMIN_LOG):
                        continue

                    can_read = is_admin or (tier == self.TIER_SAFE_WORKSPACE)
                    can_write = is_admin or (tier == self.TIER_SAFE_WORKSPACE and not is_modder)

                    try:
                        size = os.path.getsize(full_p)
                        mtime = os.path.getmtime(full_p)
                    except Exception:
                        size = 0
                        mtime = 0

                    items.append({
                        "path": rel_p,
                        "name": f,
                        "size": size,
                        "mtime": mtime,
                        "tier": tier,
                        "can_read": can_read,
                        "can_write": can_write
                    })
        except Exception as e:
            print(f"[SecurityManager] Error listing files: {e}")

        items.sort(key=lambda x: (x["tier"] != self.TIER_SAFE_WORKSPACE, x["path"]))
        return items

    def list_logs(self, user: dict = None):
        """Lists system logs for administrative review only."""
        if not self.can_view_logs(user):
            raise PermissionError("Access Denied: Administrator role required to view system logs")

        logs = []
        for name in ["upgrade.log", "server_stdout.log"]:
            p = os.path.join(self.base_dir, name)
            if os.path.exists(p):
                logs.append({
                    "name": name,
                    "size": os.path.getsize(p),
                    "mtime": os.path.getmtime(p)
                })
        return logs

    def read_file_content(self, project_path: str, rel_path: str, user: dict = None):
        full_path = self.resolve_safe_path(project_path or self.base_dir, rel_path, user=user)
        tier = self.classify_file(rel_path)

        if not os.path.isfile(full_path):
            raise FileNotFoundError(f"File not found: {rel_path}")

        if os.path.getsize(full_path) > 500 * 1024:
            raise ValueError("File exceeds maximum viewable size (500 KB)")

        # TOCTOU Protection: Use file descriptor with O_NOFOLLOW to prevent race condition symlink swaps
        flags = os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0)
        fd = os.open(full_path, flags)
        try:
            with open(fd, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
        except Exception:
            os.close(fd)
            raise

        is_admin = user and user.get("role") == self.ROLE_ADMIN
        is_modder = user and user.get("role") == self.ROLE_MODDER

        # Safeguard: Scrub file content of PII for non-administrators
        if not is_admin:
            try:
                sec = self._get_security()
                if sec:
                    content = sec.scrub_text(content)
            except Exception as e:
                print(f"[Security] Failed to load LocalSecurity for file redaction: {e}")
                
            # Anti-Prompt Injection: Wrap content in untrusted delimiters
            content = f"<user_data_untrusted>\n{content}\n</user_data_untrusted>"

        return {
            "path": rel_path,
            "tier": tier,
            "content": content,
            "can_write": is_admin or (tier == self.TIER_SAFE_WORKSPACE and not is_modder)
        }

    def write_file_content(self, project_path: str, rel_path: str, content: str, user: dict = None):
        if user and user.get("role") == self.ROLE_MODDER:
            raise PermissionError("Access Denied: Modder role has read-only permissions")

        full_path = self.resolve_safe_path(project_path or self.base_dir, rel_path, user=user)
        tier = self.classify_file(rel_path)

        if tier == self.TIER_ADMIN_LOG:
            raise PermissionError("Access Denied: System logs are strictly read-only")

        # 1. Second-Order Execution Prevention (Static Analysis of Code)
        if full_path.endswith('.lua') or full_path.endswith('.py') or full_path.endswith('.sh'):
            forbidden_calls = ['os.remove', 'os.execute', 'io.popen', 'subprocess', 'rm -rf']
            if any(call in content for call in forbidden_calls):
                raise PermissionError(f"Access Denied: High-risk system call detected in generated code. Write rejected.")

        os.makedirs(os.path.dirname(full_path), exist_ok=True)

        # 2. TOCTOU Protection: Secure file descriptor without symlink following
        flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, 'O_NOFOLLOW', 0)
        fd = os.open(full_path, flags, 0o644)
        try:
            with open(fd, "w", encoding="utf-8") as f:
                f.write(content)
        except Exception:
            os.close(fd)
            raise

        return {"success": True, "path": rel_path, "size": len(content)}
