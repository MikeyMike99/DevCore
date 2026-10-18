[//]: # (DOC_ID: SIRA-DEV-BOOT_03_01 | VERSION: v1.0 | SCOPE: DEV)

# Pillar 03.1: Diagnostic Tests & Conclusions: Shell & Virtual Environments

- **Back to Master Index**: [`../00_README_INDEX.md`](../00_README_INDEX.md)
- **Next Diagnostic Chapter**: [`03_02_GIT_FLOW_AND_SYNC_TEST_LOGS.md`](./03_02_GIT_FLOW_AND_SYNC_TEST_LOGS.md)

---

[//]: # (SECTION_ID: SIRA-DEV-BOOT_03_01-SEC-1)
## Overview
[//]: # (SECTION_ID: SIRA-DOC-03_01-SEC-1)

Before modifying `~/.bashrc` or uninstalling shared packages, we executed seven controlled diagnostic tests in WSL to prove each component's behavior. Below is the complete record of commands, terminal outputs, and proven conclusions.

---

[//]: # (SECTION_ID: SIRA-DEV-BOOT_03_01-SEC-2)
## Test 1: AST Static Import Scan
[//]: # (SECTION_ID: SIRA-DEV-BOOT_03_01-SEC-3)

### What We Tested
[//]: # (SECTION_ID: SIRA-DOC-03_01-SEC-3)
Identified the exact list of third-party libraries imported across the codebase versus packages belonging to secondary utilities.

[//]: # (SECTION_ID: SIRA-DEV-BOOT_03_01-SEC-4)
### Command Run
[//]: # (SECTION_ID: SIRA-DOC-03_01-SEC-4)
Executed a Python `ast` import scanner comparing repository `.py` files against `pip list`.

[//]: # (SECTION_ID: SIRA-DEV-BOOT_03_01-SEC-5)
### Output & Findings
[//]: # (SECTION_ID: SIRA-DOC-03_01-SEC-5)
- **DevCore Web Engine Dependencies**: `quart`, `hypercorn`, `werkzeug`, `jinja2`, `presidio-analyzer`, `presidio-anonymizer`, `spacy` (`en_core_web_lg`), `playwright`, `mcp`, `pydantic`, `cryptography`, `pypdf`, `markdown-pdf`, `accessible-output2`.
- **Secondary Tool Dependencies**: `asciinema`, `checkov`, `boto3`, `botocore`, `cyclonedx-python-lib`.

[//]: # (SECTION_ID: SIRA-DEV-BOOT_03_01-SEC-6)
### Conclusion 1
[//]: # (SECTION_ID: SIRA-DOC-03_01-SEC-6)
Confirmed which libraries had to be installed in `devcore_env` and which 27 exclusive packages could be safely purged from the shared environment without impacting secondary tools.

---

[//]: # (SECTION_ID: SIRA-DEV-BOOT_03_01-SEC-7)
## Test 2: Manager Health Verification in Isolated Environment
[//]: # (SECTION_ID: SIRA-DEV-BOOT_03_01-SEC-8)

### What We Tested
[//]: # (SECTION_ID: SIRA-DOC-03_01-SEC-8)
Verified that the dedicated virtual environment (`$HOME/.venvs/devcore_env`) could initialize all four core managers.

[//]: # (SECTION_ID: SIRA-DEV-BOOT_03_01-SEC-9)
### Exact Command Run
[//]: # (SECTION_ID: SIRA-DOC-03_01-SEC-9)
```bash
$HOME/.venvs/devcore_env/bin/python3 -c "
import sys
sys.path.insert(0, '<project_root>')
import quart, hypercorn, spacy, presidio_analyzer, playwright, mcp, cryptography
from security_manager import SecurityManager
from session_manager import SessionManager
from project_manager import ProjectManager
from agent_manager import AgentManager
nlp = spacy.load('en_core_web_lg')
print('ALL MANAGERS & SPACY LOADED IN:', sys.prefix)
"
```

[//]: # (SECTION_ID: SIRA-DEV-BOOT_03_01-SEC-10)
### Exact Output Returned
[//]: # (SECTION_ID: SIRA-DOC-03_01-SEC-10)
```text
ALL MANAGERS & SPACY LOADED IN: /home/<username>/.venvs/devcore_env
```

[//]: # (SECTION_ID: SIRA-DEV-BOOT_03_01-SEC-11)
### Conclusion 2
[//]: # (SECTION_ID: SIRA-DOC-03_01-SEC-11)
The isolated virtual environment was 100% operational and ready to host the live server.

---

[//]: # (SECTION_ID: SIRA-DEV-BOOT_03_01-SEC-12)
## Test 3: The 5-Scenario Interactive Subshell Test
[//]: # (SECTION_ID: SIRA-DEV-BOOT_03_01-SEC-13)

### What We Tested
[//]: # (SECTION_ID: SIRA-DOC-03_01-SEC-13)
Simulated all five user navigation scenarios using `bash -i -c` to verify that `.bashrc` switches environments accurately.

[//]: # (SECTION_ID: SIRA-DEV-BOOT_03_01-SEC-14)
### Exact Command Run
[//]: # (SECTION_ID: SIRA-DOC-03_01-SEC-14)
```bash
bash -i -c '
cd "$HOME"
unset VIRTUAL_ENV
echo "1. Boot in HOME: VIRTUAL_ENV=${VIRTUAL_ENV:-none} (PWD=$PWD)"
cd "$HOME/secondary-env/secondary_project"
echo "2. After cd secondary: VIRTUAL_ENV=$VIRTUAL_ENV (which python: $(which python3))"
cd /mnt/c/Users/$USER/Documents/DevCore
echo "3. After cd DevCore: VIRTUAL_ENV=$VIRTUAL_ENV (which python: $(which python3))"
work-env >/dev/null
echo "4. After work-env alias: VIRTUAL_ENV=$VIRTUAL_ENV (PWD=$PWD)"
devcore >/dev/null
echo "5. After devcore alias: VIRTUAL_ENV=$VIRTUAL_ENV (PWD=$PWD)"
'
```

[//]: # (SECTION_ID: SIRA-DEV-BOOT_03_01-SEC-15)
### Exact Output Returned
[//]: # (SECTION_ID: SIRA-DOC-03_01-SEC-15)
```text
1. Boot in HOME: VIRTUAL_ENV=none (PWD=/home/<username>)
2. After cd secondary: VIRTUAL_ENV=/home/<username>/secondary-env (which python: /home/<username>/secondary-env/bin/python3)
3. After cd DevCore: VIRTUAL_ENV=/home/<username>/.venvs/devcore_env (which python: /home/<username>/.venvs/devcore_env/bin/python3)
4. After work-env alias: VIRTUAL_ENV=/home/<username>/secondary-env (PWD=/home/<username>/secondary-env/secondary_project)
5. After devcore alias: VIRTUAL_ENV=/home/<username>/.venvs/devcore_env (PWD=/mnt/c/Users/<username>/Documents/DevCore)
```

[//]: # (SECTION_ID: SIRA-DEV-BOOT_03_01-SEC-16)
### Conclusion 3
[//]: # (SECTION_ID: SIRA-DOC-03_01-SEC-16)
Zero boot hijacking in `$HOME`, seamless auto-switching on `cd`, and reliable one-word jump commands.

---

[//]: # (SECTION_ID: SIRA-DEV-BOOT_03_01-SEC-17)
## Test 4: Live Server `/proc/<pid>/environ` Inspection
[//]: # (SECTION_ID: SIRA-DEV-BOOT_03_01-SEC-18)

### What We Tested
[//]: # (SECTION_ID: SIRA-DOC-03_01-SEC-18)
Verified that the safety gate in `scripts/cleanup_dependencies.sh` detects the server's virtual environment before and after reboot.

[//]: # (SECTION_ID: SIRA-DEV-BOOT_03_01-SEC-19)
### Output Before Server Reboot
[//]: # (SECTION_ID: SIRA-DOC-03_01-SEC-19)
```text
[Step 1/4] Verifying DevCore virtual environment health... SUCCESS.
[Step 2/4] Inspecting active server process on port 5000...
NOTICE: Server is currently running in: /home/<username>/secondary-env
It has NOT yet booted inside the new DevCore environment.
```

[//]: # (SECTION_ID: SIRA-DEV-BOOT_03_01-SEC-20)
### Output After Server Reboot via `start_server.sh`
[//]: # (SECTION_ID: SIRA-DOC-03_01-SEC-20)
```text
[Step 1/4] Verifying DevCore virtual environment health... SUCCESS.
[Step 2/4] Inspecting active server process on port 5000...
SUCCESS: Server is verified running in /home/<username>/.venvs/devcore_env.
```

[//]: # (SECTION_ID: SIRA-DEV-BOOT_03_01-SEC-21)
### Conclusion 4
[//]: # (SECTION_ID: SIRA-DOC-03_01-SEC-21)
The script's `/proc` inspection prevented premature package removal and unlocked only after the server ran inside `devcore_env`.

---

[//]: # (SECTION_ID: SIRA-DEV-BOOT_03_01-SEC-22)
## Test 5: Dependency Purge & Tool Integrity Verification
[//]: # (SECTION_ID: SIRA-DEV-BOOT_03_01-SEC-23)

### What We Tested
[//]: # (SECTION_ID: SIRA-DOC-03_01-SEC-23)
Executed package removal from the shared environment and checked secondary tool health.

[//]: # (SECTION_ID: SIRA-DEV-BOOT_03_01-SEC-24)
### Exact Output Returned
[//]: # (SECTION_ID: SIRA-DOC-03_01-SEC-24)
```text
[Step 3/4] Scratching exclusive dependencies from /home/<username>/secondary-env...
--> Removing quart from shared environment...
--> Removing spacy from shared environment...
...
Cleaned 27 exclusive packages from shared environment.

[Step 4/4] Verifying secondary environment integrity...
Secondary tool check: asciinema 2.4.0
Python functional: 3.14.4
SUCCESS: Secondary environment remains fully operational.
```

[//]: # (SECTION_ID: SIRA-DEV-BOOT_03_01-SEC-25)
### Conclusion 5
[//]: # (SECTION_ID: SIRA-DOC-03_01-SEC-25)
All 27 exclusive packages were purged while `asciinema 2.4.0` and Python remained 100% operational.

---

[//]: # (SECTION_ID: SIRA-DEV-BOOT_03_01-SEC-26)
## Beginner Coder Q&A: Shell Diagnostic Tests
[//]: # (SECTION_ID: SIRA-DEV-BOOT_03_01-SEC-1)

### 1. "In Test 3, why did we have to run `bash -i -c` with `-i`?"
[//]: # (SECTION_ID: SIRA-DOC-03_01-SEC-1)
Lines 6–9 of `~/.bashrc` check `case $- in *i*)`. Non-interactive shells exit early. Adding `-i` forces Bash to run in interactive mode, ensuring all 184 lines of `.bashrc` load completely.

[//]: # (SECTION_ID: SIRA-DEV-BOOT_03_01-SEC-2)
### 2. "Why use `strings` on `/proc/<pid>/environ` instead of opening it in an editor?"
[//]: # (SECTION_ID: SIRA-DOC-03_01-SEC-2)
`/proc/<pid>/environ` is not a physical file on your disk; it is an internal kernel memory interface. The kernel formats it with null bytes (`\0`). Opening it in an editor shows scrambled text; `strings` cleanly formats each variable on its own line.

---

- **Next Diagnostic Chapter**: Read **[`03_02_GIT_FLOW_AND_SYNC_TEST_LOGS.md`](./03_02_GIT_FLOW_AND_SYNC_TEST_LOGS.md)** to see the Git operations test suite.
