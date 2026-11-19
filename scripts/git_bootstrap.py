#!/usr/bin/env python3
"""Forwarder to Central_Docs/scripts/git_bootstrap.py."""
import sys
import subprocess
from pathlib import Path

CENTRAL_BOOT = Path(__file__).resolve().parent.parent.parent / "Central_Docs" / "scripts" / "git_bootstrap.py"
if not CENTRAL_BOOT.exists():
    print(f"[FATAL] Central git_bootstrap.py not found at: {CENTRAL_BOOT}")
    sys.exit(1)

res = subprocess.run([sys.executable, str(CENTRAL_BOOT)] + sys.argv[1:])
sys.exit(res.returncode)
