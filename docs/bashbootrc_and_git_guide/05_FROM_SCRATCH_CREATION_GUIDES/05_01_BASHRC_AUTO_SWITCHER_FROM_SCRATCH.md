[//]: # (DOC_ID: SIRA-DOC-05_01 | VERSION: v1.0 | SCOPE: Siraugga / DevCore Framework)

# Pillar 05.1: From-Scratch Creation Guide: Bash Boot Auto-Switcher

- **Back to Master Index**: [`../00_README_INDEX.md`](../00_README_INDEX.md)
- **Next From-Scratch Guide**: [`05_02_GIT_AUTOMATION_HELPERS_FROM_SCRATCH.md`](./05_02_GIT_AUTOMATION_HELPERS_FROM_SCRATCH.md)

---

## Overview
[//]: # (SECTION_ID: SIRA-DOC-05_01-SEC-1)

This guide teaches beginner developers how to build an automated, directory-aware Python virtual environment switcher inside `~/.bashrc` ("bashbootrc") from a blank file on any clean Linux or WSL distribution.

By the end of this tutorial, your terminal will automatically activate the correct Python virtual environment whenever you navigate into a project folder and safely deactivate it when you leave.

---

## Prerequisites & Directory Setup
[//]: # (SECTION_ID: SIRA-DOC-05_01-SEC-2)

Before editing `~/.bashrc`, prepare the isolated virtual environment directories on your system:

```bash
# 1. Create directory for dedicated environments
mkdir -p "$HOME/.venvs"

# 2. Generate the primary virtual environment
python3 -m venv "$HOME/.venvs/devcore_env"

# 3. Generate the secondary virtual environment
python3 -m venv "$HOME/secondary_env"
```

---

## Step-by-Step Implementation
[//]: # (SECTION_ID: SIRA-DOC-05_01-SEC-3)

### Step 1: Open `~/.bashrc` in Nano
[//]: # (SECTION_ID: SIRA-DOC-05_01-SEC-4)
```bash
nano ~/.bashrc
```

### Step 2: Add the Non-Interactive Guard
[//]: # (SECTION_ID: SIRA-DOC-05_01-SEC-5)
At the very top of `~/.bashrc`, verify or paste the interactive session guard:

```bash
# Exit immediately if running in non-interactive mode (e.g., scp, sftp, automated scripts)
case $- in
    *i*) ;;
      *) return;;
esac
```

### Step 3: Add the Auto-Switching Hook Logic
[//]: # (SECTION_ID: SIRA-DOC-05_01-SEC-6)
Scroll to the bottom of `~/.bashrc` and paste the core auto-switching engine:

```bash
# ==============================================================================
# AUTOMATIC VIRTUAL ENVIRONMENT SWITCHER HOOK
# ==============================================================================
_auto_venv_hook() {
    # 1. Primary DevCore Project Directory
    if [[ "$PWD" == *"/DevCore"* ]]; then
        if [ "$VIRTUAL_ENV" != "$HOME/.venvs/devcore_env" ]; then
            deactivate 2>/dev/null
            source "$HOME/.venvs/devcore_env/bin/activate" 2>/dev/null
        fi
    # 2. Secondary Tools / Workspace Directory
    elif [[ "$PWD" == *"/secondary_project"* ]] || [[ "$PWD" == "$HOME/secondary_env"* ]]; then
        if [ "$VIRTUAL_ENV" != "$HOME/secondary_env" ]; then
            deactivate 2>/dev/null
            source "$HOME/secondary_env/bin/activate" 2>/dev/null
        fi
    # 3. Neutral Directory Fallback
    else
        if [ -n "$VIRTUAL_ENV" ]; then
            deactivate 2>/dev/null
        fi
    fi
}
```

### Step 4: Wrap the Built-In `cd` Command & Register Prompt Hook
[//]: # (SECTION_ID: SIRA-DOC-05_01-SEC-7)
Directly beneath `_auto_venv_hook()`, add the trigger mechanisms:

```bash
# Wrap cd so every directory change triggers the inspection hook
cd() {
    builtin cd "$@" && _auto_venv_hook
}

# Attach to PROMPT_COMMAND as a secondary safety net
PROMPT_COMMAND="_auto_venv_hook${PROMPT_COMMAND:+; $PROMPT_COMMAND}"
```

### Step 5: Save and Reload
[//]: # (SECTION_ID: SIRA-DOC-05_01-SEC-8)
1. Press `Ctrl + O` and hit `Enter` to save in Nano.
2. Press `Ctrl + X` to exit Nano.
3. Reload your terminal session:
   ```bash
   source ~/.bashrc
   ```

---

## Why Order Matters in `~/.bashrc` Setup
[//]: # (SECTION_ID: SIRA-DOC-05_01-SEC-9)

1. **Guard Before Script Execution**:
   - The interactive guard (`case $- in *i*)`) must precede all prints and hooks. If commands run during automated non-interactive tasks (like file transfers), output corrupts data streams.
2. **Function Definition Before Execution**:
   - `_auto_venv_hook()` must be defined before `cd()` or `PROMPT_COMMAND` attempts to call it. Bash executes line by line from top to bottom.
3. **Deactivate Before Activating**:
   - Always call `deactivate` prior to sourcing a new environment's `activate` script. Sourcing without deactivating leaves stale binaries in `$PATH`.
4. **Linux LF vs Windows CRLF**:
   - Never edit `~/.bashrc` using Windows Notepad. Windows adds carriage returns (`\r\n`) that cause Bash to fail with `\r: command not found`. Use `nano` or ensure your editor saves with Unix line feeds (`LF`).

---

## Verification & Testing
[//]: # (SECTION_ID: SIRA-DOC-05_01-SEC-10)

Verify that your auto-switcher functions correctly by running these tests:

```bash
# Test 1: Navigate to Primary Project
cd /mnt/c/Users/<username>/Documents/DevCore
echo "$VIRTUAL_ENV"
# Expected Output: /home/<username>/.venvs/devcore_env

# Test 2: Navigate to Neutral Folder
cd /tmp
echo "$VIRTUAL_ENV"
# Expected Output: (empty string)

# Test 3: Navigate to Secondary Project
cd "$HOME/secondary_env"
echo "$VIRTUAL_ENV"
# Expected Output: /home/<username>/secondary_env
```

---

## Beginner Coder Q&A
[//]: # (SECTION_ID: SIRA-DOC-05_01-SEC-11)

### Q: Why do we use `builtin cd` instead of just `cd` inside the wrapper function?
[//]: # (SECTION_ID: SIRA-DOC-05_01-SEC-12)
**A:** If a function named `cd()` calls `cd`, it calls itself in an endless loop until the shell crashes with a stack overflow error. `builtin cd` tells Bash to run the real Linux command instead of the custom function.

### Q: Why do we need both `cd()` and `PROMPT_COMMAND`?
[//]: # (SECTION_ID: SIRA-DOC-05_01-SEC-13)
**A:** `cd()` catches normal directory hopping. `PROMPT_COMMAND` runs every time the terminal prepares to display the command prompt, catching other navigation tools like `pushd`, `popd`, or startup terminal restores.

### Q: What should I do if my terminal says `command not found: deactivate`?
[//]: # (SECTION_ID: SIRA-DOC-05_01-SEC-14)
**A:** This happens if no environment was active yet. Adding `2>/dev/null` suppresses this message safely.
