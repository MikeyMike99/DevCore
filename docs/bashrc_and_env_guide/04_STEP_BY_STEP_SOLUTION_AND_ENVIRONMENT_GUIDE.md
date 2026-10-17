[//]: # (DOC_ID: SIRA-DOC-04 | VERSION: v1.0 | SCOPE: Siraugga / DevCore Framework)

# Chapter 4: Step-by-Step Solution & Future Environment Guide

- **Previous**: [`03_DIAGNOSTIC_TESTS_AND_CONCLUSIONS.md`](./03_DIAGNOSTIC_TESTS_AND_CONCLUSIONS.md)
- **Next**: [`05_STEP_BY_STEP_BASHRC_AND_SCRIPTS_CREATION_GUIDE.md`](./05_STEP_BY_STEP_BASHRC_AND_SCRIPTS_CREATION_GUIDE.md)
- **Back to Index**: [`00_README_INDEX.md`](./00_README_INDEX.md)

---

## Overview of the Complete 5-Part Engineering Solution
[//]: # (SECTION_ID: SIRA-DOC-04-SEC-1)

To completely separate **DevCore** and a secondary project environment while making everyday terminal usage effortless, our final architecture combines five components that work together seamlessly:

1. **Dedicated Native Linux Virtual Environments**:
   - **Secondary Environment**: `$HOME/secondary-env` (contains `asciinema`, `checkov`, `boto3`, `cyclonedx`, etc.).
   - **DevCore Environment**: `$HOME/.venvs/devcore_env` (contains `quart`, `hypercorn`, `spacy`, `presidio`, `playwright`, `mcp`, `cryptography`, `accessible-output2`, etc.).
2. **Automatic Folder-Based Environment Switching (`_auto_venv_hook` in `~/.bashrc`)**:
   - Watches `$PWD` whenever you change directories (`cd`) or open a new terminal prompt (`PROMPT_COMMAND`).
   - Entering `*/secondary-env*` automatically activates `$HOME/secondary-env`.
   - Entering `*/DevCore*` automatically activates `$HOME/.venvs/devcore_env`.
3. **One-Word Jump + Activate Shortcuts in `~/.bashrc`**:
   - Typing `work-env` (or `activate-work`) activates `secondary-env` and jumps directly into the secondary project repository.
   - Typing `devcore` (or `devcore-env`) activates `devcore_env` and dynamically resolves and jumps into `/mnt/c/Users/<username>/Documents/DevCore`.
4. **Dedicated Server Boot Script ([`scripts/start_server.sh`](../../scripts/start_server.sh))**:
   - Guarantees that `server.py` always launches inside `$HOME/.venvs/devcore_env` regardless of which folder or terminal launched it.
5. **Safe Process-Verified Cleanup Tool ([`scripts/cleanup_dependencies.sh`](../../scripts/scratch_devcore_from_alp.sh))**:
   - Verifies the dedicated environment health, inspects the live server's `/proc/$pid/environ` using `strings`, and purges exclusive packages from the shared environment only after confirming the server is running inside the dedicated environment.

---

## Why the Top-to-Bottom Execution Order in `~/.bashrc` Is Mandatory
[//]: # (SECTION_ID: SIRA-DOC-04-SEC-2)

The lines inside `~/.bashrc` must follow this exact 6-step order from top to bottom:

| Step | Lines in `~/.bashrc` | What Happens | Why It Must Be in This Exact Position |
| :--- | :--- | :--- | :--- |
| **1** | Top of file | `case $- in *i*) ;; *) return;; esac` | **Must be first**: Immediately stops `.bashrc` during non-interactive background commands (`scp`, `rsync`) so custom prompts or output never break automated pipelines. |
| **2** | Standard config | History, window size, colors, prompt, and standard aliases (`ll`, `la`) | Sets up the standard shell foundation before custom project tools are loaded. |
| **3** | Tool paths | `export PATH="$HOME/.local/bin:$PATH"` | Adds user binary directories to `$PATH` before any custom functions or scripts try to run CLI tools. |
| **4** | Tool helpers | `source "$HOME/.../helpers.sh"` | Loads external tool and Git workflow helpers before our custom `cd()` wrapper is defined. |
| **5** | Function definitions | Defines jump functions and `_auto_venv_hook()` | **Must come before Step 6**: Bash must read and memorize the function definitions *before* `cd()` or `PROMPT_COMMAND` attempts to call them. |
| **6** | Bottom of file | Defines `cd()` wrapper and registers `PROMPT_COMMAND` | **Must be last**: Hooks `_auto_venv_hook` into directory changes and prompt rendering after all functions and external scripts have finished loading. |

---

## How to Add a 3rd Project Environment in the Future (Copy-Paste Recipe)
[//]: # (SECTION_ID: SIRA-DOC-04-SEC-3)

Suppose six months from now you start a brand-new Python project called **`AudioStudio`** located in `/mnt/c/Users/<username>/Documents/AudioStudio`, and you want it to have its own isolated virtual environment and automatic folder switching.

Here are the 3 steps to do it yourself:

### Step 1: Create the New Virtual Environment Inside `~/.venvs/`
[//]: # (SECTION_ID: SIRA-DOC-04-SEC-4)
Open your WSL terminal and run:
```bash
python3 -m venv "$HOME/.venvs/audiostudio"
source "$HOME/.venvs/audiostudio/bin/activate"
pip install --upgrade pip
```

### Step 2: Add a 5-Line Case Block Inside `_auto_venv_hook()` in `~/.bashrc`
[//]: # (SECTION_ID: SIRA-DOC-04-SEC-5)
Open `~/.bashrc` and add your new project's folder pattern right below `*/DevCore*)`:
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
        */AudioStudio*)
            if [ "$VIRTUAL_ENV" != "$HOME/.venvs/audiostudio" ] && [ -f "$HOME/.venvs/audiostudio/bin/activate" ]; then
                source "$HOME/.venvs/audiostudio/bin/activate"
            fi
            ;;
    esac
}
```

### Step 3: Reload `~/.bashrc`
[//]: # (SECTION_ID: SIRA-DOC-04-SEC-6)
Run:
```bash
source ~/.bashrc
```
That's it! From that moment on, every time you `cd` into `AudioStudio`, your terminal will automatically switch into `(.venvs/audiostudio)`.

---

## Beginner Coder Q&A: Understanding the Architecture in Chapter 4
[//]: # (SECTION_ID: SIRA-DOC-04-SEC-7)

### 1. "What happens when I am inside `DevCore` (so `devcore_env` is active) and I `cd ~` back to the home directory?"
[//]: # (SECTION_ID: SIRA-DOC-04-SEC-1)
- In `_auto_venv_hook()`, it checks `*/secondary-env*)` and `*/DevCore*)`.
- If you are working on DevCore and you briefly `cd /tmp` or `cd ~` to check a file, `_auto_venv_hook()` intentionally leaves your current environment active so your workflow isn't disrupted.
- The moment you `cd` into another project, `_auto_venv_hook()` immediately switches to that project's environment. And if you ever want to manually turn off all virtual environments completely, you can type:
  ```bash
  deactivate
  ```

### 2. "Why do we put new virtual environments inside a hidden `~/.venvs/` folder (`$HOME/.venvs/devcore_env`) instead of scattering them in `/home/<username>/`?"
[//]: # (SECTION_ID: SIRA-DOC-04-SEC-2)
- If you create a new folder directly in your home directory for every project (`~/devcore-env`, `~/audio-env`, `~/test-env`), your home directory quickly becomes crowded and hard to navigate with a screen reader.
- Grouping virtual environments neatly inside `~/.venvs/<project_name>` keeps your home directory completely clean while storing all environments on fast native Linux `ext4` storage.

---

- **Next Chapter**: Continue to **[`05_STEP_BY_STEP_BASHRC_AND_SCRIPTS_CREATION_GUIDE.md`](./05_STEP_BY_STEP_BASHRC_AND_SCRIPTS_CREATION_GUIDE.md)** for a complete, line-by-line beginner's guide to writing the `~/.bashrc` configuration block, `start_server.sh`, and `cleanup_dependencies.sh` from a blank file!
