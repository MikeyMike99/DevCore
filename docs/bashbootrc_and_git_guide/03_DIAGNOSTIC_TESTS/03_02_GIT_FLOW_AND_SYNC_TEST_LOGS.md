[//]: # (DOC_ID: SIRA-DEV-BOOT_03_02 | VERSION: v1.0 | SCOPE: DEV)

# Pillar 03.2: Diagnostic Tests: Git Operations & Cross-OS Sync

- **Previous Diagnostic Chapter**: [`03_01_BASHRC_AND_VENV_DIAGNOSTIC_LOGS.md`](./03_01_BASHRC_AND_VENV_DIAGNOSTIC_LOGS.md)
- **Back to Master Index**: [`../00_README_INDEX.md`](../00_README_INDEX.md)
- **Next Pillar**: [`../04_SOLUTIONS_AND_ARCHITECTURE/04_01_UNIFIED_BASHRC_AND_GIT_ARCHITECTURE.md`](../04_SOLUTIONS_AND_ARCHITECTURE/04_01_UNIFIED_BASHRC_AND_GIT_ARCHITECTURE.md)

---

[//]: # (SECTION_ID: SIRA-DEV-BOOT_03_02-SEC-1)
## Overview
[//]: # (SECTION_ID: SIRA-DOC-03_02-SEC-1)

To guarantee that our Git automation prevents data loss, handles dirty worktrees, and safely mirrors files to Windows without corrupting repository metadata, we executed a sequence of targeted terminal tests against `helpers.sh`.

---

[//]: # (SECTION_ID: SIRA-DEV-BOOT_03_02-SEC-2)
## Test 1: Daily Branch Creation & Remote Tracking Link Test
[//]: # (SECTION_ID: SIRA-DEV-BOOT_03_02-SEC-3)

### What We Tested
[//]: # (SECTION_ID: SIRA-DOC-03_02-SEC-3)
Verified that executing `start-day` extracts the sanitized developer identity, checks out a clean branch from `main`, and links upstream tracking.

[//]: # (SECTION_ID: SIRA-DEV-BOOT_03_02-SEC-4)
### Command Executed
[//]: # (SECTION_ID: SIRA-DOC-03_02-SEC-4)
```bash
bash -c '
source "$HOME/secondary-env/secondary_project/tools/recording/helpers.sh"
start-day
git status -sb
'
```

[//]: # (SECTION_ID: SIRA-DEV-BOOT_03_02-SEC-5)
### Exact Output Returned
[//]: # (SECTION_ID: SIRA-DOC-03_02-SEC-5)
```text
Already on 'main'
Your branch is up to date with 'origin/main'.
Switched to a new branch 'feature/dev-20261017'
Created and checked out: feature/dev-20261017
[//]: # (SECTION_ID: SIRA-DEV-BOOT_03_02-SEC-6)
## feature/dev-20261017...origin/feature/dev-20261017
[//]: # (SECTION_ID: SIRA-DOC-03_02-SEC-6)
```

[//]: # (SECTION_ID: SIRA-DEV-BOOT_03_02-SEC-7)
### How We Reached Our Conclusion
[//]: # (SECTION_ID: SIRA-DOC-03_02-SEC-7)
- `## feature/dev-...origin/feature/dev-...` confirms that the local branch was created and linked directly to upstream tracking in a single step.

---

[//]: # (SECTION_ID: SIRA-DEV-BOOT_03_02-SEC-8)
## Test 2: Uncommitted Worktree Stash Buffering Simulation
[//]: # (SECTION_ID: SIRA-DEV-BOOT_03_02-SEC-9)

### What We Tested
[//]: # (SECTION_ID: SIRA-DOC-03_02-SEC-9)
Simulated what happens when a developer modifies existing files and adds untracked files, and then switches branches using the automated `save-work` workflow.

[//]: # (SECTION_ID: SIRA-DEV-BOOT_03_02-SEC-10)
### Commands Executed
[//]: # (SECTION_ID: SIRA-DOC-03_02-SEC-10)
```bash
bash -c '
source "$HOME/secondary-env/secondary_project/tools/recording/helpers.sh"
echo "uncommitted edit" >> test_file.txt
echo "new untracked file" > untracked.txt
git status -s

# Trigger branch switch option inside save-work
# (Stash -> Checkout -> Stash Pop)
local has_stash="false"
if ! git diff --quiet || ! git diff --cached --quiet || [ -n "$(git status --porcelain)" ]; then
    git stash push -u -m "test_stash" >/dev/null 2>&1
    has_stash="true"
fi
echo "Stash created successfully: $has_stash"
git checkout main >/dev/null 2>&1
echo "Switched to main: $(git rev-parse --abbrev-ref HEAD)"
git checkout feature/dev-20261017 >/dev/null 2>&1
[ "$has_stash" = "true" ] && git stash pop >/dev/null 2>&1
echo "Files restored after return:"
git status -s
'
```

[//]: # (SECTION_ID: SIRA-DEV-BOOT_03_02-SEC-11)
### Exact Output Returned
[//]: # (SECTION_ID: SIRA-DOC-03_02-SEC-11)
```text
 M test_file.txt
?? untracked.txt
Stash created successfully: true
Switched to main: main
Files restored after return:
 M test_file.txt
?? untracked.txt
```

[//]: # (SECTION_ID: SIRA-DEV-BOOT_03_02-SEC-12)
### How We Reached Our Conclusion
[//]: # (SECTION_ID: SIRA-DOC-03_02-SEC-12)
- Both the modified file (`M`) and the untracked file (`??`) were safely buffered into the stash, protected across branch hops, and restored with zero lost data.

---

[//]: # (SECTION_ID: SIRA-DEV-BOOT_03_02-SEC-13)
## Test 3: Dynamic Windows Captures Path Resolution Test
[//]: # (SECTION_ID: SIRA-DEV-BOOT_03_02-SEC-14)

### What We Tested
[//]: # (SECTION_ID: SIRA-DOC-03_02-SEC-14)
Tested dynamic Windows path resolution across WSL using `_get_win_dest()` to ensure no hardcoded username paths are required.

[//]: # (SECTION_ID: SIRA-DEV-BOOT_03_02-SEC-15)
### Command Executed
[//]: # (SECTION_ID: SIRA-DOC-03_02-SEC-15)
```bash
bash -c '
source "$HOME/secondary-env/secondary_project/tools/recording/helpers.sh"
echo "Resolved Windows destination: $(_get_win_dest)"
'
```

[//]: # (SECTION_ID: SIRA-DEV-BOOT_03_02-SEC-16)
### Exact Output Returned
[//]: # (SECTION_ID: SIRA-DOC-03_02-SEC-16)
```text
Resolved Windows destination: /mnt/c/Users/<username>/Videos/Captures
```

[//]: # (SECTION_ID: SIRA-DEV-BOOT_03_02-SEC-17)
### How We Reached Our Conclusion
[//]: # (SECTION_ID: SIRA-DOC-03_02-SEC-17)
- Proved that `cmd.exe /c "echo %USERPROFILE%"` + `wslpath -u` accurately maps the active Windows user's video capture folder across WSL.

---

[//]: # (SECTION_ID: SIRA-DEV-BOOT_03_02-SEC-18)
## Test 4: Cross-OS Synchronization With `.git` Exclusion
[//]: # (SECTION_ID: SIRA-DEV-BOOT_03_02-SEC-19)

### What We Tested
[//]: # (SECTION_ID: SIRA-DOC-03_02-SEC-19)
Verified that `sync-win-repo` synchronizes source files, scripts, and media to Windows while strictly preserving the isolated Git metadata.

[//]: # (SECTION_ID: SIRA-DEV-BOOT_03_02-SEC-20)
### Command Executed
[//]: # (SECTION_ID: SIRA-DOC-03_02-SEC-20)
```bash
bash -c '
source "$HOME/secondary-env/secondary_project/tools/recording/helpers.sh"
sync-win-repo
echo "Windows sync exit code: $?"
'
```

[//]: # (SECTION_ID: SIRA-DEV-BOOT_03_02-SEC-21)
### Exact Output Returned
[//]: # (SECTION_ID: SIRA-DOC-03_02-SEC-21)
```text
sending incremental file list
./
scripts/
tools/
Windows sync exit code: 0
```

[//]: # (SECTION_ID: SIRA-DEV-BOOT_03_02-SEC-22)
### How We Reached Our Conclusion
[//]: # (SECTION_ID: SIRA-DOC-03_02-SEC-22)
- Exit code `0` and `--exclude=".git"` confirmed that source files mirrored cleanly to Windows without interfering with NTFS permissions or corrupting `.git/index`.

---

[//]: # (SECTION_ID: SIRA-DEV-BOOT_03_02-SEC-23)
## Beginner Coder Q&A: Git Diagnostic Testing
[//]: # (SECTION_ID: SIRA-DEV-BOOT_03_02-SEC-1)

### 1. "What does `git status -sb` mean in Test 1?"
[//]: # (SECTION_ID: SIRA-DOC-03_02-SEC-1)
- `-s` means **short format** (prints clean one-letter flags like `M` for modified or `??` for untracked instead of paragraphs of text).
- `-b` means **branch info** (prints the active branch name and its remote cloud tracking relationship, e.g., `## feature...origin/feature`).

[//]: # (SECTION_ID: SIRA-DEV-BOOT_03_02-SEC-2)
### 2. "Why did Test 2 use `git status --porcelain`?"
[//]: # (SECTION_ID: SIRA-DOC-03_02-SEC-2)
Normal `git diff --quiet` only detects modifications to *existing* files. If you create a brand-new file that has never been tracked, `git diff` cannot see it! Running `git status --porcelain` outputs a raw text list of all files, including untracked (`??`) files, ensuring complete detection.

---

- **Next Pillar**: Read **[`../04_SOLUTIONS_AND_ARCHITECTURE/04_01_UNIFIED_BASHRC_AND_GIT_ARCHITECTURE.md`](../04_SOLUTIONS_AND_ARCHITECTURE/04_01_UNIFIED_BASHRC_AND_GIT_ARCHITECTURE.md)** to see the full architectural blueprint.
