# Chapter 5: Beginner's Step-by-Step Guide to Creating the `~/.bashrc` Block & Shell Scripts From Scratch

- **Previous**: [`04_STEP_BY_STEP_SOLUTION_AND_ENVIRONMENT_GUIDE.md`](./04_STEP_BY_STEP_SOLUTION_AND_ENVIRONMENT_GUIDE.md)
- **Back to Index**: [`00_README_INDEX.md`](./00_README_INDEX.md)

---

## Introduction (From One Beginner Coder to Another)

When you first open `~/.bashrc`, [`scripts/start_server.sh`](../../scripts/start_server.sh), or [`scripts/cleanup_dependencies.sh`](../../scripts/scratch_devcore_from_alp.sh) as a beginner developer, seeing syntax like `#!/usr/bin/env bash`, `set -e`, `case "$PWD" in`, `builtin cd "$@" || return $?`, `${DEVCORE_VENV:-$HOME/.venvs/devcore_env}`, and `PROMPT_COMMAND` can look intimidating.

You might ask:
- *"How do I edit `.bashrc` or create a `.sh` file safely without breaking my terminal?"*
- *"What happens if I save a `.sh` file in Windows Notepad—why does Linux complain about `\r: command not found`?"*
- *"How did you build the `~/.bashrc` environment switcher and cleanup scripts step by step from a blank screen?"*

This guide walks you through building **every single part from scratch, one small block at a time**, explaining why every line is there and what breaks if you leave it out.

---

## Step 0: Three Golden Safety Rules Before Editing `.bashrc` or Creating `.sh` Scripts

Before typing a single line of Bash code, every beginner developer should know these three life-saving rules:

### Rule 1: Always Make a 1-Second Backup Before Editing `~/.bashrc`
Before you edit `~/.bashrc`, run this single command in your terminal:
```bash
cp ~/.bashrc ~/.bashrc.backup
```
- **Why?** If you accidentally make a typo in `~/.bashrc`, you can restore your original working file in one second by typing `cp ~/.bashrc.backup ~/.bashrc`!

### Rule 2: Beware the Windows Notepad Line-Ending Trap (`CRLF` vs. `LF`)
- On **Windows**, pressing `Enter` at the end of a line inserts **two** invisible characters: Carriage Return + Line Feed (`\r\n`, called `CRLF`).
- On **Linux (WSL)**, pressing `Enter` inserts only **one** character: Line Feed (`\n`, called `LF`).
- **The Trap**: If you edit `~/.bashrc` or a `.sh` script using an old Windows editor that saves `CRLF` (`\r\n`), Bash sees the invisible `\r` at the end of every line and throws bizarre errors like `$'\r': command not found` or `syntax error near unexpected token $'in\r'`.
- **The Easy Fix**: If a `.sh` file or `.bashrc` ever gets Windows line endings, run this one-line Linux command to strip out every invisible `\r` instantly:
  ```bash
  sed -i 's/\r$//' ~/.bashrc
  ```

### Rule 3: Remember `chmod +x` When Creating a New `.sh` Script
On Windows, naming a file `.bat` automatically makes it runnable. On Linux, creating a new `.sh` file starts out as a regular text file that cannot be executed directly until you give it **"Execute Permission" (`+x`)**:
```bash
chmod +x scripts/start_server.sh
```

---

## Part 1: Building the `~/.bashrc` ("bashbootrc") Auto-Switcher Block Step by Step

Below is how to write the auto-environment switching block at the bottom of `~/.bashrc` from scratch, broken into 5 small, easy-to-follow steps.

### Step 1.1: Add User Binary Directories to `$PATH` and Load Helper Toolkits
At the bottom of the default `.bashrc`, add these lines first:

```bash
# Added by CLI installer
export PATH="$HOME/.local/bin:$PATH"

# Secondary Project Recording & Git Flow Helpers
if [ -f "$HOME/secondary-env/secondary_project/tools/recording/helpers.sh" ]; then
    source "$HOME/secondary-env/secondary_project/tools/recording/helpers.sh"
fi
```

#### Beginner Line-by-Line Explanation
- **`export PATH="$HOME/.local/bin:$PATH"`**:
  `$PATH` is a colon-separated list of folders that Linux searches whenever you type a command. Putting `$HOME/.local/bin:` at the front tells Linux: *"Look inside my local bin directory first when I type custom commands."*
- **`if [ -f "$HOME/.../helpers.sh" ]; then`**:
  `[ -f ... ]` means *"Does this regular file exist?"* Checking `[ -f ... ]` first ensures that if you ever move or rename the folder, opening a terminal won't print an ugly `No such file or directory` error!
- **`source "$HOME/.../helpers.sh"`**:
  Loads external helper commands into the current terminal session.

---

### Step 1.2: Create the Secondary Project Jump & Activate Command
Next, write the function that lets you type a quick shortcut from anywhere to activate the secondary environment and jump straight into its project folder:

```bash
work-env() {
    if [ -f "$HOME/secondary-env/bin/activate" ]; then
        source "$HOME/secondary-env/bin/activate"
        cd "$HOME/secondary-env/secondary_project" 2>/dev/null || cd "$HOME/secondary-env" 2>/dev/null
        echo "Secondary project environment activated in $PWD"
    fi
}
alias activate-work='work-env'
```

#### Beginner Line-by-Line Explanation
- **`work-env() { ... }`**:
  Creates a new terminal command named `work-env`.
- **`source "$HOME/secondary-env/bin/activate"`**:
  Activates the secondary Python virtual environment.
- **`cd ... 2>/dev/null || cd ... 2>/dev/null`**:
  - The double vertical bar **`||`** means **"OR (if the first command fails, run the second command)"**.
  - It tries to `cd` into the main repository first; if that subfolder doesn't exist, it falls back to the parent environment directory.
- **`alias activate-work='work-env'`**:
  Makes `activate-work` a synonym for `work-env`.

---

### Step 1.3: Create the DevCore Jump & Activate Command
Right below the secondary jump alias, write the DevCore jump function with dynamic Windows path detection:

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
```

#### Beginner Line-by-Line Explanation
- **`local devcore_dir=""`**:
  The keyword `local` creates a temporary variable that exists *only* inside this function so it never pollutes your terminal's global variables.
- **`raw=$(cmd.exe /c "echo %USERPROFILE%" 2>/dev/null | tr -d "\r\n")`**:
  Asks Windows for your real Windows user profile folder (e.g., `C:\Users\<username>`) and uses `tr -d "\r\n"` to delete the trailing line break.
- **`[ -n "$raw" ] && devcore_dir="$(wslpath -u "$raw" 2>/dev/null)/Documents/DevCore"`**:
  - `[ -n "$raw" ]` checks that `$raw` is **n**ot empty.
  - `&&` means **"AND THEN"**.
  - `wslpath -u "$raw"` converts `C:\Users\<username>` into `/mnt/c/Users/<username>`, and appends `/Documents/DevCore`.
- **`if [ -z "$devcore_dir" ] || [ ! -d "$devcore_dir" ]; then`**:
  - If the dynamic resolution fails, it falls back safely to `/mnt/c/Users/$USER/Documents/DevCore`.

---

### Step 1.4: Write the Smart Folder Watcher `_auto_venv_hook()`
Now write the heart of the automatic environment switcher:

```bash
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
```

#### Beginner Line-by-Line Explanation
- **`case "$PWD" in ... esac`**:
  Inspects your current folder path (`$PWD`).
- **`*/secondary-env*)`**:
  If your current folder path contains `/secondary-env` anywhere inside it:
  - It checks `[ "$VIRTUAL_ENV" != "$HOME/secondary-env" ]`.
  - If it isn't active yet, it runs `source "$HOME/secondary-env/bin/activate"`.
- **`*/DevCore*)`**:
  If your current folder path contains `/DevCore` anywhere inside it:
  - It checks `[ "$VIRTUAL_ENV" != "$HOME/.venvs/devcore_env" ]`.
  - If it isn't active yet, it runs `source "$HOME/.venvs/devcore_env/bin/activate"`.

---

### Step 1.5: Connect `_auto_venv_hook` to `cd` and `PROMPT_COMMAND`
Finally, add these lines at the very bottom of `~/.bashrc`:

```bash
cd() {
    builtin cd "$@" || return $?
    _auto_venv_hook
}

if [[ ! "$PROMPT_COMMAND" =~ "_auto_venv_hook" ]]; then
    PROMPT_COMMAND="_auto_venv_hook${PROMPT_COMMAND:+; $PROMPT_COMMAND}"
fi
```

#### Beginner Line-by-Line Explanation
- **`builtin cd "$@" || return $?`**:
  - Runs the real built-in `cd` command with whatever folder arguments (`"$@"`) you typed.
  - If `builtin cd` fails, `|| return $?` immediately exits with the error code (`$?`).
  - If `builtin cd` succeeds, the next line (`_auto_venv_hook`) checks your new folder and activates the matching virtual environment!
- **`PROMPT_COMMAND="_auto_venv_hook${PROMPT_COMMAND:+; $PROMPT_COMMAND}"`**:
  - Ensures `_auto_venv_hook` also runs automatically whenever a new terminal prompt appears (such as when an editor opens a new tab directly inside a project folder).

---

## Part 2: Building `scripts/start_server.sh` From Scratch (8 Lines)

**Target File**: [`scripts/start_server.sh`](../../scripts/start_server.sh)

When you create `scripts/start_server.sh` from a blank file:

```bash
#!/bin/bash
# Start the Web Portal server inside the dedicated virtual environment

cd "$(dirname "$0")/.." || exit 1
if [ -f "$HOME/.venvs/devcore_env/bin/activate" ]; then
    source "$HOME/.venvs/devcore_env/bin/activate"
fi
exec python3 server.py
```

### Beginner Line-by-Line Explanation
1. **`#!/bin/bash`**:
   The shebang line telling Linux to use Bash.
2. **`cd "$(dirname "$0")/.." || exit 1`**:
   Locates the script's directory and steps up to the project root folder.
3. **`source "$HOME/.venvs/devcore_env/bin/activate"`**:
   Activates the dedicated virtual environment before launching Python.
4. **`exec python3 server.py`**:
   Starts `server.py` using the dedicated environment's Python binary.

---

## Part 3: Building `scripts/cleanup_dependencies.sh` Step by Step

**Target File**: [`scripts/cleanup_dependencies.sh`](../../scripts/scratch_devcore_from_alp.sh)

Here is how its 4 building blocks work:

### Block 1: Safety Header, Default Variables, and Command Flags
```bash
#!/usr/bin/env bash
set -e

DEVCORE_VENV="${DEVCORE_VENV:-$HOME/.venvs/devcore_env}"
SHARED_VENV="${SHARED_VENV:-$HOME/secondary-env}"
SERVER_PORT=5000

MODE="run"
if [ "$1" = "--check" ]; then
    MODE="check"
elif [ "$1" = "--watch" ]; then
    MODE="watch"
elif [ "$1" = "--force" ]; then
    MODE="force"
fi
```

### Block 2: Step 1 — Preflight Health Check on Dedicated Environment
```bash
if ! "$DEVCORE_VENV/bin/python3" -c "
import quart, hypercorn, spacy, presidio_analyzer, playwright, mcp, cryptography
" 2>/dev/null; then
    echo "ERROR: Virtual environment is missing required core dependencies."
    exit 1
fi
```

### Block 3: Step 2 — Kernel `/proc` Inspection of the Live Server Process
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

### Block 4: Steps 3 & 4 — Dependency Purge Loop & Health Verification
```bash
SCRATCHED_COUNT=0
for pkg in "${PACKAGES_TO_SCRATCH[@]}"; do
    if "$SHARED_VENV/bin/pip" show "$pkg" >/dev/null 2>&1; then
        echo "--> Removing $pkg from shared environment..."
        "$SHARED_VENV/bin/pip" uninstall -y "$pkg" >/dev/null 2>&1 || true
        SCRATCHED_COUNT=$((SCRATCHED_COUNT + 1))
    fi
done
```

---

## Summary Checklist: How to Verify Your Setup Anytime in 10 Seconds

Whenever you want to verify that your environment setup is working properly:

```bash
# 1. Check server & environment status without making changes:
bash ./scripts/cleanup_dependencies.sh --check

# 2. Jump to secondary environment:
work-env

# 3. Jump to DevCore:
devcore
```

---

- **Back to Master Index**: [`00_README_INDEX.md`](./00_README_INDEX.md)
