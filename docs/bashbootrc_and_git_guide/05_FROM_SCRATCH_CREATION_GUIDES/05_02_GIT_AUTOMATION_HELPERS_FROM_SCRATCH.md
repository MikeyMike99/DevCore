[//]: # (DOC_ID: SIRA-ARCH-BOOT_05_02 | VERSION: v1.0 | SCOPE: ARCH)

# Pillar 05.2: From-Scratch Creation Guide: Git Automation Helpers

- **Back to Master Index**: [`../00_README_INDEX.md`](../00_README_INDEX.md)
- **Previous From-Scratch Guide**: [`05_01_BASHRC_AUTO_SWITCHER_FROM_SCRATCH.md`](./05_01_BASHRC_AUTO_SWITCHER_FROM_SCRATCH.md)
- **Next From-Scratch Guide**: [`05_03_SERVER_RUNNER_AND_MIGRATION_SCRIPTS_FROM_SCRATCH.md`](./05_03_SERVER_RUNNER_AND_MIGRATION_SCRIPTS_FROM_SCRATCH.md)

---

[//]: # (SECTION_ID: SIRA-ARCH-BOOT_05_02-SEC-1)
## Overview
[//]: # (SECTION_ID: SIRA-DOC-05_02-SEC-1)

This guide walks you through building `helpers.sh`, a centralized Git automation toolsuite, from a completely blank text file.

By following this guide, you will implement three production-grade commands:
1. **`start-day`**: Automatically refreshes `main` and creates a dated feature branch.
2. **`save-work`**: An interactive menu with an automated stash safety net to commit and merge safely.
3. **`sync-win-repo`**: Safely mirrors Linux repositories to the Windows filesystem without corrupting Git history.

---

[//]: # (SECTION_ID: SIRA-ARCH-BOOT_05_02-SEC-2)
## Directory Setup
[//]: # (SECTION_ID: SIRA-DOC-05_02-SEC-2)

Create the tools directory in your user home folder:

```bash
mkdir -p "$HOME/tools/recording"
nano "$HOME/tools/recording/helpers.sh"
```

---

[//]: # (SECTION_ID: SIRA-ARCH-BOOT_05_02-SEC-3)
## Step-by-Step Implementation
[//]: # (SECTION_ID: SIRA-ARCH-BOOT_05_02-SEC-4)

### Step 1: Add the File Header and Base Options
[//]: # (SECTION_ID: SIRA-DOC-05_02-SEC-4)
At the top of `helpers.sh`, define the script header:

```bash
#!/usr/bin/env bash
# ==============================================================================
# Git Automation Helpers (helpers.sh)
# Beginner-Friendly Team Workflow Suite
# ==============================================================================
```

[//]: # (SECTION_ID: SIRA-ARCH-BOOT_05_02-SEC-5)
### Step 2: Implement the `start-day` Command
[//]: # (SECTION_ID: SIRA-DOC-05_02-SEC-5)
Add the morning branch bootstrapper:

```bash
start-day() {
    echo "=== Starting New Workday Branch ==="
    
    # Ensure working tree is clean
    if [ -n "$(git status --porcelain)" ]; then
        echo "[ERROR] Uncommitted changes detected! Stash or commit before starting a new day."
        return 1
    fi
    
    # Sync main branch with remote
    git checkout main && git pull origin main || {
        echo "[ERROR] Failed to update main branch."
        return 1
    }
    
    # Prompt for branch name or default to today's date
    local default_name
    default_name="feat/day-$(date +%Y-%m-%d)"
    read -rp "Enter branch name [$default_name]: " branch_name
    branch_name="${branch_name:-$default_name}"
    
    git checkout -b "$branch_name"
    git push -u origin "$branch_name"
    echo "[SUCCESS] Checked out and pushed: $branch_name"
}
```

[//]: # (SECTION_ID: SIRA-ARCH-BOOT_05_02-SEC-6)
### Step 3: Implement the `save-work` Command with Stash Safety
[//]: # (SECTION_ID: SIRA-DOC-05_02-SEC-6)
Add the interactive commit engine with branch-hopping protection:

```bash
save-work() {
    local branch
    branch=$(git rev-parse --abbrev-ref HEAD)
    
    echo "Current Branch: $branch"
    echo "1) Quick Save & Push Current Branch"
    echo "2) Finish Day: Merge Branch to Main & Clean Up"
    echo "3) Cancel"
    read -rp "Select option [1-3]: " choice
    
    case "$choice" in
        1)
            read -rp "Commit message: " msg
            git add .
            git commit -m "$msg"
            git push origin "$branch"
            echo "[SUCCESS] Pushed to origin/$branch"
            ;;
        2)
            # Automatic Stash Safety Net
            local stashed=0
            if [ -n "$(git status --porcelain)" ]; then
                echo "[INFO] Stashing uncommitted changes before branch jump..."
                git stash push -u -m "save-work-autostash"
                stashed=1
            fi
            
            # Switch to main, pull, and merge
            git checkout main && git pull origin main
            git merge "$branch" --no-edit
            git push origin main
            
            # Delete remote and local feature branch safely
            git push origin --delete "$branch" 2>/dev/null || true
            git branch -d "$branch"
            
            # Restore stashed changes if any were taken
            if [ "$stashed" -eq 1 ]; then
                echo "[INFO] Restoring stashed changes on main..."
                git stash pop
            fi
            echo "[SUCCESS] Merged to main and cleaned up $branch"
            ;;
        *)
            echo "Cancelled."
            ;;
    esac
}
```

[//]: # (SECTION_ID: SIRA-ARCH-BOOT_05_02-SEC-7)
### Step 4: Implement Cross-OS Mirror Sync (`sync-win-repo`)
[//]: # (SECTION_ID: SIRA-DOC-05_02-SEC-7)
Add the Windows mirroring function:

```bash
sync-win-repo() {
    # 1. Dynamically discover Windows User Profile
    local win_user
    win_user=$(cmd.exe /c "echo %USERNAME%" 2>/dev/null | tr -d '\r')
    local win_dest="/mnt/c/Users/${win_user}/Documents/Projects/$(basename "$PWD")"
    
    mkdir -p "$win_dest"
    
    echo "=== Mirroring Linux Repo to Windows ==="
    echo "Source: $PWD"
    echo "Dest:   $win_dest"
    
    # 2. Rsync mirror excluding .git
    rsync -rtv --delete --exclude=".git" "$PWD/" "$win_dest/"
    echo "[SUCCESS] Cross-OS sync complete!"
}
```

[//]: # (SECTION_ID: SIRA-ARCH-BOOT_05_02-SEC-8)
### Step 5: Make Executable & Register in `~/.bashrc`
[//]: # (SECTION_ID: SIRA-DOC-05_02-SEC-8)
Run the following commands in your terminal:

```bash
chmod +x "$HOME/tools/recording/helpers.sh"
echo 'source "$HOME/tools/recording/helpers.sh"' >> ~/.bashrc
source ~/.bashrc
```

---

[//]: # (SECTION_ID: SIRA-ARCH-BOOT_05_02-SEC-9)
## Why Order Matters in Git Automation
[//]: # (SECTION_ID: SIRA-DOC-05_02-SEC-9)

1. **Pull Main Before Branching**:
   - `start-day` updates `main` *before* cutting a new branch. Branching from stale local code causes merge conflicts later.
2. **Stash Before Checkout**:
   - In `save-work`, uncommitted files must be stashed *before* checking out `main`. Otherwise, Git aborts the checkout or overwrites changes.
3. **Push Remote Before Local Deletion**:
   - In `save-work`, `git push origin main` must succeed *before* `git branch -d` deletes the feature branch. If the push fails, your local branch remains intact.
4. **Exclude `.git` During Rsync**:
   - Mirroring must exclude `.git`. Windows line endings and NTFS case-insensitivity corrupt Linux Git index databases.

---

[//]: # (SECTION_ID: SIRA-ARCH-BOOT_05_02-SEC-10)
## Beginner Coder Q&A
[//]: # (SECTION_ID: SIRA-ARCH-BOOT_05_02-SEC-11)

### Q: Why do we use `git stash push -u` instead of just `git stash`?
[//]: # (SECTION_ID: SIRA-DOC-05_02-SEC-11)
**A:** Standard `git stash` only saves files that Git is already tracking. The `-u` (untracked) flag ensures brand-new files you created today are also safely stashed.

[//]: # (SECTION_ID: SIRA-ARCH-BOOT_05_02-SEC-12)
### Q: What is `tr -d '\r'` doing in the Windows path helper?
[//]: # (SECTION_ID: SIRA-DOC-05_02-SEC-12)
**A:** `cmd.exe` outputs text with Windows carriage returns (`\r\n`). `tr -d '\r'` strips the invisible `\r` so the Linux path resolves without syntax errors.

[//]: # (SECTION_ID: SIRA-ARCH-BOOT_05_02-SEC-13)
### Q: What happens if `git merge` encounters a conflict in `save-work`?
[//]: # (SECTION_ID: SIRA-DOC-05_02-SEC-13)
**A:** Git stops and asks you to resolve the conflict. Because the branch is not deleted until after a successful push, your work is never lost.
