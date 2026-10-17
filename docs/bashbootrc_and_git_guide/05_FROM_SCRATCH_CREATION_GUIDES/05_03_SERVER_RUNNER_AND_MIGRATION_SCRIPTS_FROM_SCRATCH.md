[//]: # (DOC_ID: SIRA-DOC-05_03 | VERSION: v1.0 | SCOPE: Siraugga / DevCore Framework)

# Pillar 05.3: From-Scratch Creation Guide: Server Runner & Migration Scripts

- **Back to Master Index**: [`../00_README_INDEX.md`](../00_README_INDEX.md)
- **Previous From-Scratch Guide**: [`05_02_GIT_AUTOMATION_HELPERS_FROM_SCRATCH.md`](./05_02_GIT_AUTOMATION_HELPERS_FROM_SCRATCH.md)

---

## Overview
[//]: # (SECTION_ID: SIRA-DOC-05_03-SEC-1)

This guide details how to build two essential production maintenance scripts from scratch:
1. **`scripts/start_server.sh`**: A deterministic server runner that locks working directories and ensures the server executes strictly inside its dedicated virtual environment.
2. **`scripts/cleanup_dependencies.sh`**: A safety-first migration script that checks running server process environments before purging conflicting Python packages.

---

## Script 1: Deterministic Server Runner (`start_server.sh`)
[//]: # (SECTION_ID: SIRA-DOC-05_03-SEC-2)

### Purpose
[//]: # (SECTION_ID: SIRA-DOC-05_03-SEC-3)
When servers are started manually or by background daemons, the current working directory or shell environment might not be configured properly. This script guarantees correct execution every time.

### Implementation
[//]: # (SECTION_ID: SIRA-DOC-05_03-SEC-4)
Create `scripts/start_server.sh`:

```bash
#!/usr/bin/env bash
# ==============================================================================
# Deterministic Server Startup Script
# ==============================================================================
set -e

# 1. Resolve Project Root relative to script location
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

# 2. Source the Dedicated Virtual Environment Explicitly
VENV_PATH="$HOME/.venvs/devcore_env"
if [ -f "$VENV_PATH/bin/activate" ]; then
    source "$VENV_PATH/bin/activate"
else
    echo "[ERROR] Virtual environment not found at $VENV_PATH" >&2
    exit 1
fi

# 3. Verify Python Executable
echo "[BOOT] Starting server using: $(which python3)"
echo "[BOOT] Root Directory: $PROJECT_ROOT"

# 4. Replace shell process with Python server process
exec python3 server.py
```

Make the script executable:
```bash
chmod +x scripts/start_server.sh
```

---

## Script 2: Safe Dependency Migration (`cleanup_dependencies.sh`)
[//]: # (SECTION_ID: SIRA-DOC-05_03-SEC-5)

### Purpose
[//]: # (SECTION_ID: SIRA-DOC-05_03-SEC-6)
When separating a monolithic Python environment into isolated environments, you must verify that no live production server is actively using the environment before uninstalling packages.

### Implementation
[//]: # (SECTION_ID: SIRA-DOC-05_03-SEC-7)
Create `scripts/cleanup_dependencies.sh`:

```bash
#!/usr/bin/env bash
# ==============================================================================
# Safe Dependency Migration & Cleanup
# ==============================================================================
set -e

echo "=== Stage 1: Inspecting Running Server Processes ==="

# 1. Find any running python server process
SERVER_PID=$(pgrep -f "python3.*server.py" | head -n 1 || true)

if [ -n "$SERVER_PID" ]; then
    echo "[INFO] Detected active server process at PID: $SERVER_PID"
    
    # 2. Inspect /proc/<pid>/environ using strings to handle null bytes safely
    RUNNING_VENV=$(strings "/proc/$SERVER_PID/environ" | grep "^VIRTUAL_ENV=" | cut -d '=' -f 2 || true)
    
    echo "[INFO] Server is currently running inside: ${RUNNING_VENV:-System Python}"
    
    # 3. Guard against modifying active server environment
    if [ "$RUNNING_VENV" == "$HOME/secondary_env" ]; then
        echo "[CRITICAL ERROR] The server is currently running from secondary_env!"
        echo "Stop the server or migrate it to devcore_env before purging dependencies."
        exit 1
    fi
    echo "[OK] Live server is safely isolated from secondary_env."
else
    echo "[INFO] No active server process detected. Proceeding safely."
fi

echo "=== Stage 2: Purging Conflicting Packages ==="
# List of packages that belong strictly to devcore_env
CONFLICTING_PACKAGES=(
    "quart"
    "hypercorn"
    "spacy"
    "presidio-analyzer"
)

source "$HOME/secondary_env/bin/activate"

for pkg in "${CONFLICTING_PACKAGES[@]}"; do
    if pip show "$pkg" >/dev/null 2>&1; then
        echo "[PURGE] Removing $pkg from secondary_env..."
        pip uninstall -y "$pkg"
    else
        echo "[SKIP] $pkg is not installed in secondary_env."
    fi
done

echo "[SUCCESS] Dependency migration and cleanup completed safely."
```

Make the script executable:
```bash
chmod +x scripts/cleanup_dependencies.sh
```

---

## Why Order Matters in Runner & Migration Scripts
[//]: # (SECTION_ID: SIRA-DOC-05_03-SEC-8)

1. **Resolve Directory Before Activating Venv**:
   - `cd "$PROJECT_ROOT"` must happen before `source "$VENV_PATH/bin/activate"`. Relative path imports inside Python depend on being located at the workspace root.
2. **`exec` as the Final Action**:
   - `exec python3 server.py` replaces the Bash shell process entirely. Any code placed *after* an `exec` call is permanently ignored by Bash.
3. **Inspect Process Memory Before Purging Packages**:
   - `cleanup_dependencies.sh` checks `/proc/$SERVER_PID/environ` *before* executing `pip uninstall`. If packages were removed while the server was actively serving requests, in-flight imports would trigger immediate runtime `ModuleNotFoundError` crashes.
4. **Strings Filter Before Regex**:
   - Linux process environment blocks (`/proc/<pid>/environ`) are delimited by null bytes (`\0`). Standard `grep` treats null-byte streams as binary and may fail to match strings without `strings` or `tr` pre-filtering.

---

## Beginner Coder Q&A
[//]: # (SECTION_ID: SIRA-DOC-05_03-SEC-9)

### Q: Why use `exec python3 server.py` instead of just `python3 server.py`?
[//]: # (SECTION_ID: SIRA-DOC-05_03-SEC-10)
**A:** `exec` replaces the wrapper shell process with Python. This ensures system signals (such as `Ctrl+C` or daemon restart signals) reach Python directly without getting trapped or delayed by an intermediary Bash shell.

### Q: What is `/proc/<pid>/environ`?
[//]: # (SECTION_ID: SIRA-DOC-05_03-SEC-11)
**A:** Linux stores live diagnostic information about every running program inside the virtual `/proc` directory. Reading `/proc/<pid>/environ` lets you see the exact environment variables (like `$VIRTUAL_ENV`) that the process was launched with.

### Q: Will `pip uninstall` delete files from other virtual environments?
[//]: # (SECTION_ID: SIRA-DOC-05_03-SEC-12)
**A:** No. Because we explicitly activated `secondary_env` in Stage 2, `pip` only removes packages located inside that specific environment's folder.
