import re

with open("security_manager.py", "r") as f:
    content = f.read()

# Replace the entire resolve_safe_path body
old_resolve = """    def resolve_safe_path(self, target_base: str, rel_path: str, user: dict = None) -> str:
        \"\"\"Enforces absolute sandbox boundaries using realpath to prevent symlink escapes.\"\"\"
        if not rel_path:
            raise ValueError("Empty file path")

        clean_rel = os.path.normpath(rel_path).lstrip("/\\\\")
        if clean_rel.startswith("..") or "/../" in clean_rel or "\\\\..\\\\" in clean_rel:
            raise PermissionError("Access Denied: Path traversal forbidden")

        # Resolve real canonical paths (following symlinks)
        real_base = os.path.realpath(target_base)
        candidate_path = os.path.join(real_base, clean_rel)

        if os.path.lexists(candidate_path):
            real_target = os.path.realpath(candidate_path)
        else:
            parent_dir = os.path.realpath(os.path.dirname(candidate_path))
            real_target = os.path.join(parent_dir, os.path.basename(candidate_path))

        # Check that physical location resides strictly within real_base (Super Admins bypass this)
        is_super_admin = user and user.get("role") == self.ROLE_SUPER_ADMIN
        if not is_super_admin and not real_target.startswith(real_base + os.sep) and real_target != real_base:
            raise PermissionError("Access Denied: Symlink or path escapes sandbox boundary")

        # Role Check: Non-admins can NEVER touch Core Engine or Logs
        if user and user.get("role") not in (self.ROLE_ADMIN, self.ROLE_SUPER_ADMIN):
            tier = self.classify_file(clean_rel)
            if tier in (self.TIER_CORE_ENGINE, self.TIER_ADMIN_LOG, self.TIER_FORBIDDEN):
                raise PermissionError(f"Access Denied: Role '{user.get('role')}' cannot access {tier} files")

        return real_target"""

new_resolve = """    def resolve_safe_path(self, target_base: str, rel_path: str, user: dict = None) -> str:
        \"\"\"Enforces absolute sandbox boundaries using realpath to prevent symlink escapes.\"\"\"
        if not rel_path:
            raise ValueError("Empty file path")

        is_super_admin = user and user.get("role") == self.ROLE_SUPER_ADMIN
        
        if is_super_admin:
            if os.path.isabs(rel_path):
                real_target = os.path.realpath(rel_path)
            else:
                real_target = os.path.realpath(os.path.join(target_base, rel_path))
            clean_rel = rel_path
        else:
            clean_rel = os.path.normpath(rel_path).lstrip("/\\\\")
            if clean_rel.startswith("..") or "/../" in clean_rel or "\\\\..\\\\" in clean_rel:
                raise PermissionError("Access Denied: Path traversal forbidden")

            # Resolve real canonical paths (following symlinks)
            real_base = os.path.realpath(target_base)
            candidate_path = os.path.join(real_base, clean_rel)

            if os.path.lexists(candidate_path):
                real_target = os.path.realpath(candidate_path)
            else:
                parent_dir = os.path.realpath(os.path.dirname(candidate_path))
                real_target = os.path.join(parent_dir, os.path.basename(candidate_path))

            if not real_target.startswith(real_base + os.sep) and real_target != real_base:
                raise PermissionError("Access Denied: Symlink or path escapes sandbox boundary")

        # Role Check: Non-admins can NEVER touch Core Engine or Logs
        if user and user.get("role") not in (self.ROLE_ADMIN, self.ROLE_SUPER_ADMIN):
            tier = self.classify_file(clean_rel)
            if tier in (self.TIER_CORE_ENGINE, self.TIER_ADMIN_LOG, self.TIER_FORBIDDEN):
                raise PermissionError(f"Access Denied: Role '{user.get('role')}' cannot access {tier} files")

        return real_target"""

if old_resolve in content:
    content = content.replace(old_resolve, new_resolve)
    with open("security_manager.py", "w") as f:
        f.write(content)
    print("Patch successful.")
else:
    print("Could not find the target block.")
