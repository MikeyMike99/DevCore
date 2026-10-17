# Pillar 04.1: Unified Architecture Blueprint: Shell Boot & Git Operations

- **Back to Master Index**: [`../00_README_INDEX.md`](../00_README_INDEX.md)
- **Next Solution Chapter**: [`04_02_FUTURE_REPLICATION_AND_EXTENSION_RECIPES.md`](./04_02_FUTURE_REPLICATION_AND_EXTENSION_RECIPES.md)

---

## Overview

The integration between **`~/.bashrc` ("bashbootrc")**, **isolated virtual environments**, and **automated Git operations** creates a unified, self-healing developer workflow across WSL Linux and Windows.

Below is the complete architectural blueprint detailing the lifecycle, data flow, and safety boundaries.

---

## Unified System Architecture Diagram

```text
+-------------------------------------------------------------------------------+
|                             Terminal Startup (WSL)                            |
+---------------------------------------+---------------------------------------+
                                        |
                                        v
+-------------------------------------------------------------------------------+
|                               ~/.bashrc Sequence                              |
|  1. Non-Interactive Guard (case $- in *i*) -> Exit early if background        |
|  2. Register $PATH ($HOME/.local/bin) -> CLI discovery                        |
|  3. Load helpers.sh -> Register 'start-day', 'save-work', 'sync-win-repo'     |
|  4. Define devcore-env() & work-env() -> Dynamic Windows path resolution      |
|  5. Define _auto_venv_hook() -> Inspects $PWD (*/DevCore* vs */secondary-env*)|
|  6. Wrap cd() & register PROMPT_COMMAND -> Trigger hook on every folder move  |
+---------------------------------------+---------------------------------------+
                                        |
            +---------------------------+---------------------------+
            |                                                       |
            v                                                       v
+-----------------------+                               +-----------------------+
|   DevCore Workspace   |                               |  Secondary Git Tools  |
|  (/mnt/c/.../DevCore) |                               |  ($HOME/secondary-env)|
+-----------+-----------+                               +-----------+-----------+
            |                                                       |
            v                                                       v
+-----------------------+                               +-----------------------+
| ~/.venvs/devcore_env  |                               |    ~/secondary-env    |
| - Quart, Hypercorn    |                               | - Git Automation      |
| - SpaCy, Presidio     |                               | - Asciinema, Checkov  |
| - Playwright, MCP     |                               | - Boto3, CycloneDX    |
+-----------+-----------+                               +-----------+-----------+
            |                                                       |
            v                                                       v
+-----------------------+                               +-----------------------+
|  scripts/start_server |                               |   helpers.sh Engine   |
|  - Locks to devcore   |                               |   - start-day (branch)|
|  - Boots Port 5000    |                               |   - save-work (stash) |
+-----------------------+                               +-----------+-----------+
                                                                    |
                                                                    v
                                                        +-----------------------+
                                                        |     sync-win-repo     |
                                                        | - rsync --exclude .git|
                                                        | - Mirrors to Windows  |
                                                        +-----------------------+
```

---

## The 4 Core Workflow Lifecycles

### 1. The Terminal Navigation Lifecycle
1. **User types `cd /mnt/c/.../DevCore`**:
2. The `cd()` wrapper calls `builtin cd "$@"` to perform the folder navigation.
3. If navigation succeeds, `_auto_venv_hook` inspects `$PWD`.
4. The pattern `*/DevCore*)` matches. It checks `$VIRTUAL_ENV`. Since it is not already `devcore_env`, it silently sources `$HOME/.venvs/devcore_env/bin/activate`.
5. The prompt displays `(.venvs/devcore_env) user@host:~/DevCore$`.

### 2. The Daily Git Feature Branch Lifecycle
1. **User types `start-day`**:
2. Checks out `main` and pulls latest changes from GitHub (`git pull origin main`).
3. Generates a sanitized branch name: `feature/<username>-<date>`.
4. Creates the branch (`git checkout -b`) and establishes upstream tracking immediately (`git push -u origin <branch>`).

### 3. The Safe Commit & Merge Lifecycle (`save-work`)
1. **User types `save-work` and selects Option 4 (Merge into `main`)**:
2. Commits any local work on the feature branch.
3. Stashes any untracked or auxiliary files (`git stash push -u`).
4. Switches to `main`, pulls remote updates (`git pull origin main`), and merges the feature branch.
5. Pushes updated `main` to GitHub.
6. **Only after push success**: Deletes the local feature branch and deletes the remote branch from GitHub.
7. Restores the stash pocket (`git stash pop`).

### 4. Cross-OS Synchronization Lifecycle (`sync-win-repo`)
1. Calls `_get_win_dest()` to dynamically query Windows for `%USERPROFILE%`.
2. Converts Windows path to `/mnt/c/Users/<user>/...` using `wslpath -u`.
3. Runs `rsync -rtv --delete --exclude=".git"`.
4. Copies source code, media, and docs to Windows while leaving Git databases uncorrupted.

---

## Beginner Coder Q&A: System Architecture

### 1. "Why do we keep `helpers.sh` separate from `~/.bashrc` instead of pasting all 700 lines into `.bashrc`?"
- Putting hundreds of lines of project-specific code directly into `~/.bashrc` bloats your terminal startup time.
- Keeping `helpers.sh` in its own repository file means you can update or share your Git automation scripts without modifying your personal operating system dotfiles. `~/.bashrc` simply includes it via `source`.

### 2. "Why does `start_server.sh` use `exec` instead of just running `python3 server.py`?"
When a script runs `python3 server.py`, Linux keeps both the shell wrapper and the Python program in memory. Writing `exec python3 server.py` tells Linux: *"Replace the shell wrapper with Python directly."* This saves system memory and ensures signals (like shutdown or restart) reach the web server directly.

---

- **Next Solution Chapter**: Read **[`04_02_FUTURE_REPLICATION_AND_EXTENSION_RECIPES.md`](./04_02_FUTURE_REPLICATION_AND_EXTENSION_RECIPES.md)** for copy-paste recipes to add new projects.
