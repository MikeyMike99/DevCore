#!/usr/bin/env python3
"""Forwarder to Central_Docs/scripts/security_leak_scanner.py."""
import sys
import subprocess
from pathlib import Path

CENTRAL_SCANNER = Path(__file__).resolve().parent.parent.parent / "Central_Docs" / "scripts" / "security_leak_scanner.py"
if not CENTRAL_SCANNER.exists():
    print(f"[FATAL] Central security_leak_scanner.py not found at: {CENTRAL_SCANNER}")
    sys.exit(1)

res = subprocess.run([sys.executable, str(CENTRAL_SCANNER)] + sys.argv[1:])
sys.exit(res.returncode)
