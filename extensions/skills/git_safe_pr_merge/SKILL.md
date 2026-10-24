---
id: git_safe_pr_merge
name: git-safe-pr-merge
description: Safe end-to-end Git delivery workflow with explicit gates for worktree, commit, push, PR, and merge to main.
triggers:
  - git 管理
  - 安全合并
  - worktree
  - commit push pr merge
requires:
  - git
  - gh
  - bash
  - pytest
---

# Git Safe PR Merge (Quentin)

## Goal
Run a guarded Git workflow from feature branch/worktree into `main` with hard safety gates.

## Mandatory Rules
- Never commit on `main` (or target base branch).
- In `--execute` mode, unit/regression gates must pass before write actions.
- Never merge without PR.
- Prefer auto-merge when CI checks exist.
- Refuse push/PR/merge when no new commit is created in this run, unless `--allow-existing-commits` is explicitly set.
- If user requests self-managed remote operations, run with `--local-only` and stop after local commit.

## Script
Use:

```bash
bash scripts/git_safe_flow.sh \
  --repo /abs/path/to/repo \
  --base main \
  --create-worktree safety-agent \
  --unit-cmd "pytest tests/unit -q" \
  --regression-cmd "pytest -q" \
  --commit-msg "planning: tighten goal checks" \
  --pr-title "planning: tighten goal checks" \
  --pr-body "## Summary\n- tighten goal checks" \
  --merge-method squash \
  --auto-stage \
  --execute
```

Default is dry-run. Add `--execute` for real write actions.

## Local-Only Mode
If the user will push manually in VS Code, run:

```bash
bash scripts/git_safe_flow.sh \
  --repo /abs/path/to/repo \
  --base main \
  --unit-cmd "pytest tests/unit -q" \
  --regression-cmd "pytest -q" \
  --commit-msg "tools: update safe flow" \
  --execute \
  --local-only
```

## Checklist
See `references/safety-checklist.md`.
