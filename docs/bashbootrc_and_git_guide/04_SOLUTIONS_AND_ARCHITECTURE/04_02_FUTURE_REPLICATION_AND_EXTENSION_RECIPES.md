# Pillar 04.2: Future Replication & Extension Recipes

- **Back to Master Index**: [`../00_README_INDEX.md`](../00_README_INDEX.md)
- **Previous Solution Chapter**: [`04_01_UNIFIED_BASHRC_AND_GIT_ARCHITECTURE.md`](./04_01_UNIFIED_BASHRC_AND_GIT_ARCHITECTURE.md)
- **Next: From-Scratch Creation Guides**: [`../05_FROM_SCRATCH_CREATION_GUIDES/05_01_BASHRC_AUTO_SWITCHER_FROM_SCRATCH.md`](../05_FROM_SCRATCH_CREATION_GUIDES/05_01_BASHRC_AUTO_SWITCHER_FROM_SCRATCH.md)

---

## Overview

As projects grow, developers frequently need to add a third or fourth virtual environment or create custom Git automation commands. 

This guide provides tested, copy-paste recipes for extending both the shell boot hook (`_auto_venv_hook`) and the Git automation suite (`helpers.sh`).

---

## Recipe 1: Adding a 3rd Virtual Environment to `~/.bashrc`

Suppose you create a new game or data science project located at `/mnt/c/Users/<username>/Documents/GameDev` and its dedicated virtual environment lives at `~/.venvs/gamedev_env`.

### Step 1: Open `~/.bashrc` in Your Terminal
```bash
nano ~/.bashrc
```

### Step 2: Locate the `_auto_venv_hook()` Function
Scroll down to the `_auto_venv_hook()` block.

### Step 3: Add the New Path Match Rule
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

### Step 4: Reload Your Shell Configuration
```bash
source ~/.bashrc
```

---

## Recipe 2: Adding a Custom Git Workflow Command to `helpers.sh`

Suppose your team needs an automated command `check-sync` that tells you if your local branch is behind GitHub before you start coding.

### Step 1: Open `helpers.sh`
```bash
nano "$HOME/tools/recording/helpers.sh"
```

### Step 2: Append the New Helper Function
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

### Step 3: Refresh Active Shell Session
```bash
source "$HOME/tools/recording/helpers.sh"
```

---

## Why Order Matters in Extension Recipes

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

## Extension Verification Checklist

| Test Item | Command / Action | Expected Result |
| :--- | :--- | :--- |
| **New Directory Navigation** | `cd /mnt/c/Users/<username>/Documents/GameDev` | Prompt updates; `echo $VIRTUAL_ENV` outputs `.../gamedev_env` |
| **Neutral Navigation** | `cd /tmp` | `echo $VIRTUAL_ENV` outputs empty string |
| **Custom Git Command** | `check-sync` | Status banner prints; reports sync delta |
| **Shell Reload Safety** | `source ~/.bashrc` | Completes instantly with zero error lines |

---

## Beginner Coder Q&A

### Q: What happens if I create a new project folder inside DevCore?
**A:** Because `_auto_venv_hook()` uses wildcard pattern matching (`*"/DevCore"*`), any subfolder inside DevCore will automatically remain in `devcore_env`. If you want a specific subfolder inside DevCore to use a separate environment, place that specific subfolder check **above** the main DevCore check.

### Q: Why do we write `2>/dev/null` after `deactivate` and `source`?
**A:** `2>/dev/null` silences standard error messages. If no virtual environment is active, calling `deactivate` prints `deactivate: command not found`. Redirecting errors keeps your terminal prompt clean and quiet during navigation.

### Q: Do I need to restart my computer when updating `helpers.sh`?
**A:** No. Simply run `source ~/.bashrc` or `source "$HOME/tools/recording/helpers.sh"`. Changes take effect instantly in that terminal window.
