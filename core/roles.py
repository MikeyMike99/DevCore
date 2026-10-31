"""Canonical super-admin / root role names and matcher.

Single source of truth so the admin-role list isn't copied (and drifting, with
inconsistent casing) across modules. Pure leaf module — imports nothing from the
project — so any module can import it without a circular dependency.
"""

ADMIN_ROLES = frozenset({"admin", "super_admin", "super admin", "root", "tier5_sysadmin"})


def is_admin_role(role) -> bool:
    """Case-insensitive check of a single role name against the admin/root set."""
    return str(role or "").strip().lower() in ADMIN_ROLES
