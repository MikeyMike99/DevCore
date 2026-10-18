[//]: # (DOC_ID: SIRA-DEV-ENV_INDEX | VERSION: v1.0 | SCOPE: DEV)

# Bashrc ("bashbootrc") & Virtual Environment Separation Documentation Index

Welcome to the technical documentation and future setup guide for the **WSL `~/.bashrc` ("bashbootrc") Automatic Environment Switcher** and **Project vs. Secondary Virtual Environment Separation**.

This folder documents the complete investigation, system and source code evidence, diagnostic test suite, and step-by-step engineering solution used to isolate the **DevCore** environment (`~/.venvs/devcore_env`) from a secondary project environment (`~/secondary-env`), configure automatic folder-based environment switching in `~/.bashrc`, build the zero-downtime transition script ([`scripts/cleanup_dependencies.sh`](../../scripts/scratch_devcore_from_alp.sh)), and eliminate hardcoded paths across Windows and WSL.

---

[//]: # (SECTION_ID: SIRA-DEV-ENV_INDEX-SEC-1)
## Documentation Directory Contents
[//]: # (SECTION_ID: SIRA-DOC-00-SEC-1)

The documentation is organized into seven focused, screen-reader-friendly guides:

1. **[`00_README_INDEX.md`](./00_README_INDEX.md)** *(This File)*
   - Master table of contents, file map, quick-reference terminal commands, and beginner orientation.

2. **[`00A_BEGINNER_GUIDE_TO_BASHRC_AND_VIRTUAL_ENVIRONMENTS.md`](./00A_BEGINNER_GUIDE_TO_BASHRC_AND_VIRTUAL_ENVIRONMENTS.md)**
   - Beginner Developer & Coder Guide explaining from scratch:
     1. What is `~/.bashrc` ("bashbootrc"), and why does Linux run it every time you open a terminal?
     2. What is a Python Virtual Environment (`venv`), and why did mixing projects in one folder cause problems?
     3. Why did we build a "smart folder detector" (`_auto_venv_hook`) instead of forcing one environment on startup?
     4. Plain-English glossary of terms (`source`, `alias`, `$HOME`, `$USER`, `$PWD`, `$VIRTUAL_ENV`, `PROMPT_COMMAND`, `wslpath`, `/proc`).
     5. Why the order of lines in `~/.bashrc` matters.

3. **[`01_PROBLEMS_WE_ENCOUNTERED.md`](./01_PROBLEMS_WE_ENCOUNTERED.md)**
   - Plain-English explanation of the five problems encountered during the environment separation and `.bashrc` setup:
     1. **Mixed Dependencies & The Port 5000 Zero-Downtime Trap**: Core web engine packages and secondary tool packages tangled in one venv while the server was actively running on Port 5000.
     2. **Forcing a Default Boot Environment vs. Auto-Switching by Folder**: Why hard-activating an environment at the bottom of `.bashrc` hijacked every terminal, and how we pivoted to automatic directory detection (`cd`).
     3. **Hardcoded Absolute User Paths Across WSL and Windows**: Why hardcoded usernames break portability and how dynamic resolution solved it.
     4. **The Null-Byte `/proc/$pid/environ` Trap When Checking the Live Server**: Why standard `grep` failed to detect which virtual environment the running server was using, and how `strings` solved it.
     5. **Home Directory (`~`) Clutter & Keeping Project Helpers Clean**: Cleaning leftover archive chunks and scratch files while keeping tool helper scripts strictly separated.
   - Includes a dedicated **Beginner Coder Q&A** section.

4. **[`02_SOURCE_CODE_AND_SYSTEM_EVIDENCE.md`](./02_SOURCE_CODE_AND_SYSTEM_EVIDENCE.md)**
   - Quotes, file locations, and line-by-line analysis from the primary files:
     - `~/.bashrc` (Interactive guard, helper script sourcing, environment switchers, `_auto_venv_hook()`, `cd()` wrapper, and `PROMPT_COMMAND`).
     - [`scripts/start_server.sh`](../../scripts/start_server.sh) (Server boot script).
     - [`scripts/cleanup_dependencies.sh`](../../scripts/scratch_devcore_from_alp.sh) (4-stage verification, `/proc` inspection, and dependency purge script).
     - Project recording helper scripts (Dynamic Windows destination resolution and `$HOME` portability).
   - Includes a dedicated **Beginner Coder Q&A** section.

5. **[`03_DIAGNOSTIC_TESTS_AND_CONCLUSIONS.md`](./03_DIAGNOSTIC_TESTS_AND_CONCLUSIONS.md)**
   - Every command and live test executed, the exact outputs returned, and how each test proved our conclusions:
     - **Test 1**: AST Static Import Scan across the entire codebase.
     - **Test 2**: Core Manager Verification (`SecurityManager`, `SessionManager`, `ProjectManager`, `AgentManager`) inside the isolated virtual environment.
     - **Test 3**: 5-Scenario Interactive Subshell Test of `_auto_venv_hook`, `cd`, and jump aliases.
     - **Test 4**: Dynamic Windows `%USERPROFILE%` + `wslpath -u` Path Resolution Test.
     - **Test 5**: Live Server `/proc/<pid>/environ` Inspection (`--check` before and after server reboot).
     - **Test 6**: Dependency Purge execution and verifying tool integrity.
     - **Test 7**: Home Directory (`~`) File Audit and Space Reclamation Verification.
   - Includes a dedicated **Beginner Coder Q&A** section.

6. **[`04_STEP_BY_STEP_SOLUTION_AND_ENVIRONMENT_GUIDE.md`](./04_STEP_BY_STEP_SOLUTION_AND_ENVIRONMENT_GUIDE.md)**
   - Architecture walkthrough of how the 5 parts of the final solution fit together, why the top-to-bottom execution order inside `~/.bashrc` matters, and how to replicate this pattern for any future project environment.
   - Includes a dedicated **Beginner Coder Q&A** section.

7. **[`05_STEP_BY_STEP_BASHRC_AND_SCRIPTS_CREATION_GUIDE.md`](./05_STEP_BY_STEP_BASHRC_AND_SCRIPTS_CREATION_GUIDE.md)**
   - A complete beginner's guide to writing the `~/.bashrc` auto-switching block, [`scripts/start_server.sh`](../../scripts/start_server.sh), and [`scripts/cleanup_dependencies.sh`](../../scripts/scratch_devcore_from_alp.sh) from a blank file, explaining every Bash symbol (`#!/usr/bin/env bash`, `set -e`, `case ... esac`, `builtin cd "$@"`, `2>/dev/null`, `${VAR:-default}`, and `PROMPT_COMMAND`) line by line.

---

[//]: # (SECTION_ID: SIRA-DEV-ENV_INDEX-SEC-2)
## System & Project File Map
[//]: # (SECTION_ID: SIRA-DOC-00-SEC-2)

| File / Directory | Location | Role |
| :--- | :--- | :--- |
| `~/.bashrc` | `<user_home>/.bashrc` | Personal Bash startup configuration ("bashbootrc") with auto-venv switching and jump commands |
| `~/.venvs/devcore_env` | `<user_home>/.venvs/devcore_env` | Dedicated Linux ext4 Python virtual environment exclusively for DevCore |
| `~/secondary-env` | `<user_home>/secondary-env` | Dedicated Python virtual environment for secondary project tools (`asciinema`, security tools, etc.) |
| [`start_server.sh`](../../scripts/start_server.sh) | `<project_root>/scripts/start_server.sh` | Launches the web server strictly inside `~/.venvs/devcore_env` |
| [`cleanup_dependencies.sh`](../../scripts/scratch_devcore_from_alp.sh) | `<project_root>/scripts/cleanup_dependencies.sh` | Verifies active server PID/venv and purges exclusive packages from shared environment |
| `helpers.sh` | `<secondary_repo>/tools/recording/helpers.sh` | Terminal recording & Git workflow helpers (kept 100% separate from DevCore) |

---

[//]: # (SECTION_ID: SIRA-DEV-ENV_INDEX-SEC-3)
## Quick-Reference Everyday Commands
[//]: # (SECTION_ID: SIRA-DOC-00-SEC-3)

Once your terminal is open, you have two ways to switch environments:

[//]: # (SECTION_ID: SIRA-DEV-ENV_INDEX-SEC-4)
### Option A: Automatic Switching (Just `cd` Into Any Project Folder)
[//]: # (SECTION_ID: SIRA-DOC-00-SEC-4)
- Navigate anywhere inside the secondary project:
  ```bash
  cd ~/secondary-env/secondary_project
  ```
  *Result*: `~/.bashrc` automatically detects `*/secondary-env*` and activates `($HOME/secondary-env)`.
- Navigate anywhere inside DevCore:
  ```bash
  cd /mnt/c/Users/<username>/Documents/DevCore
  ```
  *Result*: `~/.bashrc` automatically detects `*/DevCore*` and activates `($HOME/.venvs/devcore_env)`.

[//]: # (SECTION_ID: SIRA-DEV-ENV_INDEX-SEC-5)
### Option B: Instant One-Word Jump Commands (From Anywhere)
[//]: # (SECTION_ID: SIRA-DOC-00-SEC-5)
- Type **`work-env`** (or **`activate-work`**):
  Activates `~/secondary-env` and immediately jumps (`cd`) into `~/secondary-env/secondary_project`.
- Type **`devcore`** (or **`devcore-env`**):
  Activates `~/.venvs/devcore_env` and immediately jumps (`cd`) into your Windows `Documents/DevCore` folder.

---

[//]: # (SECTION_ID: SIRA-DEV-ENV_INDEX-SEC-6)
## New to Bash Startup Files or Virtual Environments? Start Here First!
[//]: # (SECTION_ID: SIRA-DOC-00-SEC-6)

If you are a beginner developer reading this documentation for the first time—and you did not write `~/.bashrc` and have never built an automatic virtual environment switcher before—read **[`00A_BEGINNER_GUIDE_TO_BASHRC_AND_VIRTUAL_ENVIRONMENTS.md`](./00A_BEGINNER_GUIDE_TO_BASHRC_AND_VIRTUAL_ENVIRONMENTS.md)** before diving into Chapter 1.
