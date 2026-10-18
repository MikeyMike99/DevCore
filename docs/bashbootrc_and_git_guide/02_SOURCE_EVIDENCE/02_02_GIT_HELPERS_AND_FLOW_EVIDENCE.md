[//]: # (DOC_ID: SIRA-DEV-BOOT_02_02 | VERSION: v1.0 | SCOPE: DEV)

# Pillar 02.2: Source Code Evidence: Automated Git Operations & Synchronization

- **Previous Evidence Chapter**: [`02_01_BASHRC_AND_SYS_EVIDENCE.md`](./02_01_BASHRC_AND_SYS_EVIDENCE.md)
- **Back to Master Index**: [`../00_README_INDEX.md`](../00_README_INDEX.md)
- **Next Pillar**: [`../03_DIAGNOSTIC_TESTS/03_01_BASHRC_AND_VENV_DIAGNOSTIC_LOGS.md`](../03_DIAGNOSTIC_TESTS/03_01_BASHRC_AND_VENV_DIAGNOSTIC_LOGS.md)

---

[//]: # (SECTION_ID: SIRA-DEV-BOOT_02_02-SEC-1)
## Overview
[//]: # (SECTION_ID: SIRA-DOC-02_02-SEC-1)

Automated Git flow helpers protect developers from data loss, detached HEAD states, and cross-filesystem corruption. Below are the actual source code excerpts, line numbers, and technical proofs from `helpers.sh`.

---

[//]: # (SECTION_ID: SIRA-DEV-BOOT_02_02-SEC-2)
## Source 1: Dynamic Branch Creation & Upstream Tracking in `start-day`
[//]: # (SECTION_ID: SIRA-DOC-02_02-SEC-2)

**Source File**: `<secondary_repo>/tools/recording/helpers.sh` (Lines 103–135)

```bash
start-day() {
    dev_user="$(git -C "$REPO_DIR" config user.name 2>/dev/null || echo "$USER")"
    dev_clean="$(echo "$dev_user" | tr '[:upper:]' '[:lower:]' | tr -cd 'a-z0-9_-')"
    local branch_name="feature/${dev_clean}-${date_str}"
    
    cur_b="$(git rev-parse --abbrev-ref HEAD 2>/dev/null)"
    if [ "$cur_b" = "main" ]; then
        git pull origin main >/dev/null 2>&1
    fi

    if git checkout -b "$branch_name"; then
        echo "Created and checked out: $branch_name"
        git push -u origin "$branch_name" 2>/dev/null || true
    fi
}
```

[//]: # (SECTION_ID: SIRA-DEV-BOOT_02_02-SEC-3)
### What This Source Proves
[//]: # (SECTION_ID: SIRA-DOC-02_02-SEC-3)
1. **Dynamic Developer Identity**: `git config user.name` is extracted dynamically and sanitized (`tr -cd 'a-z0-9_-'`) to prevent malformed branch names.
2. **Main Synchronization**: If on `main`, it pulls the latest remote code *before* branching.
3. **Immediate Upstream Link**: `git push -u origin "$branch_name"` links the new local branch to the remote repository on day one, eliminating "no upstream branch" errors later.

---

[//]: # (SECTION_ID: SIRA-DEV-BOOT_02_02-SEC-4)
## Source 2: Automated Stash Buffering During Branch Switches in `save-work`
[//]: # (SECTION_ID: SIRA-DOC-02_02-SEC-4)

**Source File**: `<secondary_repo>/tools/recording/helpers.sh` (Lines 426–445 and 496–505)

```bash
# Stash uncommitted changes safely before checkout
local has_stash="false"
if ! git diff --quiet || ! git diff --cached --quiet; then
    git stash push -u -m "temp_sync_recording_stash" >/dev/null 2>&1
    has_stash="true"
fi

# Switch branch with fallback
if ! git checkout main 2>/dev/null && ! git checkout -m main 2>/dev/null; then
    echo "Error: Could not switch to main."
    [ "$has_stash" = "true" ] && git stash pop >/dev/null 2>&1 || true
    return 1
fi

# Restore uncommitted changes after checkout
[ "$has_stash" = "true" ] && git stash pop >/dev/null 2>&1 || true
```

[//]: # (SECTION_ID: SIRA-DEV-BOOT_02_02-SEC-5)
### What This Source Proves
[//]: # (SECTION_ID: SIRA-DOC-02_02-SEC-5)
1. **Dirty Worktree Protection**: `git diff --quiet || git diff --cached --quiet` detects both unstaged and staged modifications.
2. **Untracked Inclusion**: `git stash push -u` bundles untracked new files into the stash pocket.
3. **Reversible Safety Net**: If `git checkout main` fails, the script immediately runs `git stash pop` before returning, ensuring zero edits are ever lost.

---

[//]: # (SECTION_ID: SIRA-DEV-BOOT_02_02-SEC-6)
## Source 3: Protected Feature Merge & Verified Remote Deletion
[//]: # (SECTION_ID: SIRA-DOC-02_02-SEC-6)

**Source File**: `<secondary_repo>/tools/recording/helpers.sh` (Lines 448–475)

```bash
if git merge "$current_branch" -m "$msg"; then
    echo "Merged $current_branch into main."
    if git push origin main; then
        echo "Pushed updated main to remote."
        # Only delete feature branch AFTER successful push
        git branch -d "$current_branch" 2>/dev/null || git branch -D "$current_branch" 2>/dev/null
        git push origin --delete "$current_branch" 2>/dev/null || true
        echo "Cleaned up feature branch: $current_branch"
    else
        echo "Push to remote failed. Keeping local branch for safety."
    fi
else
    echo "Merge conflict detected! Aborting merge..."
    git merge --abort 2>/dev/null || true
    git checkout "$current_branch" 2>/dev/null || true
fi
```

[//]: # (SECTION_ID: SIRA-DEV-BOOT_02_02-SEC-7)
### What This Source Proves
[//]: # (SECTION_ID: SIRA-DOC-02_02-SEC-7)
1. **Guarded Branch Retirement**: Deleting local (`git branch -d`) and remote (`git push origin --delete`) feature branches occurs **only after** `git push origin main` returns success.
2. **Automatic Conflict Rollback**: If a conflict occurs, `git merge --abort` restores the repository to a clean state and returns to the feature branch.

---

[//]: # (SECTION_ID: SIRA-DEV-BOOT_02_02-SEC-8)
## Source 4: Cross-OS Synchronization With Git Database Protection
[//]: # (SECTION_ID: SIRA-DOC-02_02-SEC-8)

**Source File**: `<secondary_repo>/tools/recording/helpers.sh` (Lines 638–644)

```bash
sync-win-repo() {
    local src_repo="$REPO_DIR"
    local win_dest="$(_get_win_dest)"
    
    rsync -rtv --delete --exclude=".git" "$src_repo/" "$win_dest/"
}
```

[//]: # (SECTION_ID: SIRA-DEV-BOOT_02_02-SEC-9)
### What This Source Proves
[//]: # (SECTION_ID: SIRA-DOC-02_02-SEC-9)
- The `--exclude=".git"` flag prevents mirroring Linux `ext4` Git internal files into Windows `NTFS`, preserving repository database integrity across operating systems.

---

[//]: # (SECTION_ID: SIRA-DEV-BOOT_02_02-SEC-10)
## Beginner Coder Q&A: Git Source Evidence
[//]: # (SECTION_ID: SIRA-DEV-BOOT_02_02-SEC-1)

### 1. "What does `2>/dev/null || true` mean in `git push -u origin ...`?"
[//]: # (SECTION_ID: SIRA-DOC-02_02-SEC-1)
- `2>/dev/null` silences any network error text.
- `|| true` guarantees that if the push fails (e.g., if you are currently offline on an airplane), the script does **not** crash and allows you to keep working locally!

[//]: # (SECTION_ID: SIRA-DEV-BOOT_02_02-SEC-2)
### 2. "Why does `git merge` include the `-m` flag?"
[//]: # (SECTION_ID: SIRA-DOC-02_02-SEC-2)
Without `-m "message"`, Git pops open a terminal text editor (like Vim or Nano) asking you to type a merge commit message. For beginners who do not know how to exit Vim (`:wq`), this feels like the terminal is frozen. Passing `-m` writes the message automatically and completes the merge instantly.

---

- **Next Pillar**: Read **[`../03_DIAGNOSTIC_TESTS/03_01_BASHRC_AND_VENV_DIAGNOSTIC_LOGS.md`](../03_DIAGNOSTIC_TESTS/03_01_BASHRC_AND_VENV_DIAGNOSTIC_LOGS.md)** to inspect the live terminal test logs.
