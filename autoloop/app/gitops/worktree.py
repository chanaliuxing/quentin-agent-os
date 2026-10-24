import asyncio
from pathlib import Path
from git import Repo
from app.config import settings


class WorktreeManager:
    def __init__(self, main_repo_path: Path):
        self.main_repo = Repo(main_repo_path)
        self.worktrees_dir = settings.worktrees_dir

    async def create_worktree(self, agent_name: str, phase_id: str) -> Path:
        branch_name = f"autoloop/{phase_id}/{agent_name}"
        worktree_path = self.worktrees_dir / phase_id / agent_name

        if worktree_path.exists():
            await self.remove_worktree(agent_name, phase_id)

        worktree_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            self.main_repo.git.worktree("add", str(worktree_path), "-b", branch_name)
        except Exception:
            self.main_repo.git.worktree("add", str(worktree_path), branch_name)

        return worktree_path

    async def remove_worktree(self, agent_name: str, phase_id: str) -> None:
        worktree_path = self.worktrees_dir / phase_id / agent_name

        if not worktree_path.exists():
            return

        try:
            self.main_repo.git.worktree("remove", str(worktree_path), "--force")
        except Exception as e:
            print(f"Warning: failed to remove worktree {worktree_path}: {e}")

        if worktree_path.exists():
            import shutil

            shutil.rmtree(worktree_path, ignore_errors=True)

    async def list_worktrees(self) -> list[str]:
        try:
            output = self.main_repo.git.worktree("list", "--porcelain")
            return output.strip().split("\n\n")
        except Exception:
            return []

    async def cleanup_phase_worktrees(self, phase_id: str) -> None:
        phase_dir = self.worktrees_dir / phase_id
        if not phase_dir.exists():
            return

        for agent_dir in phase_dir.iterdir():
            if agent_dir.is_dir():
                await self.remove_worktree(agent_dir.name, phase_id)
