# Git Safe Delivery Checklist

## Before Commit
- Confirm target repo/worktree path is correct.
- Confirm current branch is not `main` (or target base branch).
- Confirm `origin` remote exists.
- Review `git status` and staged diff.

## Quality Gates
- Unit tests pass.
- Regression tests pass.
- No unresolved conflicts.

## Delivery Steps
- Commit with clear, imperative message.
- Push branch to `origin` (skip in `--local-only`, then user pushes manually).
- Create PR to base branch (skip in `--local-only`, then user creates PR manually).
- Enable auto-merge (preferred) or merge explicitly when policy allows.

## After Merge
- Verify base branch includes expected commit.
- Confirm CI status and PR merged state.
- Ensure no accidental artifacts were committed.
