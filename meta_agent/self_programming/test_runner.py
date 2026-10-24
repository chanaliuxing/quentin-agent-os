# meta_agent/self_programming/test_runner.py
import tempfile
from pathlib import Path
import shutil
import os
import subprocess
import json

class SandboxTestRunner:
    """
    A test runner that operates within a temporary sandbox environment.
    """

    def run_tests(
        self,
        implementation_code: str,
        verification_test_code: str,
        target_file: Path,
        source_root: Path,
    ) -> dict:
        """Alias for run_in_sandbox to satisfy TestRunnerBackend protocol."""
        return self.run_in_sandbox(
            implementation_code,
            verification_test_code,
            target_file,
            source_root=source_root,
        )

    def run_in_sandbox(
        self,
        implementation_code: str,
        test_code: str,
        target_file: Path,
        *,
        source_root: Path | None = None,
    ):
        source_root = Path(source_root) if source_root is not None else Path.cwd()
        use_docker = bool(os.environ.get("USE_DOCKER_SANDBOX"))
        
        # P5: Git Worktree Optimization (OpenClaw Parity)
        is_git = (source_root / ".git").exists()
        sandbox_dir = tempfile.mkdtemp(prefix="taylor_sandbox_")
        sandbox_path = Path(sandbox_dir)
        worktree_created = False

        try:
            if is_git:
                try:
                    subprocess.run(
                        ["git", "worktree", "add", "--detach", str(sandbox_path)],
                        cwd=source_root,
                        check=True,
                        capture_output=True
                    )
                    print(f"[Sandbox] Created git worktree at {sandbox_path}")
                    worktree_created = True
                except Exception as e:
                    print(f"[Sandbox] Git worktree failed ({e}), falling back to copy.")
                    is_git = False # Fallback

            if not is_git:
                # Legacy copytree
                ignore_patterns = shutil.ignore_patterns(".git", "__pycache__", "venv", "*.pyc")
                shutil.copytree(source_root, sandbox_path, dirs_exist_ok=True, ignore=ignore_patterns)
                print(f"[Sandbox] Copied files to {sandbox_path}")

            # Write implementation code
            sandbox_target_file = sandbox_path / target_file
            sandbox_target_file.parent.mkdir(parents=True, exist_ok=True)
            with open(sandbox_target_file, 'w') as f:
                f.write(implementation_code)

            # Write test code
            sandbox_test_file = sandbox_path / "tests" / "temp_test.py"
            sandbox_test_file.parent.mkdir(parents=True, exist_ok=True)
            with open(sandbox_test_file, 'w') as f:
                f.write(test_code)

            if use_docker:
                res = self._run_in_docker(sandbox_path, sandbox_test_file)
            else:
                res = self._run_locally(sandbox_path, sandbox_test_file)
            
            return res

        except Exception as e:
            return {"success": False, "message": f"Error in sandbox: {e}"}
        finally:
            # Cleanup
            if worktree_created:
                subprocess.run(
                    ["git", "worktree", "remove", "--force", str(sandbox_path)],
                    cwd=source_root,
                    stderr=subprocess.DEVNULL
                )
            else:
                shutil.rmtree(sandbox_path, ignore_errors=True)

    def _run_locally(self, sandbox_path: Path, test_file: Path) -> dict:
        print(f"Running pytest on {test_file} locally...")
        result = subprocess.run(
            ["pytest", str(test_file)],
            cwd=sandbox_path,
            capture_output=True,
            text=True
        )
        return {
            "success": result.returncode == 0,
            "exit_code": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "sandbox_path": str(sandbox_path)
        }

    def _run_in_docker(self, sandbox_path: Path, test_file: Path) -> dict:
        image = os.environ.get("SANDBOX_DOCKER_IMAGE", "python:3.11-slim")
        workdir = "/workspace"
        cmd = [
            "docker", "run", "--rm",
            "--cpus", os.environ.get("SANDBOX_CPUS", "1"),
            "--memory", os.environ.get("SANDBOX_MEMORY", "512m"),
            "--network", "none",
            "-v", f"{sandbox_path}:{workdir}:ro",
            "-w", workdir,
            image,
            "bash", "-lc",
            f"cp -r {workdir} /tmp/w && cd /tmp/w && pip install -q pytest && pytest {test_file.name}"
        ]
        print(f"Running pytest in docker: {' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=True, text=True)
        return {
            "success": result.returncode == 0,
            "exit_code": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "sandbox_path": str(sandbox_path),
            "docker_image": image,
        }
