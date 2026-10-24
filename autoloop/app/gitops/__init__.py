from .worktree import WorktreeManager
from .overlap import detect_git_overlaps
from .merge import resolve_conflict_markers, auto_resolve_conflicts_in_repo

__all__ = [
    "WorktreeManager",
    "detect_git_overlaps",
    "resolve_conflict_markers",
    "auto_resolve_conflicts_in_repo",
]
