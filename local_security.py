"""Compatibility shim. core/server.py still imports `local_security` from the repo root, but the file moved to
security/local_security.py on 2026-09-22. That broke the import, and because the callers swallow ImportError the
prompt firewall and the big-prompt scrubber silently stopped running. Keep this so those imports resolve."""
from security.local_security import LocalSecurity  # noqa: F401
