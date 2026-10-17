# Pillar 00B: Beginner Guide to Git Automation & Branching Workflows

- **Previous Primer**: [`00A_BEGINNER_GUIDE_TO_BASHBOOTRC_AND_VENVS.md`](./00A_BEGINNER_GUIDE_TO_BASHBOOTRC_AND_VENVS.md)
- **Back to Master Index**: [`../00_README_INDEX.md`](../00_README_INDEX.md)
- **Next Pillar**: [`../01_PROBLEMS_ENCOUNTERED/01_01_BASHRC_AUTO_SWITCHING_AND_PATH_TRAPS.md`](../01_PROBLEMS_ENCOUNTERED/01_01_BASHRC_AUTO_SWITCHING_AND_PATH_TRAPS.md)

---

## Introduction: Why Do We Need Git Automation?

If you are a beginner developer, version control with Git can feel like walking through a minefield. You run a command you saw on a forum, and suddenly Git throws an error like:
```text
error: Your local changes to the following files would be overwritten by checkout:
Please commit your changes or stash them before you switch branches.
Aborting
```
Or even worse:
```text
fatal: You are in 'detached HEAD' state.
```

To eliminate these fears, we built automated workflow commands (`start-day` and `save-work`) into our shell helper toolkit (`helpers.sh`). This primer explains what Git is doing behind the scenes and why automation keeps your code safe.

---

## Question 1: What Is Git & What Is a Branch?

Think of a Git repository as a digital ledger that records every saved checkpoint (called a **commit**) in your project's history.

- **The `main` Branch**:
  The primary, production-ready timeline of your code. You never want to write experimental, unverified, or broken code directly on `main`.
- **A `feature` Branch**:
  A private, parallel sandbox branched off `main`. When you run `start-day`, the helper creates a branch like `feature/<developer>-<date>`. You can write, test, and break things in your feature branch without affecting `main` or your teammates.

---

## Question 2: Why Do Beginners Lose Work During Branch Switches?

Imagine you edit three files on your feature branch, but you have not yet committed them. You decide to check what is on `main` and type:
```bash
git checkout main
```

### What Git Does
Git sees that switching to `main` would overwrite the files you just edited. Git halts with an error. If a beginner tries to force it with `git checkout -f main`, **Git permanently erases the uncommitted edits**!

### How Our Automated Workflow Protects You (`git stash`)
Our `save-work` automation implements an automated safety net before touching branches:
1. It checks `git diff --quiet`. If any uncommitted edits exist, it automatically runs:
   ```bash
   git stash push -u -m "temp_sync_switch_stash"
   ```
   *(This safely packs your in-progress work into an invisible temporary locker).*
2. It switches branches safely.
3. It immediately runs `git stash pop` to unpack your work back onto the screen. Zero data is ever lost.

---

## Question 3: Plain-English Glossary of Everyday Git Commands

- **`git add .`**: Marks all modified files as ready to be saved into the next checkpoint ("staging").
- **`git commit -m "message"`**: Stamps a permanent checkpoint into the project ledger with a descriptive note.
- **`git push -u origin <branch>`**: Uploads your local commits to the remote cloud server (e.g., GitHub) and sets up a tracking link so future pushes know where to go.
- **`git pull origin <branch>`**: Downloads the newest commits from the cloud and merges them into your active branch.
- **`git stash`**: Temporarily hides your uncommitted work in a clean pocket so you can pull, switch branches, or merge without conflicts.
- **`git merge origin/main`**: Takes updates that your teammates pushed to `main` and folds them cleanly into your feature branch.
- **`git branch -d <branch>`**: Safely deletes a feature branch after all of its work has been successfully merged into `main`.

---

## Question 4: Why Does the Order of Git Operations Matter?

In Git, executing commands in the wrong order can cause merge conflicts or corrupt your local repository state.

### The Mandatory 5-Step Feature Merge Order
Look at the sequence enforced inside `save-work` (Option 4: Merge feature into `main`):

| Step | Command | Why It Must Be in This Position |
| :--- | :--- | :--- |
| **1. Commit Local Work** | `git commit -m "Finalize..."` | **Must be first**: Never switch branches with unstaged, half-written code in your workspace. |
| **2. Stash Buffering** | `git stash push -u` | Preserves any untracked auxiliary files before changing HEAD. |
| **3. Checkout Main** | `git checkout main` | Moves the workspace pointer to the destination branch. |
| **4. Pull Remote Main** | `git pull origin main` | **Critical**: You must update `main` with the newest cloud changes *before* attempting to merge your branch into it. |
| **5. Merge & Push** | `git merge <branch>` then `git push` | Merges your feature branch into updated `main` and pushes both to the cloud. |

If you swapped Step 4 and Step 5 (merging *before* pulling `main`), you would merge into an outdated local branch and your subsequent `git push` would be rejected by the server!

---

## Beginner Coder Q&A: Understanding Git Automation

### 1. "What is `origin` in commands like `git push origin main`?"
`origin` is simply the default nickname Git gives to the remote cloud repository URL (e.g., your GitHub repo). Typing `git push origin main` means: *"Push my commits to the remote cloud server's `main` branch."*

### 2. "Why does `helpers.sh` use `git rev-parse --abbrev-ref HEAD`?"
`HEAD` is a pointer pointing to whichever branch you are currently standing on. Running `git rev-parse --abbrev-ref HEAD` returns the clean name of your current branch (e.g., `feature/dev-20261017`). The script reads this dynamically so it never pushes to the wrong branch.

### 3. "What happens if a merge has conflicts?"
If two developers edit the exact same line in the same file, Git pauses the merge and asks a human to decide which line to keep. Our automation detects this, prints an alert, and tells you: *"Resolve conflicts with `git status`, or run `git merge --abort` to safely cancel without breaking anything."*

---

- **Next Pillar**: Read **[`../01_PROBLEMS_ENCOUNTERED/01_01_BASHRC_AUTO_SWITCHING_AND_PATH_TRAPS.md`](../01_PROBLEMS_ENCOUNTERED/01_01_BASHRC_AUTO_SWITCHING_AND_PATH_TRAPS.md)** to see the 5 shell and environment problems we ran into.
