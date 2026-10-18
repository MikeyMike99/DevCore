[//]: # (DOC_ID: SIRA-DEV-02_SOURCE_CODE_AND | VERSION: v1.0 | SCOPE: DEV)

# Chapter 2: Source Code & System Evidence

- **Previous**: [`01_PROBLEMS_WE_ENCOUNTERED.md`](./01_PROBLEMS_WE_ENCOUNTERED.md)
- **Next**: [`03_DIAGNOSTIC_TESTS_AND_CONCLUSIONS.md`](./03_DIAGNOSTIC_TESTS_AND_CONCLUSIONS.md)

---

[//]: # (SECTION_ID: SIRA-DEV-02_SOURCE_CODE_AND-SEC-1)
## Overview
[//]: # (SECTION_ID: SIRA-DOC-02-SEC-1)

Every engineering decision we made was backed by inspecting the live files on disk and the Linux kernel process table (`/proc`). Below are the source code blocks, relative file paths, and line numbers from the files that power our setup, followed by a plain-English analysis of what each block does.

---

[//]: # (SECTION_ID: SIRA-DEV-02_SOURCE_CODE_AND-SEC-2)
## Evidence 1: The Interactive Guard & External Helper Sourcing in `~/.bashrc`
[//]: # (SECTION_ID: SIRA-DOC-02-SEC-2)

**Source File**: `~/.bashrc` (Lines 1–9 and Lines 119–125)

```bash
# ~/.bashrc: executed by bash(1) for non-login shells.
# see /usr/share/doc/bash/examples/startup-files (in the package bash-doc)
# for examples

# If not running interactively, don't do anything
case $- in
    *i*) ;;
      *) return;;
esac
```

And in the tool loading section of `~/.bashrc`:
```bash
# Added by CLI installer
export PATH="$HOME/.local/bin:$PATH"

# Secondary Project Recording & Workflow Helpers
if [ -f "$HOME/secondary-env/secondary_project/tools/recording/helpers.sh" ]; then
    source "$HOME/secondary-env/secondary_project/tools/recording/helpers.sh"
fi
```

[//]: # (SECTION_ID: SIRA-DEV-02_SOURCE_CODE_AND-SEC-3)
### What This Proves
[//]: # (SECTION_ID: SIRA-DOC-02-SEC-3)
1. **Why Non-Interactive `bash -c` Subshells Exit Early (`case $- in *i*)`)**:
   Line 6 checks the special Bash flags variable `$-`. When a terminal is interactive (has a human typing or uses `bash -i`), `$-` contains the letter `i` (`*i*`), so Bash continues reading `.bashrc`. When a script runs non-interactively (`bash -c "..."` without `-i`), line 8 immediately executes `return;;` and stops reading `.bashrc`!
2. **Dynamic `$HOME` Path for External Helpers**:
   Instead of hardcoding absolute paths, the check uses `[ -f "$HOME/secondary-env/secondary_project/tools/recording/helpers.sh" ]` before sourcing it. If the file exists, its helper commands are loaded cleanly into the shell without errors if moved to another system.

---

[//]: # (SECTION_ID: SIRA-DEV-02_SOURCE_CODE_AND-SEC-4)
## Evidence 2: Manual Jump Commands & Automatic Folder-Based Switching in `~/.bashrc`
[//]: # (SECTION_ID: SIRA-DOC-02-SEC-4)

**Source File**: `~/.bashrc` (Auto-Environment Switcher Block)

```bash
# =============================================================================
# Automatic Virtual Environment Detection & Activation
# - Navigating into */secondary-env* automatically activates secondary-env.
# - Navigating into */DevCore* automatically activates devcore_env.
# =============================================================================
work-env() {
    if [ -f "$HOME/secondary-env/bin/activate" ]; then
        source "$HOME/secondary-env/bin/activate"
        cd "$HOME/secondary-env/secondary_project" 2>/dev/null || cd "$HOME/secondary-env" 2>/dev/null
        echo "Secondary project environment activated in $PWD"
    fi
}
alias activate-work='work-env'

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

[//]: # (SECTION_ID: SIRA-DEV-02_SOURCE_CODE_AND-SEC-5)
### Line-by-Line Technical Breakdown
[//]: # (SECTION_ID: SIRA-DOC-02-SEC-5)
1. **Jump Functions and Aliases**:
   - Checks that the virtual environment activation script exists (`[ -f ... ]`).
   - Runs `source .../bin/activate` to activate the virtual environment.
   - Navigates (`cd`) directly into the project repository (with safe fallback) and prints confirmation.
2. **Dynamic Windows Profile Resolution (`devcore-env()`)**:
   - Dynamically asks Windows `cmd.exe /c "echo %USERPROFILE%"`, strips carriage returns (`tr -d "\r\n"`), and converts the Windows path into its WSL Linux path via `wslpath -u`, then appends `/Documents/DevCore`.
   - Includes a safe fallback (`/mnt/c/Users/$USER/Documents/DevCore`) in case Windows interop is unavailable.
3. **Smart Directory Pattern Matching (`_auto_venv_hook()`)**:
   - Uses a Bash `case "$PWD" in` pattern match against the current working directory.
   - `*/secondary-env*)`: Matches the secondary environment and any subfolder inside it. The guard `[ "$VIRTUAL_ENV" != "$HOME/secondary-env" ]` ensures that if the environment is *already* active, it does nothing (zero redundant operations).
   - `*/DevCore*)`: Matches the DevCore project root and any subfolder inside it.
4. **`cd()` Wrapper and `PROMPT_COMMAND`**:
   - Every time you type `cd <target>`, `builtin cd "$@" || return $?` moves you into the folder (or stops and returns the error code `$?` if the folder doesn't exist), and immediately runs `_auto_venv_hook`.
   - `PROMPT_COMMAND` ensures that even if you open a brand-new terminal tab that starts *already inside* a project folder (without typing `cd`), `_auto_venv_hook` runs automatically before the prompt appears.

---

[//]: # (SECTION_ID: SIRA-DEV-02_SOURCE_CODE_AND-SEC-6)
## Evidence 3: The Dedicated Server Startup Script (`scripts/start_server.sh`)
[//]: # (SECTION_ID: SIRA-DOC-02-SEC-6)

**Source File**: [`scripts/start_server.sh`](../../scripts/start_server.sh)

```bash
#!/bin/bash
# Start the Web Portal server inside the dedicated virtual environment

cd "$(dirname "$0")/.." || exit 1
if [ -f "$HOME/.venvs/devcore_env/bin/activate" ]; then
    source "$HOME/.venvs/devcore_env/bin/activate"
fi
exec python3 server.py
```

[//]: # (SECTION_ID: SIRA-DEV-02_SOURCE_CODE_AND-SEC-7)
### Line-by-Line Technical Breakdown
[//]: # (SECTION_ID: SIRA-DOC-02-SEC-7)
- **`cd "$(dirname "$0")/.." || exit 1`**:
  `"$0"` is the path to `start_server.sh` itself. `dirname "$0"` gets the `scripts` folder, and `/..` steps one level up into the root project directory—regardless of which folder the user was standing in when calling the script.
- **`source "$HOME/.venvs/devcore_env/bin/activate"`**:
  Activates the dedicated virtual environment so `python3` points strictly to the isolated environment's Python binary.
- **`exec python3 server.py`**:
  `exec` replaces the shell process with `python3 server.py` directly, inheriting the activated virtual environment.

---

[//]: # (SECTION_ID: SIRA-DEV-02_SOURCE_CODE_AND-SEC-8)
## Evidence 4: The Live Process Inspector & Dependency Cleanup Script (`scripts/cleanup_dependencies.sh`)
[//]: # (SECTION_ID: SIRA-DOC-02-SEC-8)

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

And the package removal loop:
```bash
PACKAGES_TO_SCRATCH=(
    "quart"
    "sse-starlette"
    "presidio-analyzer"
    "presidio-anonymizer"
    "en-core-web-lg"
    "spacy"
    "spacy-legacy"
    "spacy-loggers"
    "thinc"
    "blis"
    "cymem"
    "murmurhash"
    "preshed"
    "srsly"
    "wasabi"
    "weasel"
    "confection"
    "cloudpathlib"
    "catalogue"
    "smart-open"
    "playwright"
    "pypdf"
    "markdown-pdf"
    "accessible-output2"
    "libloader"
    "plantuml"
    "platform-utils"
)

SCRATCHED_COUNT=0
for pkg in "${PACKAGES_TO_SCRATCH[@]}"; do
    if "$SHARED_VENV/bin/pip" show "$pkg" >/dev/null 2>&1; then
        echo "--> Removing $pkg from shared environment..."
        "$SHARED_VENV/bin/pip" uninstall -y "$pkg" >/dev/null 2>&1 || true
        SCRATCHED_COUNT=$((SCRATCHED_COUNT + 1))
    fi
done
```

[//]: # (SECTION_ID: SIRA-DEV-02_SOURCE_CODE_AND-SEC-9)
### What This Proves
[//]: # (SECTION_ID: SIRA-DOC-02-SEC-9)
1. **Kernel-Level Process Identification (`check_server()`)**:
   - `pgrep -f "python.*server\.py"` finds running Python server processes.
   - `readlink -f "/proc/$pid/cwd"` verifies the working directory.
   - `strings "/proc/$pid/environ" | grep "^VIRTUAL_ENV=" | cut -d= -f2-` extracts the exact virtual environment path that the live server booted inside.
2. **Surgical Removal of Project-Exclusive Packages**:
   - Calls `pip` strictly inside the target shared environment—never touching the dedicated environment—and removes only the specified exclusive packages.

---

[//]: # (SECTION_ID: SIRA-DEV-02_SOURCE_CODE_AND-SEC-10)
## Evidence 5: Dynamic Windows Path Resolution in External Helper Scripts
[//]: # (SECTION_ID: SIRA-DOC-02-SEC-10)

**Source File**: `<secondary_repo>/tools/recording/helpers.sh`

```bash
# Dynamically resolve the Windows Captures folder for the current user
_get_win_dest() {
    local win_profile=""
    if command -v cmd.exe >/dev/null 2>&1; then
        local raw_path
        raw_path=$(cmd.exe /c "echo %USERPROFILE%" 2>/dev/null | tr -d '\r\n')
        if [ -n "$raw_path" ]; then
            win_profile=$(wslpath -u "$raw_path" 2>/dev/null)
        fi
    fi
    if [ -n "$win_profile" ] && [ -d "$win_profile" ]; then
        echo "$win_profile/Videos/Captures"
    else
        echo "/mnt/c/Users/$USER/Videos/Captures"
    fi
}
```

[//]: # (SECTION_ID: SIRA-DEV-02_SOURCE_CODE_AND-SEC-11)
### What This Proves
[//]: # (SECTION_ID: SIRA-DOC-02-SEC-11)
- Rather than hardcoding usernames, `_get_win_dest()` dynamically queries Windows for `%USERPROFILE%`, converts it with `wslpath -u`, and falls back to `/mnt/c/Users/$USER/Videos/Captures`.

---

[//]: # (SECTION_ID: SIRA-DEV-02_SOURCE_CODE_AND-SEC-12)
## Beginner Coder Q&A: Understanding the Source Code in Chapter 2
[//]: # (SECTION_ID: SIRA-DOC-02-SEC-12)

When a beginner coder reads the Bash code in Chapter 2 for the first time, several symbols stand out. Here is what they mean in plain English:

[//]: # (SECTION_ID: SIRA-DEV-02_SOURCE_CODE_AND-SEC-1)
### 1. "What does `2>/dev/null` mean? Why is it on so many lines?"
[//]: # (SECTION_ID: SIRA-DOC-02-SEC-1)
In Linux, every command has two output channels:
- **Channel `1` (`stdout`)**: Normal output messages.
- **Channel `2` (`stderr`)**: Error messages (like `Warning: folder not found`).
- **`/dev/null`**: A special "black hole" trash can built into Linux. Anything sent to `/dev/null` disappears silently.
- Therefore, **`2>/dev/null`** simply means: *"If this command prints a noisy error message on Channel 2, throw that error message into the silent trash can so it doesn't clutter the user's screen or interrupt their screen reader!"*

[//]: # (SECTION_ID: SIRA-DEV-02_SOURCE_CODE_AND-SEC-2)
### 2. "What does `>/dev/null 2>&1` mean?"
[//]: # (SECTION_ID: SIRA-DOC-02-SEC-2)
- `>/dev/null` sends **Channel 1 (normal output)** to `/dev/null`.
- `2>&1` sends **Channel 2 (error output)** to the exact same place as Channel 1.
- Together, `>/dev/null 2>&1` means: *"Run this check completely silently—don't print normal output and don't print error output; I only care whether the command succeeded (`True`) or failed (`False`)!"*

[//]: # (SECTION_ID: SIRA-DEV-02_SOURCE_CODE_AND-SEC-3)
### 3. "In `_auto_venv_hook()`, why are there asterisks around `*/DevCore*`?"
[//]: # (SECTION_ID: SIRA-DOC-02-SEC-3)
In a Bash `case` block, the asterisk (`*`) is a **wildcard** that means *"any characters before or after this word"*:
- Because we wrote `*/DevCore*` with an asterisk at both the front and the back, it matches:
  - `/mnt/c/Users/<username>/Documents/DevCore` (the main folder)
  - `/mnt/c/Users/<username>/Documents/DevCore/playground` (a subfolder)
  - `/mnt/c/Users/<username>/Documents/DevCore/scripts` (another subfolder)
- Putting `*` on both ends guarantees that no matter how deep inside the project you navigate, Bash recognizes which project you are in.

[//]: # (SECTION_ID: SIRA-DEV-02_SOURCE_CODE_AND-SEC-4)
### 4. "Why do we check `if [[ ! "$PROMPT_COMMAND" =~ "_auto_venv_hook" ]]` before adding `_auto_venv_hook`?"
[//]: # (SECTION_ID: SIRA-DOC-02-SEC-4)
- If you edit `~/.bashrc` and type `source ~/.bashrc` multiple times in a session to reload your changes, without that check `_auto_venv_hook` would get appended multiple times to `PROMPT_COMMAND`.
- That check ensures the hook is only added once, maintaining clean and predictable terminal behavior.

---

- **Next Chapter**: Read [`03_DIAGNOSTIC_TESTS_AND_CONCLUSIONS.md`](./03_DIAGNOSTIC_TESTS_AND_CONCLUSIONS.md) to see every live test we ran to verify this code.
