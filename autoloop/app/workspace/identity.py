from __future__ import annotations

from pathlib import Path

from git import Repo
from pydantic import BaseModel, Field


class WorkspaceIdentity(BaseModel):
    repo_root: str = Field(min_length=1)
    worktree_path: str = Field(min_length=1)
    base_sha: str = ""
    head_sha: str = ""


def resolve_workspace_identity(path: Path) -> WorkspaceIdentity:
    resolved = path.resolve()
    try:
        repo = Repo(resolved, search_parent_directories=True)
        repo_root = Path(repo.working_tree_dir or resolved).resolve()
        try:
            head_sha = repo.head.commit.hexsha
        except Exception:
            head_sha = ""
        base_sha = head_sha
        return WorkspaceIdentity(
            repo_root=str(repo_root),
            worktree_path=str(resolved),
            base_sha=base_sha,
            head_sha=head_sha,
        )
    except Exception:
        return WorkspaceIdentity(
            repo_root=str(resolved),
            worktree_path=str(resolved),
            base_sha="",
            head_sha="",
        )
