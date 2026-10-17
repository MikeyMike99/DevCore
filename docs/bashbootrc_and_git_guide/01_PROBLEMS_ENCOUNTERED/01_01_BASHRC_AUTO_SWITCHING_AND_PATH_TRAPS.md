# Pillar 01.1: Shell Boot Configuration & Virtual Environment Traps

- **Back to Master Index**: [`../00_README_INDEX.md`](../00_README_INDEX.md)
- **Next Problem Chapter**: [`01_02_GIT_WORKFLOW_AND_CROSS_OS_SYNC_TRAPS.md`](./01_02_GIT_WORKFLOW_AND_CROSS_OS_SYNC_TRAPS.md)

---

## Overview

When establishing independent virtual environments for **DevCore** and a **Secondary Project** while teaching `~/.bashrc` ("bashbootrc") to detect and switch environments automatically, five distinct technical obstacles appeared.

Below is the plain-English breakdown of what went wrong, why it occurred, and how we solved it.

---

## Problem 1: Mixed Shared Dependencies & The Live Port 5000 Zero-Downtime Trap

### What Happened
Originally, the workstation had a single Python virtual environment (`$HOME/secondary-env`). Over time, packages for two unrelated projects were installed together inside it:
- Cloud tools: `asciinema`, `checkov`, `boto3`, `cyclonedx-python-lib`.
- Web platform engine: `quart`, `hypercorn`, `presidio-analyzer`, `spacy`, `en_core_web_lg`, `playwright`, `mcp`, `cryptography`.

The live web server (`server.py`) was actively running on **Port 5000** using that shared environment to host our active developer web session.

### Why It Happened
1. **Zero-Restart Architecture Constraint**: We could not kill Port 5000 mid-session without dropping active WebSocket streams and disconnecting the browser.
2. **Cannot Uninstall Running Modules**: Uninstalling `quart` or `spacy` from the shared environment while the active server process was executing them risked immediate runtime errors or failed hot-patches.
3. **The Solution**: We created `$HOME/.venvs/devcore_env` in parallel on native Linux `ext4`, installed and verified all dependencies, updated [`scripts/start_server.sh`](../../scripts/start_server.sh), and built [`scripts/cleanup_dependencies.sh`](../../scripts/scratch_devcore_from_alp.sh) to purge shared packages only after confirming the server rebooted inside the dedicated environment.

---

## Problem 2: Boot Default Environment vs. Automatic Folder-Based Switching

### What Happened
In our first `.bashrc` draft, we placed `source ~/.venvs/devcore_env/bin/activate` unconditionally at the bottom of the file.

### Why It Happened
- Forcing one environment at boot hijacked every new terminal. Opening a terminal to work on the secondary project placed the user inside `devcore_env` unexpectedly.
- **The Solution**: We replaced the forced boot activation with `_auto_venv_hook()`. It monitors `$PWD` on every `cd` and prompt render: entering `*/DevCore*` activates `devcore_env`, entering `*/secondary-env*` activates `secondary-env`, and booting in `$HOME` remains clean and neutral.

---

## Problem 3: Hardcoded Absolute User Paths Across WSL and Windows

### What Happened
Scripts originally contained hardcoded paths like `/home/<user>/...` and `/mnt/c/Users/<user>/Documents/DevCore`. When moving between computers or user accounts, scripts crashed with `No such file or directory`.

### Why It Happened
1. **WSL Username Disconnect**: In WSL, the Linux user name does not always match the Windows user folder name (`C:\Users\<WindowsUser>`).
2. **The Solution**: We eliminated hardcoded paths by combining:
   - `$HOME` and `$USER` for Linux files.
   - Dynamic Windows profile detection via `cmd.exe /c "echo %USERPROFILE%"` piped into `wslpath -u`.
   - Wildcard pattern matching (`*/DevCore*`) in `_auto_venv_hook()`.

---

## Problem 4: The Null-Byte `/proc/$pid/environ` Trap

### What Happened
When [`scripts/cleanup_dependencies.sh`](../../scripts/scratch_devcore_from_alp.sh) needed to inspect the live `server.py` process to check its `VIRTUAL_ENV`, standard `grep "^VIRTUAL_ENV=" /proc/$pid/environ` failed or reported `Binary file matches`.

### Why It Happened
1. **Kernel Null-Byte Delimiters**: In Linux, `/proc/$pid/environ` separates environment variables using null bytes (`\0`) instead of newline characters (`\n`).
2. **`grep` Binary Detection**: Because there are no line breaks, `grep` treats the file as one continuous binary blob.
3. **The Solution**: We piped the file through the Linux `strings` utility first:
   ```bash
   venv=$(strings "/proc/$pid/environ" 2>/dev/null | grep "^VIRTUAL_ENV=" | cut -d= -f2- || true)
   ```
   `strings` turns null-separated variables into newline-separated text lines so `grep` and `cut` extract the path cleanly.

---

## Problem 5: Root Home Directory (`~`) Clutter & Script Independence

### What Happened
The home directory (`~`) had accumulated 56 loose files (over 200 MB), including split archive chunks and temporary scratch test scripts. Furthermore, secondary project scripts needed to remain 100% independent of DevCore.

### Why It Happened
- Temporary test scripts from past debugging sessions had been left behind.
- **The Solution**: We ran a dry-run audit, cleared the 56 loose scratch files from `~`, and verified via `grep` that secondary helper scripts contained zero references to DevCore.

---

## Beginner Coder Q&A: Shell & Environment Traps

### 1. "Why did we put the dedicated venv in `~/.venvs/` instead of inside the Windows folder?"
Folders under `/mnt/c/` live on Windows NTFS. Running thousands of small Python file operations across the Windows-to-WSL bridge is 5x to 10x slower. Putting virtual environments inside `~/.venvs/` (native Linux `ext4`) makes `python3` and `pip` run at maximum native speed.

### 2. "Why does `_auto_venv_hook` check `[ "$VIRTUAL_ENV" != ... ]` before activating?"
Activating a virtual environment takes several milliseconds because it updates environment variables. If you `cd` between subfolders inside the same project, the check realizes that environment is *already* active and does nothing, preventing terminal lag.

---

- **Next Chapter**: Read **[`01_02_GIT_WORKFLOW_AND_CROSS_OS_SYNC_TRAPS.md`](./01_02_GIT_WORKFLOW_AND_CROSS_OS_SYNC_TRAPS.md)** to see the 5 Git workflow and cross-OS sync problems.
