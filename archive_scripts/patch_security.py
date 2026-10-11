import re

with open("security_manager.py", "r") as f:
    content = f.read()

# Add ROLE_SUPER_ADMIN
content = content.replace('ROLE_ADMIN = "admin"', 'ROLE_ADMIN = "admin"\n    ROLE_SUPER_ADMIN = "super_admin"')

# Add super_admin to TEST_USERS
test_user_str = """    TEST_USERS = {
        "superadmin": {
            "password": "super",
            "role": ROLE_SUPER_ADMIN,
            "name": "Michael (Super Admin)",
            "allowed_projects": ["*"]
        },"""
content = content.replace('TEST_USERS = {', test_user_str)

# can_access_project
content = content.replace('if user["role"] == self.ROLE_ADMIN:', 'if user["role"] in (self.ROLE_ADMIN, self.ROLE_SUPER_ADMIN):')

# can_view_logs
content = content.replace('== self.ROLE_ADMIN)', 'in (self.ROLE_ADMIN, self.ROLE_SUPER_ADMIN))')

# can_reload_engine
# The replace above might catch this if it's identical, but let's be safe.
# It was: return bool(user and user.get("role") == self.ROLE_ADMIN)
# It's better to use regex for both:
content = re.sub(r'return bool\(user and user\.get\("role"\) == self\.ROLE_ADMIN\)', 
                 r'return bool(user and user.get("role") in (self.ROLE_ADMIN, self.ROLE_SUPER_ADMIN))', 
                 content)

# resolve_safe_path - bypass sandbox check for super_admin
sandbox_check = """        # Check that physical location resides strictly within real_base
        if not real_target.startswith(real_base + os.sep) and real_target != real_base:
            raise PermissionError("Access Denied: Symlink or path escapes sandbox boundary")"""

new_sandbox_check = """        # Check that physical location resides strictly within real_base (Super Admins bypass this)
        is_super_admin = user and user.get("role") == self.ROLE_SUPER_ADMIN
        if not is_super_admin and not real_target.startswith(real_base + os.sep) and real_target != real_base:
            raise PermissionError("Access Denied: Symlink or path escapes sandbox boundary")"""
content = content.replace(sandbox_check, new_sandbox_check)

# Role check in resolve_safe_path
content = content.replace('if user and user.get("role") != self.ROLE_ADMIN:', 
                          'if user and user.get("role") not in (self.ROLE_ADMIN, self.ROLE_SUPER_ADMIN):')

# list_files
content = content.replace('is_admin = user and user.get("role") == self.ROLE_ADMIN',
                          'is_admin = user and user.get("role") in (self.ROLE_ADMIN, self.ROLE_SUPER_ADMIN)\n        is_super_admin = user and user.get("role") == self.ROLE_SUPER_ADMIN')

content = content.replace("""                    if tier == self.TIER_FORBIDDEN:
                        continue""",
                          """                    if tier == self.TIER_FORBIDDEN and not is_super_admin:
                        continue""")

# write_file_content
write_log_check = """        if tier == self.TIER_ADMIN_LOG:
            raise PermissionError("Access Denied: System logs are strictly read-only")"""

new_write_log_check = """        is_super_admin = user and user.get("role") == self.ROLE_SUPER_ADMIN
        if tier == self.TIER_ADMIN_LOG and not is_super_admin:
            raise PermissionError("Access Denied: System logs are strictly read-only")"""
content = content.replace(write_log_check, new_write_log_check)

static_check = """        # 1. Second-Order Execution Prevention (Static Analysis of Code)
        if full_path.endswith('.lua') or full_path.endswith('.py') or full_path.endswith('.sh'):
            forbidden_calls = ['os.remove', 'os.execute', 'io.popen', 'subprocess', 'rm -rf']
            if any(call in content for call in forbidden_calls):
                raise PermissionError(f"Access Denied: High-risk system call detected in generated code. Write rejected.")"""

new_static_check = """        # 1. Second-Order Execution Prevention (Static Analysis of Code) - Bypassed for Super Admin
        if not is_super_admin and (full_path.endswith('.lua') or full_path.endswith('.py') or full_path.endswith('.sh')):
            forbidden_calls = ['os.remove', 'os.execute', 'io.popen', 'subprocess', 'rm -rf']
            if any(call in content for call in forbidden_calls):
                raise PermissionError(f"Access Denied: High-risk system call detected in generated code. Write rejected.")"""
content = content.replace(static_check, new_static_check)

with open("security_manager.py", "w") as f:
    f.write(content)

print("Patched security_manager.py successfully.")
