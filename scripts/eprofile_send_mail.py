"""Compatibility wrapper forwarding CLI mail dispatch to `services.mail.cli`."""

from __future__ import annotations

import os
import sys

DEVCORE_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if DEVCORE_ROOT not in sys.path:
    sys.path.insert(0, DEVCORE_ROOT)

from services.mail.cli import main  # noqa: E402


if __name__ == "__main__":
    sys.exit(main())
