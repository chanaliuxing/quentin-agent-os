from pathlib import Path

from app.workspace import resolve_workspace_identity


def test_resolve_workspace_identity_returns_workspace_paths():
    identity = resolve_workspace_identity(Path.cwd())
    assert identity.repo_root
    assert identity.worktree_path
    assert Path(identity.worktree_path).exists()


def test_resolve_workspace_identity_has_git_head_for_repo_paths():
    identity = resolve_workspace_identity(Path.cwd())
    assert len(identity.head_sha) >= 7
    assert identity.base_sha == identity.head_sha
