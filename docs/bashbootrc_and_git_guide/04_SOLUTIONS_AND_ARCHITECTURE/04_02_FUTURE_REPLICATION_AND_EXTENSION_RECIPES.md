[//]: # (DOC_ID: SIRA-DEV-BOOT_04_02 | VERSION: v1.0 | SCOPE: DEV)

# Pillar 04.2: Future Replication & Extension Recipes

- **Back to Master Index**: [`../00_README_INDEX.md`](../00_README_INDEX.md)
- **Previous Solution Chapter**: [`04_01_UNIFIED_BASHRC_AND_GIT_ARCHITECTURE.md`](./04_01_UNIFIED_BASHRC_AND_GIT_ARCHITECTURE.md)
- **Next: From-Scratch Creation Guides**: [`../05_FROM_SCRATCH_CREATION_GUIDES/05_01_BASHRC_AUTO_SWITCHER_FROM_SCRATCH.md`](../05_FROM_SCRATCH_CREATION_GUIDES/05_01_BASHRC_AUTO_SWITCHER_FROM_SCRATCH.md)

---

[//]: # (SECTION_ID: SIRA-DEV-BOOT_04_02-SEC-1)
## Overview
[//]: # (SECTION_ID: SIRA-DOC-04_02-SEC-1)

As projects grow, developers frequently need to add a third or fourth virtual environment or create custom Git automation commands. 

This guide provides tested, copy-paste recipes for extending both the shell boot hook (`_auto_venv_hook`) and the Git automation suite (`helpers.sh`).

---

[//]: # (SECTION_ID: SIRA-DEV-BOOT_04_02-SEC-2)
## Recipe 1: Adding a 3rd Virtual Environment to `~/.bashrc`
[//]: # (SECTION_ID: SIRA-DOC-04_02-SEC-2)

Suppose you create a new game or data science project located at `/mnt/c/Users/<username>/Documents/GameDev` and its dedicated virtual environment lives at `~/.venvs/gamedev_env`.

[//]: # (SECTION_ID: SIRA-DEV-BOOT_04_02-SEC-3)
### Step 1: Open `~/.bashrc` in Your Terminal
[//]: # (SECTION_ID: SIRA-DOC-04_02-SEC-3)
```bash
nano ~/.bashrc
```

[//]: # (SECTION_ID: SIRA-DEV-BOOT_04_02-SEC-4)
### Step 2: Locate the `_auto_venv_hook()` Function
[//]: # (SECTION_ID: SIRA-DOC-04_02-SEC-4)
Scroll down to the `_auto_venv_hook()` block.

[//]: # (SECTION_ID: SIRA-DEV-BOOT_04_02-SEC-5)
### Step 3: Add the New Path Match Rule
[//]: # (SECTION_ID: SIRA-DOC-04_02-SEC-5)
Insert the new `elif` branch before the default deactivation fallback:

```bash
_auto_venv_hook() {
    # 1. Primary DevCore Workspace
    if [[ "$PWD" == *"/DevCore"* ]]; then
        if [ "$VIRTUAL_ENV" != "$HOME/.venvs/devcore_env" ]; then
            deactivate 2>/dev/null
            source "$HOME/.venvs/devcore_env/bin/activate" 2>/dev/null
        fi
    # 2. GameDev Project Workspace (NEW)
    elif [[ "$PWD" == *"/GameDev"* ]]; then
        if [ "$VIRTUAL_ENV" != "$HOME/.venvs/gamedev_env" ]; then
            deactivate 2>/dev/null
            source "$HOME/.venvs/gamedev_env/bin/activate" 2>/dev/null
        fi
    # 3. Secondary Tools / Work Env
    elif [[ "$PWD" == *"/secondary_project"* ]] || [[ "$PWD" == "$HOME/secondary_env"* ]]; then
        if [ "$VIRTUAL_ENV" != "$HOME/secondary_env" ]; then
            deactivate 2>/dev/null
            source "$HOME/secondary_env/bin/activate" 2>/dev/null
        fi
    # 4. Neutral Territory - Clean Exit
    else
        if [ -n "$VIRTUAL_ENV" ]; then
            deactivate 2>/dev/null
        fi
    fi
}
```

[//]: # (SECTION_ID: SIRA-DEV-BOOT_04_02-SEC-6)
### Step 4: Reload Your Shell Configuration
[//]: # (SECTION_ID: SIRA-DOC-04_02-SEC-6)
```bash
source ~/.bashrc
```

---

[//]: # (SECTION_ID: SIRA-DEV-BOOT_04_02-SEC-7)
## Recipe 2: Adding a Custom Git Workflow Command to `helpers.sh`
[//]: # (SECTION_ID: SIRA-DOC-04_02-SEC-7)

Suppose your team needs an automated command `check-sync` that tells you if your local branch is behind GitHub before you start coding.

[//]: # (SECTION_ID: SIRA-DEV-BOOT_04_02-SEC-8)
### Step 1: Open `helpers.sh`
[//]: # (SECTION_ID: SIRA-DOC-04_02-SEC-8)
```bash
nano "$HOME/tools/recording/helpers.sh"
```

[//]: # (SECTION_ID: SIRA-DEV-BOOT_04_02-SEC-9)
### Step 2: Append the New Helper Function
[//]: # (SECTION_ID: SIRA-DOC-04_02-SEC-9)
Add this function to the bottom of `helpers.sh`:

```bash
check-sync() {
    echo "=========================================="
    echo "  Checking Remote Repository Sync Status  "
    echo "=========================================="
    
    # 1. Fetch latest headers without merging
    git fetch origin
    
    local current_branch
    current_branch=$(git rev-parse --abbrev-ref HEAD)
    
    local behind_count
    behind_count=$(git rev-list --count "HEAD..origin/$current_branch" 2>/dev/null || echo "0")
    
    if [ "$behind_count" -gt 0 ]; then
        echo "[WARNING] You are $behind_count commit(s) behind origin/$current_branch!"
        echo "Run 'git pull origin $current_branch' before making edits."
    else
        echo "[OK] Your local branch '$current_branch' is fully up to date."
    fi
}
```

[//]: # (SECTION_ID: SIRA-DEV-BOOT_04_02-SEC-10)
### Step 3: Refresh Active Shell Session
[//]: # (SECTION_ID: SIRA-DOC-04_02-SEC-10)
```bash
source "$HOME/tools/recording/helpers.sh"
```

---

[//]: # (SECTION_ID: SIRA-DEV-BOOT_04_02-SEC-11)
## Why Order Matters in Extension Recipes
[//]: # (SECTION_ID: SIRA-DOC-04_02-SEC-11)

1. **Specific Folders Before Generic Fallbacks**:
   - In `_auto_venv_hook()`, nested folders or specific projects must be evaluated before broad parent paths.
   - If a generic pattern like `*"/Documents"*` matched first, the shell would never reach child project rules.
2. **Deactivate Before Activate**:
   - Always invoke `deactivate` before sourcing a new virtual environment.
   - Failing to deactivate leaves stale paths from the old environment prepended to `$PATH`.
3. **Fetch Before Rev-List**:
   - In Git automation scripts, `git fetch origin` must complete before evaluating commit differences.
   - Evaluating `HEAD..origin/branch` against stale local cache reports false sync states.

---

[//]: # (SECTION_ID: SIRA-DEV-BOOT_04_02-SEC-12)
## Extension Verification Checklist
[//]: # (SECTION_ID: SIRA-DOC-04_02-SEC-12)

| Test Item | Command / Action | Expected Result |
| :--- | :--- | :--- |
| **New Directory Navigation** | `cd /mnt/c/Users/<username>/Documents/GameDev` | Prompt updates; `echo $VIRTUAL_ENV` outputs `.../gamedev_env` |
| **Neutral Navigation** | `cd /tmp` | `echo $VIRTUAL_ENV` outputs empty string |
| **Custom Git Command** | `check-sync` | Status banner prints; reports sync delta |
| **Shell Reload Safety** | `source ~/.bashrc` | Completes instantly with zero error lines |

---

[//]: # (SECTION_ID: SIRA-DEV-BOOT_04_02-SEC-13)
## Beginner Coder Q&A
[//]: # (SECTION_ID: SIRA-DEV-BOOT_04_02-SEC-14)

### Q: What happens if I create a new project folder inside DevCore?
[//]: # (SECTION_ID: SIRA-DOC-04_02-SEC-14)
**A:** Because `_auto_venv_hook()` uses wildcard pattern matching (`*"/DevCore"*`), any subfolder inside DevCore will automatically remain in `devcore_env`. If you want a specific subfolder inside DevCore to use a separate environment, place that specific subfolder check **above** the main DevCore check.

[//]: # (SECTION_ID: SIRA-DEV-BOOT_04_02-SEC-15)
### Q: Why do we write `2>/dev/null` after `deactivate` and `source`?
[//]: # (SECTION_ID: SIRA-DOC-04_02-SEC-15)
**A:** `2>/dev/null` silences standard error messages. If no virtual environment is active, calling `deactivate` prints `deactivate: command not found`. Redirecting errors keeps your terminal prompt clean and quiet during navigation.

[//]: # (SECTION_ID: SIRA-DEV-BOOT_04_02-SEC-16)
### Q: Do I need to restart my computer when updating `helpers.sh`?
[//]: # (SECTION_ID: SIRA-DOC-04_02-SEC-16)
**A:** No. Simply run `source ~/.bashrc` or `source "$HOME/tools/recording/helpers.sh"`. Changes take effect instantly in that terminal window.
