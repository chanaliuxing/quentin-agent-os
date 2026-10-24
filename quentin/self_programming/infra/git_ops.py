import subprocess
import uuid
from pathlib import Path


class GitSafetyLayer:
    """
    使用 Git 分支作为 AI 沙盒：
    - 为每个 task 创建 ai-dev/<task> 分支
    - 成功时提交 commit
    - 失败时回到原分支并删除沙盒分支
    """

    def __init__(self, repo_path: str = "."):
        self.repo_path = str(Path(repo_path).resolve())
        try:
            self._base_branch = self._get_current_branch()
            self.enabled = True
        except RuntimeError as e:
            print(f"[GitSafetyLayer] Disabled: {e}")
            self._base_branch = None
            self.enabled = False

    def _run(self, *args: str) -> None:
        subprocess.check_call(list(args), cwd=self.repo_path)

    def _get_current_branch(self) -> str:
        try:
            out = subprocess.check_output(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                cwd=self.repo_path,
            )
            return out.decode().strip()
        except Exception as e:
            raise RuntimeError(f"Not a git repository or HEAD not available at {self.repo_path}: {e}")

    def create_sandbox(self, task_id: str) -> str:
        branch_name = f"ai-dev/{task_id[:8]}-{uuid.uuid4().hex[:6]}"
        # 从当前分支拉一个分支
        try:
            self._run("git", "checkout", "-b", branch_name)
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"Failed to create sandbox branch {branch_name}: {e}")
        return branch_name

    def commit_work(self, message: str) -> None:
        print(f"[{self.__class__.__name__}] Staging changes...")
        self._run("git", "add", ".")
        print(f"[{self.__class__.__name__}] Committing work with message: {message}")
        try:
            self._run("git", "commit", "-m", message)
        except subprocess.CalledProcessError as e:
            # 可能没有变化，忽略
            print(f"[{self.__class__.__name__}] git commit failed (likely no changes): {e}")
            pass

    def cleanup_sandbox(self, sandbox_branch: str) -> None:
        # 回到最初的 base branch
        try:
            self._run("git", "checkout", self._base_branch)
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"Failed to checkout base branch {self._base_branch}: {e}")
        # 删除临时分支
        try:
            self._run("git", "branch", "-D", sandbox_branch)
        except subprocess.CalledProcessError:
            # Branch may already be gone; ignore
            pass

    def finalize_success(self, sandbox_branch: str, commit_message: str, merge: bool = True, delete_branch: bool = True) -> None:
        """
        Commit changes on sandbox branch, merge back to base (optional), and clean up.
        """
        self.commit_work(commit_message)
        try:
            self._run("git", "checkout", self._base_branch)
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"Failed to checkout base branch {self._base_branch}: {e}")

        if merge:
            try:
                self._run("git", "merge", "--no-ff", sandbox_branch)
            except subprocess.CalledProcessError as e:
                raise RuntimeError(f"Failed to merge sandbox branch {sandbox_branch}: {e}")

        if delete_branch:
            try:
                self._run("git", "branch", "-D", sandbox_branch)
            except subprocess.CalledProcessError:
                pass
