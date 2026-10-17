[//]: # (DOC_ID: SIRA-DOC-01_02 | VERSION: v1.0 | SCOPE: Siraugga / DevCore Framework)

# Pillar 01.2: Git Workflow Traps & Cross-OS Synchronization Issues

- **Previous Problem Chapter**: [`01_01_BASHRC_AUTO_SWITCHING_AND_PATH_TRAPS.md`](./01_01_BASHRC_AUTO_SWITCHING_AND_PATH_TRAPS.md)
- **Back to Master Index**: [`../00_README_INDEX.md`](../00_README_INDEX.md)
- **Next Pillar**: [`../02_SOURCE_EVIDENCE/02_01_BASHRC_AND_SYS_EVIDENCE.md`](../02_SOURCE_EVIDENCE/02_01_BASHRC_AND_SYS_EVIDENCE.md)

---

## Overview
[//]: # (SECTION_ID: SIRA-DOC-01_02-SEC-1)

When developers collaborate using Git across **WSL (Linux)** and **Windows**, several dangerous traps can cause lost code, merge aborts, or corrupted repositories. 

Below is the plain-English breakdown of five specific Git traps encountered in everyday developer workflows and how our automated toolkit (`helpers.sh`) neutralizes each one.

---

## Problem 1: Uncommitted Worktree Collisions During Branch Checkout
[//]: # (SECTION_ID: SIRA-DOC-01_02-SEC-2)

### What Happened
[//]: # (SECTION_ID: SIRA-DOC-01_02-SEC-3)
A developer edits three files on their active feature branch, decides to switch to `main` to pull updates, and runs `git checkout main`. Git halts immediately with:
```text
error: Your local changes to the following files would be overwritten by checkout:
Please commit your changes or stash them before you switch branches.
Aborting
```

### Why It Happened
[//]: # (SECTION_ID: SIRA-DOC-01_02-SEC-4)
1. **Uncommitted State**: Git refuses to let you switch branches if any uncommitted changes in your working tree would be overwritten by files on the target branch.
2. **The Beginner Trap**: Beginners often try to force the checkout with `git checkout -f main` or discard changes with `git reset --hard`, which permanently erases their uncommitted hours of work.
3. **The Automated Solution**: Inside `save-work`, the script automatically checks `if ! git diff --quiet || ! git diff --cached --quiet; then`. If uncommitted changes exist, it automatically stashes them with `git stash push -u -m "temp_sync_switch_stash"`, performs the switch, and pops them cleanly with `git stash pop`.

---

## Problem 2: The Detached HEAD Trap
[//]: # (SECTION_ID: SIRA-DOC-01_02-SEC-5)

### What Happened
[//]: # (SECTION_ID: SIRA-DOC-01_02-SEC-6)
A developer wants to view a teammate's branch, types `git checkout origin/feature-xyz`, and Git prints:
```text
You are in 'detached HEAD' state. You can look around, make experimental changes...
```
When the developer makes commits in this state, those commits do not belong to any branch. When they switch back to `main`, their new commits become invisible and will eventually be permanently deleted by Git's garbage collection!

### Why It Happened
[//]: # (SECTION_ID: SIRA-DOC-01_02-SEC-7)
- A remote tracking reference (`origin/<branch>`) is a read-only snapshot. Checking it out directly detaches `HEAD` from any local branch.
- **The Solution**: In `helpers.sh` (`_resolve_branch()`), the script uses `git rev-parse --verify --quiet` and `git checkout -b <branch> origin/<branch>` to ensure that checking out a remote branch always constructs an active local tracking branch.

---

## Problem 3: Missing Upstream Tracking Information
[//]: # (SECTION_ID: SIRA-DOC-01_02-SEC-8)

### What Happened
[//]: # (SECTION_ID: SIRA-DOC-01_02-SEC-9)
A developer creates a new branch (`git checkout -b feature/my-task`), makes commits, and types `git push`. Git rejects the command with:
```text
fatal: The current branch feature/my-task has no upstream branch.
To push the current branch and set the remote as upstream, use
    git push --set-upstream origin feature/my-task
```

### Why It Happened
[//]: # (SECTION_ID: SIRA-DOC-01_02-SEC-10)
- By default, Git does not know which remote branch matches a newly created local branch until you set up an upstream tracking reference.
- **The Solution**: When `start-day` creates a branch, it immediately executes `git push -u origin "$branch_name"` on creation, linking local and cloud repositories so subsequent `git push` and `git pull` commands work with zero arguments.

---

## Problem 4: The `.git` Directory Corruption Trap During Windows-WSL Sync
[//]: # (SECTION_ID: SIRA-DOC-01_02-SEC-11)

### What Happened
[//]: # (SECTION_ID: SIRA-DOC-01_02-SEC-12)
When synchronizing project folders between WSL Linux (`/home/<user>/...`) and Windows (`/mnt/c/...`) using `rsync`, attempting to run `git status` inside the Windows directory suddenly threw errors:
```text
fatal: not a git repository (or any of the parent directories): .git
```
Or warned that all file permissions changed from `100644` to `100755`.

### Why It Happened
[//]: # (SECTION_ID: SIRA-DOC-01_02-SEC-13)
1. **Filesystem Metadata Incompatibility**: Linux `ext4` and Windows `NTFS` handle file permissions, ownership, and symlinks differently.
2. **Corrupted Index**: Mirroring the internal `.git/` folder from Linux to Windows over `rsync` can break Git index locks and symlinks.
3. **The Solution**: In `helpers.sh` (`sync-win-repo`), the `rsync` command explicitly includes:
   ```bash
   rsync -rtv --delete --exclude=".git" "$src_repo/" "$win_dest/"
   ```
   Excluding `.git/` allows files, source code, and assets to sync perfectly while keeping the Git version control databases isolated and uncorrupted on their native filesystems.

---

## Problem 5: Accidental Branch Deletion Before Upstream Verification
[//]: # (SECTION_ID: SIRA-DOC-01_02-SEC-14)

### What Happened
[//]: # (SECTION_ID: SIRA-DOC-01_02-SEC-15)
After merging a feature branch locally, a developer deletes the branch (`git branch -D feature/xyz`) before pushing `main` to GitHub. If the push fails due to a network glitch or branch protection rule, the feature branch is gone and cannot be easily restored.

### Why It Happened
[//]: # (SECTION_ID: SIRA-DOC-01_02-SEC-16)
- Premature local cleanup leaves no safety net.
- **The Solution**: In `save-work` (Option 4), branch deletion (`git branch -d` and `git push origin --delete`) is strictly guarded: it executes **only after** `git push origin main` returns exit code `0` (100% success).

---

## Beginner Coder Q&A: Git Workflow Traps
[//]: # (SECTION_ID: SIRA-DOC-01_02-SEC-17)

### 1. "What is the difference between `git branch -d` and `git branch -D`?"
[//]: # (SECTION_ID: SIRA-DOC-01_02-SEC-1)
- `-d` (lowercase) is **safe delete**: Git checks if the branch has been fully merged into `main`. If unmerged commits exist, Git refuses to delete it.
- `-D` (uppercase) is **force delete**: Git deletes the branch regardless of whether work was merged. Our automated script uses `-d` first, and only falls back to `-D` if the merge was verified.

### 2. "Why does `git stash push` need the `-u` flag?"
[//]: # (SECTION_ID: SIRA-DOC-01_02-SEC-2)
By default, `git stash` only saves files that Git is already tracking. If you created a brand-new file (like `new_module.py`), normal stash ignores it! Adding **`-u` (untracked)** tells Git: *"Save everything, including brand-new files, so nothing gets left behind."*

---

- **Next Pillar**: Read **[`../02_SOURCE_EVIDENCE/02_01_BASHRC_AND_SYS_EVIDENCE.md`](../02_SOURCE_EVIDENCE/02_01_BASHRC_AND_SYS_EVIDENCE.md)** to see the exact code citations for the shell configuration.
