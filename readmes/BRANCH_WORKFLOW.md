# Branch Workflow for StructBioReasoner Development

## Branch Structure

```
main (production)
  ↑
  └── akv (your main development branch)
        ↑
        └── akv_dev (your active development branch) ← YOU ARE HERE
```

## Current Branch Status

- **Current Branch:** `akv_dev`
- **Tracking:** `origin/akv_dev`
- **Parent Branch:** `akv`
- **Latest Commit:** `9c40d4d` - "Add binder design implementation: Phase 1 data structures and documentation"

## Branch Purpose

### `akv_dev` (Active Development)
- **Purpose:** Your personal development sandbox for binder design implementation
- **Freedom:** Make any changes without affecting co-developers
- **Workflow:** Commit frequently, experiment freely
- **Merge Target:** Will merge into `akv` when features are stable

### `akv` (Your Main Branch)
- **Purpose:** Your stable development branch
- **Workflow:** Merge from `akv_dev` when features are tested and working
- **Merge Target:** Will merge into `main` when ready for production

### `main` (Production)
- **Purpose:** Stable production code
- **Workflow:** Only merge well-tested, reviewed code

## Workflow Commands

### Daily Development (on `akv_dev`)

```bash
# Make sure you're on akv_dev
git checkout akv_dev

# Pull latest changes from remote
git pull origin akv_dev

# Make your changes, then stage and commit
git add <files>
git commit -m "Descriptive commit message"

# Push to remote
git push origin akv_dev
```

### Merging `akv_dev` → `akv` (When Features Are Stable)

```bash
# Switch to akv branch
git checkout akv

# Pull latest changes
git pull origin akv

# Merge akv_dev into akv
git merge akv_dev

# Resolve any conflicts if they occur
# Then push to remote
git push origin akv
```

### Merging `akv` → `main` (When Ready for Production)

```bash
# Switch to main branch
git checkout main

# Pull latest changes
git pull origin main

# Merge akv into main
git merge akv

# Resolve any conflicts if they occur
# Then push to remote
git push origin main
```

### Syncing `akv_dev` with `akv` (Get Latest from Parent)

If you want to pull changes from `akv` into `akv_dev`:

```bash
# Make sure you're on akv_dev
git checkout akv_dev

# Fetch latest from akv
git fetch origin akv

# Merge akv into akv_dev
git merge origin/akv

# Resolve any conflicts if they occur
# Then push to remote
git push origin akv_dev
```

### Checking Branch Status

```bash
# See all branches and their tracking status
git branch -vv

# See all branches including remote
git branch -a

# See commit history
git log --oneline --graph --all -10

# See what branch you're on
git status
```

## Current Commit History

```
9c40d4d (HEAD -> akv_dev, origin/akv_dev) Add binder design implementation: Phase 1 data structures and documentation
136733d (origin/akv, akv) attempting to add llm integation into bindcraft agent
1a7fcd4 added parsl stuff
cb03373 folding at work
2e93c3a lots of bug fixes
50489cc bug fixes
```

## Files in Latest Commit (akv_dev)

1. **BINDER_DESIGN_IMPLEMENTATION_CHECKLIST.md** (new)
   - Obsidian-compliant checklist with 9 phases
   - Tracks implementation progress

2. **BINDER_JNANA_CHANGES_SUMMARY.md** (new)
   - Documents changes to Jnana framework
   - Binder-specific hypothesis generation

3. **struct_bio_reasoner/data/protein_hypothesis.py** (modified)
   - Extended `BinderAnalysis` dataclass
   - Added helper methods for data access
   - Added parent-child tracking methods

## Best Practices

### ✅ DO:
- Commit frequently on `akv_dev` with descriptive messages
- Test your changes before merging to `akv`
- Pull from remote before starting work each day
- Use meaningful commit messages
- Keep `akv_dev` focused on binder design implementation

### ❌ DON'T:
- Push directly to `main` without review
- Merge untested code to `akv`
- Force push (`git push -f`) unless absolutely necessary
- Delete branches without backing up

## Merge Strategy

### Phase 1: Development (Current)
- Work on `akv_dev`
- Commit frequently
- Push to `origin/akv_dev`

### Phase 2: Stabilization
- Test features thoroughly on `akv_dev`
- Fix bugs and issues
- When stable, merge `akv_dev` → `akv`

### Phase 3: Integration
- Test on `akv` with other features
- Coordinate with co-developers
- When ready, merge `akv` → `main`

## Conflict Resolution

If you encounter merge conflicts:

```bash
# After running git merge and seeing conflicts
# Edit the conflicted files to resolve conflicts
# Look for markers like:
# <<<<<<< HEAD
# your changes
# =======
# their changes
# >>>>>>> branch-name

# After resolving, stage the files
git add <resolved-files>

# Complete the merge
git commit

# Push the merge
git push
```

## Quick Reference

| Task | Command |
|------|---------|
| Check current branch | `git status` |
| Switch to akv_dev | `git checkout akv_dev` |
| Create new branch | `git checkout -b <branch-name>` |
| Stage changes | `git add <files>` |
| Commit changes | `git commit -m "message"` |
| Push to remote | `git push origin <branch-name>` |
| Pull from remote | `git pull origin <branch-name>` |
| Merge branch | `git merge <branch-name>` |
| View commit history | `git log --oneline -10` |
| View all branches | `git branch -a` |
| Delete local branch | `git branch -d <branch-name>` |
| Delete remote branch | `git push origin --delete <branch-name>` |

## Next Steps

1. ✅ **Created `akv_dev` branch** - COMPLETE
2. ✅ **Committed Phase 1 changes** - COMPLETE
3. ✅ **Pushed to remote** - COMPLETE
4. 🔄 **Continue development on `akv_dev`** - IN PROGRESS
5. ⏳ **Test and stabilize features** - TODO
6. ⏳ **Merge to `akv` when ready** - TODO
7. ⏳ **Merge to `main` when production-ready** - TODO

## Notes

- You are now working on `akv_dev` branch
- All future commits will go to `akv_dev` by default
- Your co-developers won't be affected by your changes until you merge
- You can freely experiment and make changes
- When features are stable, merge to `akv`
- When everything is tested and working, merge to `main`

## GitHub Pull Request (Optional)

If you want to create a pull request for review before merging:

```bash
# Push your branch (already done)
git push origin akv_dev

# Then visit:
# https://github.com/IDeA-ANL-ORNL/StructBioReasoner/pull/new/akv_dev

# Create PR from akv_dev → akv
# Request review from co-developers
# Merge after approval
```

---

**Happy Coding! 🚀**

You're all set to develop independently on `akv_dev` without interfering with your co-developers!

