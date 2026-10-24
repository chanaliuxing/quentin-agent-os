#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage:
  bash scripts/git_safe_flow.sh [options]

Options:
  --repo PATH                    Target repo/worktree path (default: current dir)
  --base BRANCH                  Base branch to merge into (default: main)
  --unit-cmd CMD                 Unit test gate command (default: "pytest tests/unit -q")
  --regression-cmd CMD           Regression test gate command (default: "pytest -q")
  --commit-msg MSG               Commit message
  --pr-title TITLE               PR title (default: commit message)
  --pr-body BODY                 PR body text
  --merge-method METHOD          squash|merge|rebase (default: squash)
  --auto-stage                   Run git add -A before commit
  --allow-existing-commits       Allow push/PR/merge when no new commit is created in this run
  --disable-auto-merge           Create PR only; do not enable auto-merge
  --merge-now                    Merge immediately (still requires PR)
  --local-only                   Stop after local commit; skip push/PR/merge
  --create-worktree NAME         Create a new worktree at <repo>/worktrees/NAME
  --worktree-path PATH           Custom path for new worktree (with --create-worktree)
  --branch BRANCH                Branch for new worktree (default: codex/<NAME>)
  --execute                      Perform writes. Without this flag, dry-run only.
  --help                         Show this help
USAGE
}

log() {
  printf '[git-safe-flow] %s\n' "$*"
}

die() {
  printf '[git-safe-flow][ERROR] %s\n' "$*" >&2
  exit 1
}

require_cmd() {
  local cmd="$1"
  if ! command -v "$cmd" >/dev/null 2>&1; then
    die "missing required command: $cmd"
  fi
}

run_cmd() {
  local cmd="$1"
  if [[ "$EXECUTE" -eq 1 ]]; then
    log "exec: $cmd"
    bash -lc "$cmd"
  else
    log "dry-run: $cmd"
  fi
}

run_gate() {
  local name="$1"
  local cmd="$2"
  if [[ -z "$cmd" ]]; then
    die "$name command is empty"
  fi
  if [[ "$EXECUTE" -eq 1 ]]; then
    log "gate($name): $cmd"
    if ! bash -lc "$cmd"; then
      die "$name gate failed: $cmd"
    fi
  else
    log "dry-run gate($name): $cmd"
  fi
}

git_repo_cmd() {
  git -C "$REPO" "$@"
}

gh_repo_cmd() {
  (cd "$REPO" && gh "$@")
}

REPO="$(pwd)"
BASE="main"
UNIT_CMD="pytest tests/unit -q"
REGRESSION_CMD="pytest -q"
COMMIT_MSG=""
PR_TITLE=""
PR_BODY=""
MERGE_METHOD="squash"
AUTO_STAGE=0
EXECUTE=0
ALLOW_EXISTING_COMMITS=0
ENABLE_AUTO_MERGE=1
MERGE_NOW=0
LOCAL_ONLY=0
CREATE_WORKTREE=""
WORKTREE_PATH=""
WORKTREE_BRANCH=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --repo)
      REPO="$2"
      shift 2
      ;;
    --base)
      BASE="$2"
      shift 2
      ;;
    --unit-cmd)
      UNIT_CMD="$2"
      shift 2
      ;;
    --regression-cmd)
      REGRESSION_CMD="$2"
      shift 2
      ;;
    --commit-msg)
      COMMIT_MSG="$2"
      shift 2
      ;;
    --pr-title)
      PR_TITLE="$2"
      shift 2
      ;;
    --pr-body)
      PR_BODY="$2"
      shift 2
      ;;
    --merge-method)
      MERGE_METHOD="$2"
      shift 2
      ;;
    --auto-stage)
      AUTO_STAGE=1
      shift
      ;;
    --allow-existing-commits)
      ALLOW_EXISTING_COMMITS=1
      shift
      ;;
    --disable-auto-merge)
      ENABLE_AUTO_MERGE=0
      shift
      ;;
    --merge-now)
      MERGE_NOW=1
      shift
      ;;
    --local-only)
      LOCAL_ONLY=1
      shift
      ;;
    --create-worktree)
      CREATE_WORKTREE="$2"
      shift 2
      ;;
    --worktree-path)
      WORKTREE_PATH="$2"
      shift 2
      ;;
    --branch)
      WORKTREE_BRANCH="$2"
      shift 2
      ;;
    --execute)
      EXECUTE=1
      shift
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      die "unknown option: $1"
      ;;
  esac
done

require_cmd git
require_cmd bash

REPO="$(cd "$REPO" && pwd)"
[[ -d "$REPO" ]] || die "repo path does not exist: $REPO"

if [[ "$MERGE_METHOD" != "squash" && "$MERGE_METHOD" != "merge" && "$MERGE_METHOD" != "rebase" ]]; then
  die "invalid --merge-method: $MERGE_METHOD (expected squash|merge|rebase)"
fi

if [[ "$MERGE_NOW" -eq 1 && "$ENABLE_AUTO_MERGE" -eq 1 ]]; then
  die "--merge-now cannot be used with auto-merge enabled; pass --disable-auto-merge"
fi
if [[ "$LOCAL_ONLY" -eq 1 && "$MERGE_NOW" -eq 1 ]]; then
  die "--local-only cannot be combined with --merge-now"
fi

if [[ -n "$CREATE_WORKTREE" ]]; then
  [[ "$CREATE_WORKTREE" =~ ^[A-Za-z0-9._/-]+$ ]] || die "invalid worktree name: $CREATE_WORKTREE"
  if [[ -z "$WORKTREE_BRANCH" ]]; then
    WORKTREE_BRANCH="codex/$CREATE_WORKTREE"
  fi
  if [[ -z "$WORKTREE_PATH" ]]; then
    WORKTREE_PATH="$REPO/worktrees/$CREATE_WORKTREE"
  fi

  if [[ -e "$WORKTREE_PATH" ]]; then
    die "worktree path already exists: $WORKTREE_PATH"
  fi

  run_cmd "git -C '$REPO' fetch origin '$BASE'"
  run_cmd "git -C '$REPO' worktree add -b '$WORKTREE_BRANCH' '$WORKTREE_PATH' '$BASE'"

  if [[ "$EXECUTE" -eq 1 ]]; then
    REPO="$(cd "$WORKTREE_PATH" && pwd)"
  else
    REPO="$WORKTREE_PATH"
  fi
  log "target switched to worktree: $REPO"
fi

if ! git -C "$REPO" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  die "not a git repository: $REPO"
fi

if ! git_repo_cmd remote get-url origin >/dev/null 2>&1; then
  die "missing git remote: origin"
fi

CURRENT_BRANCH="$(git_repo_cmd rev-parse --abbrev-ref HEAD)"
if [[ "$CURRENT_BRANCH" == "HEAD" ]]; then
  die "detached HEAD is not allowed"
fi
if [[ "$CURRENT_BRANCH" == "$BASE" ]]; then
  die "refuse to run on base branch '$BASE'; switch to a feature branch"
fi

if [[ "$ALLOW_EXISTING_COMMITS" -eq 0 && -z "$COMMIT_MSG" ]]; then
  die "--commit-msg is required unless --allow-existing-commits is set"
fi

if [[ -z "$PR_TITLE" ]]; then
  PR_TITLE="$COMMIT_MSG"
fi
if [[ -z "$PR_TITLE" ]]; then
  PR_TITLE="chore: update $CURRENT_BRANCH"
fi
if [[ -z "$PR_BODY" ]]; then
  PR_BODY="## Summary\n- Safe delivery by scripts/git_safe_flow.sh"
fi

if [[ "$LOCAL_ONLY" -eq 0 ]]; then
  require_cmd gh
fi

WORKTREE_COUNT="$(git_repo_cmd worktree list --porcelain | grep -c '^worktree ' || true)"
log "repo=$REPO branch=$CURRENT_BRANCH base=$BASE worktrees=$WORKTREE_COUNT execute=$EXECUTE"

log "status preflight:"
git_repo_cmd status --short

if [[ "$AUTO_STAGE" -eq 1 ]]; then
  run_cmd "git -C '$REPO' add -A"
fi

run_gate "unit" "$UNIT_CMD"
run_gate "regression" "$REGRESSION_CMD"

HEAD_BEFORE="$(git_repo_cmd rev-parse HEAD)"
NEW_COMMIT=0

if git_repo_cmd diff --staged --quiet; then
  log "no staged changes"
  if [[ "$EXECUTE" -eq 1 && "$ALLOW_EXISTING_COMMITS" -eq 0 ]]; then
    die "no staged changes; nothing to commit"
  fi
else
  run_cmd "git -C '$REPO' commit -m \"$COMMIT_MSG\""
  if [[ "$EXECUTE" -eq 1 ]]; then
    HEAD_AFTER="$(git_repo_cmd rev-parse HEAD)"
    if [[ "$HEAD_AFTER" != "$HEAD_BEFORE" ]]; then
      NEW_COMMIT=1
    fi
  fi
fi

if [[ "$EXECUTE" -eq 1 && "$ALLOW_EXISTING_COMMITS" -eq 0 && "$NEW_COMMIT" -eq 0 ]]; then
  die "expected a new commit but none was created"
fi

if [[ "$LOCAL_ONLY" -eq 1 ]]; then
  log "local-only mode: skip push/PR/merge"
  if [[ "$EXECUTE" -eq 1 ]]; then
    log "done(local-only): branch=$CURRENT_BRANCH base=$BASE"
  else
    log "dry-run complete(local-only); pass --execute to perform local commit"
  fi
  exit 0
fi

run_cmd "git -C '$REPO' push -u origin '$CURRENT_BRANCH'"

PR_NUMBER=""
if [[ "$EXECUTE" -eq 1 ]]; then
  PR_NUMBER="$(gh_repo_cmd pr view --json number --jq .number 2>/dev/null || true)"
  if [[ -z "$PR_NUMBER" ]]; then
    gh_repo_cmd pr create \
      --base "$BASE" \
      --head "$CURRENT_BRANCH" \
      --title "$PR_TITLE" \
      --body "$PR_BODY"
    PR_NUMBER="$(gh_repo_cmd pr view --json number --jq .number)"
  fi
  [[ -n "$PR_NUMBER" ]] || die "failed to resolve PR number"
  log "pr=#${PR_NUMBER}"
else
  log "dry-run: gh pr create --base '$BASE' --head '$CURRENT_BRANCH' --title '$PR_TITLE' --body '<body>'"
fi

MERGE_FLAG="--squash"
if [[ "$MERGE_METHOD" == "merge" ]]; then
  MERGE_FLAG="--merge"
elif [[ "$MERGE_METHOD" == "rebase" ]]; then
  MERGE_FLAG="--rebase"
fi

if [[ "$MERGE_NOW" -eq 1 ]]; then
  if [[ "$EXECUTE" -eq 1 ]]; then
    gh_repo_cmd pr merge "$PR_NUMBER" "$MERGE_FLAG" --delete-branch
  else
    log "dry-run: gh pr merge <pr-number> $MERGE_FLAG --delete-branch"
  fi
elif [[ "$ENABLE_AUTO_MERGE" -eq 1 ]]; then
  if [[ "$EXECUTE" -eq 1 ]]; then
    gh_repo_cmd pr merge "$PR_NUMBER" --auto "$MERGE_FLAG" --delete-branch
  else
    log "dry-run: gh pr merge <pr-number> --auto $MERGE_FLAG --delete-branch"
  fi
else
  log "merge disabled by --disable-auto-merge"
fi

if [[ "$EXECUTE" -eq 1 ]]; then
  git_repo_cmd fetch origin "$BASE"
  log "done: branch=$CURRENT_BRANCH base=$BASE pr=#${PR_NUMBER}"
else
  log "dry-run complete; pass --execute to perform writes"
fi
