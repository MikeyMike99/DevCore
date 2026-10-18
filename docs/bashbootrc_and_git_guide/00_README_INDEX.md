[//]: # (DOC_ID: SIRA-DEV-BOOT_INDEX | VERSION: v1.0 | SCOPE: DEV)

# Master Documentation Index: Bashbootrc & Automated Git Operations

Welcome to the comprehensive, beginner-friendly technical documentation suite for **Linux Shell Boot Configuration (`~/.bashrc` / "bashbootrc")**, **Virtual Environment Orchestration**, and **Automated Git Operations & Cross-OS Synchronization**.

This modular documentation suite is engineered to be 100% accessible, screen-reader optimized, and structured into the **6 Functional Documentation Pillars** so that developers at any skill level can understand, maintain, debug, and replicate these systems from scratch.

---

[//]: # (SECTION_ID: SIRA-DEV-BOOT_INDEX-SEC-1)
## Master Documentation Directory Tree
[//]: # (SECTION_ID: SIRA-DOC-00-SEC-1)

| Pillar | File Path | Role & Summary |
| :--- | :--- | :--- |
| **Pillar 00** | [`00_README_INDEX.md`](./00_README_INDEX.md) | Master directory map, system file table, and 10-second quick commands (This File). |
| **Pillar 00** | [`00_PRIMERS/00A_BEGINNER_GUIDE_TO_BASHBOOTRC_AND_VENVS.md`](./00_PRIMERS/00A_BEGINNER_GUIDE_TO_BASHBOOTRC_AND_VENVS.md) | Foundational primer on `.bashrc`, dotfiles, Python virtual environments, and auto-switching. |
| **Pillar 00** | [`00_PRIMERS/00B_BEGINNER_GUIDE_TO_GIT_AUTOMATION_AND_BRANCHING.md`](./00_PRIMERS/00B_BEGINNER_GUIDE_TO_GIT_AUTOMATION_AND_BRANCHING.md) | Foundational primer on Git branches, tracking, stashes, merge conflicts, and automated wrappers. |
| **Pillar 01** | [`01_PROBLEMS_ENCOUNTERED/01_01_BASHRC_AUTO_SWITCHING_AND_PATH_TRAPS.md`](./01_PROBLEMS_ENCOUNTERED/01_01_BASHRC_AUTO_SWITCHING_AND_PATH_TRAPS.md) | Deep breakdown of 5 shell & venv traps (boot hijacking, null-byte `/proc` files, path hardcoding). |
| **Pillar 01** | [`01_PROBLEMS_ENCOUNTERED/01_02_GIT_WORKFLOW_AND_CROSS_OS_SYNC_TRAPS.md`](./01_PROBLEMS_ENCOUNTERED/01_02_GIT_WORKFLOW_AND_CROSS_OS_SYNC_TRAPS.md) | Deep breakdown of 5 Git traps (stash loss on checkout, detached HEAD, merge clashing, `.git` corruption). |
| **Pillar 02** | [`02_SOURCE_EVIDENCE/02_01_BASHRC_AND_SYS_EVIDENCE.md`](./02_SOURCE_EVIDENCE/02_01_BASHRC_AND_SYS_EVIDENCE.md) | Verbatim source citations and line numbers from `~/.bashrc`, `start_server.sh`, and cleanup scripts. |
| **Pillar 02** | [`02_SOURCE_EVIDENCE/02_02_GIT_HELPERS_AND_FLOW_EVIDENCE.md`](./02_SOURCE_EVIDENCE/02_02_GIT_HELPERS_AND_FLOW_EVIDENCE.md) | Verbatim source citations from Git flow scripts (`start-day`, `save-work`, `git stash`, `rsync --exclude`). |
| **Pillar 03** | [`03_DIAGNOSTIC_TESTS/03_01_BASHRC_AND_VENV_DIAGNOSTIC_LOGS.md`](./03_DIAGNOSTIC_TESTS/03_01_BASHRC_AND_VENV_DIAGNOSTIC_LOGS.md) | Terminal test logs: AST scans, subshell testing, PID verification, and dependency purge tests. |
| **Pillar 03** | [`03_DIAGNOSTIC_TESTS/03_02_GIT_FLOW_AND_SYNC_TEST_LOGS.md`](./03_DIAGNOSTIC_TESTS/03_02_GIT_FLOW_AND_SYNC_TEST_LOGS.md) | Terminal test logs: Branch creation, automated stashing, merge conflict handling, and Windows sync. |
| **Pillar 04** | [`04_SOLUTIONS_AND_ARCHITECTURE/04_01_UNIFIED_BASHRC_AND_GIT_ARCHITECTURE.md`](./04_SOLUTIONS_AND_ARCHITECTURE/04_01_UNIFIED_BASHRC_AND_GIT_ARCHITECTURE.md) | Complete architectural blueprint, data flow diagrams, and state transitions. |
| **Pillar 04** | [`04_SOLUTIONS_AND_ARCHITECTURE/04_02_FUTURE_REPLICATION_AND_EXTENSION_RECIPES.md`](./04_SOLUTIONS_AND_ARCHITECTURE/04_02_FUTURE_REPLICATION_AND_EXTENSION_RECIPES.md) | Copy-paste recipes to add new project environments or custom Git workflow commands. |
| **Pillar 05** | [`05_FROM_SCRATCH_CREATION_GUIDES/05_01_BASHRC_AUTO_SWITCHER_FROM_SCRATCH.md`](./05_FROM_SCRATCH_CREATION_GUIDES/05_01_BASHRC_AUTO_SWITCHER_FROM_SCRATCH.md) | Blank Notepad line-by-line guide to creating the `.bashrc` environment block. |
| **Pillar 05** | [`05_FROM_SCRATCH_CREATION_GUIDES/05_02_GIT_AUTOMATION_HELPERS_FROM_SCRATCH.md`](./05_FROM_SCRATCH_CREATION_GUIDES/05_02_GIT_AUTOMATION_HELPERS_FROM_SCRATCH.md) | Blank Notepad line-by-line guide to writing interactive Git workflow helper scripts. |
| **Pillar 05** | [`05_FROM_SCRATCH_CREATION_GUIDES/05_03_SERVER_RUNNER_AND_MIGRATION_SCRIPTS_FROM_SCRATCH.md`](./05_FROM_SCRATCH_CREATION_GUIDES/05_03_SERVER_RUNNER_AND_MIGRATION_SCRIPTS_FROM_SCRATCH.md) | Blank Notepad line-by-line guide to writing the server launcher and cleanup scripts. |

---

[//]: # (SECTION_ID: SIRA-DEV-BOOT_INDEX-SEC-2)
## System File Map
[//]: # (SECTION_ID: SIRA-DOC-00-SEC-2)

| File / Component | Relative Location | Responsibility |
| :--- | :--- | :--- |
| `~/.bashrc` | `<user_home>/.bashrc` | Terminal boot configuration ("bashbootrc") with auto-venv detection and jump aliases. |
| Dedicated Project Venv | `<user_home>/.venvs/devcore_env` | Isolated Python 3.14 virtual environment exclusively for the primary web portal. |
| Secondary Project Venv | `<user_home>/secondary-env` | Isolated virtual environment for Git automation, cloud tools, and recording utilities. |
| Dedicated Server Boot Script | `<project_root>/scripts/start_server.sh` | Launches the primary server process locked strictly to `devcore_env`. |
| Dependency Transition Script | `<project_root>/scripts/cleanup_dependencies.sh` | Verifies running server PID/venv before safely purging shared packages. |
| Git Workflow Helpers | `<secondary_repo>/tools/recording/helpers.sh` | Interactive Git flow engine (`start-day`, `save-work`, branch management, stash guards). |

---

[//]: # (SECTION_ID: SIRA-DEV-BOOT_INDEX-SEC-3)
## 10-Second Quick-Reference Commands
[//]: # (SECTION_ID: SIRA-DEV-BOOT_INDEX-SEC-4)

### Environment Navigation
[//]: # (SECTION_ID: SIRA-DOC-00-SEC-4)
- **Automatic Switching**: Simply type `cd <folder_name>`. Navigating into a secondary project directory automatically activates its environment; navigating into DevCore automatically switches to `devcore_env`.
- **Direct Jump to DevCore**:
  ```bash
  devcore
  ```
- **Direct Jump to Secondary Project**:
  ```bash
  work-env
  ```

[//]: # (SECTION_ID: SIRA-DEV-BOOT_INDEX-SEC-5)
### Automated Git Operations
[//]: # (SECTION_ID: SIRA-DOC-00-SEC-5)
- **Start a Fresh Working Day**:
  ```bash
  start-day
  ```
  *(Pulls latest `main`, generates a clean `feature/<dev>-<date>` branch, and sets upstream tracking).*
- **Interactive Save / Merge / Sync Menu**:
  ```bash
  save-work
  ```
  *(Provides an 8-option interactive menu to commit, push, pull, rebase, or merge with automatic stash safety).*

---

[//]: # (SECTION_ID: SIRA-DEV-BOOT_INDEX-SEC-6)
## Orientation for Beginners
[//]: # (SECTION_ID: SIRA-DOC-00-SEC-6)

If you are new to Linux shell startup scripts, Python virtual environments, or Git automation, start by reading the two foundational primers:
1. **[`00_PRIMERS/00A_BEGINNER_GUIDE_TO_BASHBOOTRC_AND_VENVS.md`](./00_PRIMERS/00A_BEGINNER_GUIDE_TO_BASHBOOTRC_AND_VENVS.md)**
2. **[`00_PRIMERS/00B_BEGINNER_GUIDE_TO_GIT_AUTOMATION_AND_BRANCHING.md`](./00_PRIMERS/00B_BEGINNER_GUIDE_TO_GIT_AUTOMATION_AND_BRANCHING.md)**
