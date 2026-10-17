# Pillar 02.1: Source Code & System Evidence: Shell Boot & Process Management

- **Back to Master Index**: [`../00_README_INDEX.md`](../00_README_INDEX.md)
- **Next Evidence Chapter**: [`02_02_GIT_HELPERS_AND_FLOW_EVIDENCE.md`](./02_02_GIT_HELPERS_AND_FLOW_EVIDENCE.md)

---

## Overview

Every architectural decision in our shell boot configuration and process supervision was verified directly against the live files and Linux kernel process tables (`/proc`). Below are the primary code excerpts, line numbers, and technical proofs.

---

## Source 1: Interactive Guard & Local Tool Path Registration in `~/.bashrc`

**Source File**: `~/.bashrc` (Lines 1–9 and 119–125)

```bash
# ~/.bashrc: executed by bash(1) for non-login shells.

# If not running interactively, don't do anything
case $- in
    *i*) ;;
      *) return;;
esac

# Added by CLI installer
export PATH="$HOME/.local/bin:$PATH"

# Secondary Project Workflow Helpers
if [ -f "$HOME/secondary-env/secondary_project/tools/recording/helpers.sh" ]; then
    source "$HOME/secondary-env/secondary_project/tools/recording/helpers.sh"
fi
```

### What This Source Proves
1. **Interactive Flag Verification (`case $- in *i*)`)**:
   `$-` contains the active flags of the shell session. When a script runs non-interactively (`bash -c "..."`), `$-` does not contain `i`, so line 8 immediately executes `return;;`. This prevents background commands (`scp`, `rsync`) from choking on custom shell output.
2. **Dynamic User Tool Discovery**:
   Adding `$HOME/.local/bin` to the front of `$PATH` ensures custom developer CLI binaries are discoverable across all terminal sessions.

---

## Source 2: Auto-Environment Detection & Dynamic Windows Profile Resolution

**Source File**: `~/.bashrc` (Auto-Switcher Block)

```bash
devcore-env() {
    if [ -f "$HOME/.venvs/devcore_env/bin/activate" ]; then
        source "$HOME/.venvs/devcore_env/bin/activate"
        local devcore_dir=""
        if command -v cmd.exe >/dev/null 2>&1; then
            local raw
            raw=$(cmd.exe /c "echo %USERPROFILE%" 2>/dev/null | tr -d "\r\n")
            [ -n "$raw" ] && devcore_dir="$(wslpath -u "$raw" 2>/dev/null)/Documents/DevCore"
        fi
        if [ -z "$devcore_dir" ] || [ ! -d "$devcore_dir" ]; then
            devcore_dir="/mnt/c/Users/$USER/Documents/DevCore"
        fi
        [ -d "$devcore_dir" ] && cd "$devcore_dir" 2>/dev/null
        echo "DevCore environment activated in $PWD"
    fi
}
alias devcore='devcore-env'

_auto_venv_hook() {
    case "$PWD" in
        */secondary-env*)
            if [ "$VIRTUAL_ENV" != "$HOME/secondary-env" ] && [ -f "$HOME/secondary-env/bin/activate" ]; then
                source "$HOME/secondary-env/bin/activate"
            fi
            ;;
        */DevCore*)
            if [ "$VIRTUAL_ENV" != "$HOME/.venvs/devcore_env" ] && [ -f "$HOME/.venvs/devcore_env/bin/activate" ]; then
                source "$HOME/.venvs/devcore_env/bin/activate"
            fi
            ;;
    esac
}

cd() {
    builtin cd "$@" || return $?
    _auto_venv_hook
}

if [[ ! "$PROMPT_COMMAND" =~ "_auto_venv_hook" ]]; then
    PROMPT_COMMAND="_auto_venv_hook${PROMPT_COMMAND:+; $PROMPT_COMMAND}"
fi
```

### What This Source Proves
1. **Dynamic Path Bridge**: `cmd.exe /c "echo %USERPROFILE%"` query combined with `wslpath -u` bridges Windows user profile paths into WSL without any hardcoded usernames.
2. **Wildcard Directory Detection**: `case "$PWD" in */DevCore*)` guarantees that navigating into the root or any subfolder triggers environment activation.

3. **Idempotent Prompt Hook**: Checking `[[ ! "$PROMPT_COMMAND" =~ "_auto_venv_hook" ]]` prevents duplicate registration when reloading `.bashrc`.
---

## Source 3: Dedicated Server Boot Wrapper (`scripts/start_server.sh`)

**Source File**: [`scripts/start_server.sh`](../../scripts/start_server.sh)

```bash
#!/bin/bash
cd "$(dirname "$0")/.." || exit 1
if [ -f "$HOME/.venvs/devcore_env/bin/activate" ]; then
    source "$HOME/.venvs/devcore_env/bin/activate"
fi
exec python3 server.py
```

### What This Source Proves
- **Process Replacement**: `exec python3 server.py` replaces the shell process entirely with Python, ensuring no lingering wrapper shells remain in memory.
- **Location Independence**: `cd "$(dirname "$0")/.."` guarantees the server boots in the project root regardless of where the launcher was invoked.

---

## Source 4: Kernel Process Inspection in `scripts/cleanup_dependencies.sh`

**Source File**: [`scripts/cleanup_dependencies.sh`](../../scripts/scratch_devcore_from_alp.sh)

```bash
check_server() {
    SERVER_PID="none"
    SERVER_VENV="none"
    for pid in $(pgrep -f "python.*server\.py" 2>/dev/null); do
        if [ "$pid" != "$$" ] && [ -d "/proc/$pid" ]; then
            local cwd venv
            cwd=$(readlink -f "/proc/$pid/cwd" 2>/dev/null || true)
            if [[ "$cwd" == *"/DevCore"* ]]; then
                venv=$(strings "/proc/$pid/environ" 2>/dev/null | grep "^VIRTUAL_ENV=" | cut -d= -f2- || true)
                SERVER_PID="$pid"
                SERVER_VENV="${venv:-system_or_unspecified}"
                break
            fi
        fi
    done
}
```

### What This Source Proves
- Inspects `/proc/$pid/cwd` to confirm the process belongs to DevCore.
- Uses `strings "/proc/$pid/environ"` to parse null-byte-separated environment blocks and identify the running virtual environment before allowing package removals.

---

## Beginner Coder Q&A: Source Code & System Evidence

### 1. "What is `tr -d '\r\n'` on line 6 of the Windows resolution block?"
Windows text ends with Carriage Return + Line Feed (`\r\n`). Linux only uses Line Feed (`\n`). Piping Windows output through `tr -d '\r\n'` deletes the invisible Windows `\r` character so it doesn't corrupt Linux path variables.

### 2. "Why does `check_server()` check `[ "$pid" != "$$" ]`?"
In Bash, `$$` represents the Process ID of the script currently running. Checking `"$pid" != "$$"` ensures the script doesn't mistake itself for the server process!

---

- **Next Evidence Chapter**: Read **[`02_02_GIT_HELPERS_AND_FLOW_EVIDENCE.md`](./02_02_GIT_HELPERS_AND_FLOW_EVIDENCE.md)** to inspect the automated Git operations code.
