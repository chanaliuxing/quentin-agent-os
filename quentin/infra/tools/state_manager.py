from __future__ import annotations
import subprocess
import logging
import os
import shutil
from pathlib import Path
from typing import Optional, List

logger = logging.getLogger(__name__)

class PhysicalStateManager:
    """
    P5: Ported from OpenClaw's transactional state logic.
    Handles physical snapshots (git stash) and rollbacks.
    """
    def __init__(self, repo_root: str | Path):
        self.repo_root = Path(repo_root).resolve()
        self._stashes: List[str] = []

    def _is_git_repo(self) -> bool:
        return (self.repo_root / ".git").exists()

    def capture_snapshot(self, label: str = "auto") -> Optional[str]:
        """
        Creates a physical recovery point.
        """
        if self._is_git_repo():
            try:
                # We stash everything including untracked files
                msg = f"Taylor Auto-Snapshot: {label}"
                subprocess.run(
                    ["git", "stash", "push", "--include-untracked", "-m", msg],
                    cwd=self.repo_root,
                    check=True,
                    capture_output=True
                )
                # After pushing, we need to re-apply so the agent can keep working
                # but the snapshot is now in the stash list.
                subprocess.run(["git", "stash", "apply"], cwd=self.repo_root, check=True)
                
                # Get the stash ID (usually stash@{0})
                self._stashes.append("stash@{0}")
                logger.info(f"PhysicalState: Captured git stash snapshot: {label}")
                return "stash@{0}"
            except Exception as e:
                logger.error(f"PhysicalState: Failed to capture git snapshot: {e}")
        
        # Fallback: File-based snapshot (for specific critical files only, to avoid bloat)
        return None

    def rollback(self):
        """
        Physically reverts the environment to the last snapshot.
        """
        if self._is_git_repo():
            try:
                logger.warning("PhysicalState: PERFORMING PHYSICAL ROLLBACK...")
                # 1. Clean current dirty state
                subprocess.run(["git", "reset", "--hard", "HEAD"], cwd=self.repo_root, check=True)
                subprocess.run(["git", "clean", "-fd"], cwd=self.repo_root, check=True)
                # 2. Pop the last stash (not apply, but pop to revert to exactly that state)
                # Note: This is simplified. In a real system, we'd manage specific stash IDs.
                subprocess.run(["git", "stash", "pop"], cwd=self.repo_root, check=True)
                logger.info("PhysicalState: Rollback successful.")
            except Exception as e:
                logger.error(f"PhysicalState: Rollback failed! {e}")

    def commit_success(self):
        """
        Called when a task succeeds. Clears the recovery point.
        """
        if self._is_git_repo() and self._stashes:
            try:
                subprocess.run(["git", "stash", "drop"], cwd=self.repo_root, check=True)
                self._stashes.pop()
                logger.info("PhysicalState: Task successful. Snapshot cleared.")
            except Exception:
                pass
