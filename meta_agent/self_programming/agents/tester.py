from __future__ import annotations
from typing import List
import subprocess
from pathlib import Path

from meta_agent.self_programming.schema import ProgrammingTask, DevPlan, TestPlan, TestReport


import os # Added for os.environ

class TesterAgent:
    """
    v0：只支持 pytest，在 repo_root 下跑。
    future：支持 test_plan 里的 test 子集。
    """

    def __init__(self, repo_root: str):
        self.repo_root = str(Path(repo_root).resolve())

    def build_test_plan(self, task: ProgrammingTask, plan: DevPlan) -> TestPlan:
        # v0: if DevPlan provides test targets, use them; otherwise run full pytest.
        targets = []
        if plan.test_plan:
            targets = plan.test_plan.get("targets", []) or []
        return TestPlan(
            task_id=task.task_id,
            framework="pytest",
            tests=[{"id": t} for t in targets],
        )

    def run_tests(self, test_plan: TestPlan) -> TestReport:
        # Prepare environment to include repo_root in PYTHONPATH
        env_vars = os.environ.copy()
        env_vars["PYTHONPATH"] = self.repo_root + os.pathsep + env_vars.get("PYTHONPATH", "")

        # Build pytest args from test_plan; default: run all tests in repo.
        pytest_targets = [t.get("id") for t in test_plan.tests if t.get("id")]
        pytest_cmd = ["pytest", "-q"] + pytest_targets
        try:
            proc = subprocess.run(
                pytest_cmd,
                cwd=self.repo_root,
                text=True,
                capture_output=True,
                env=env_vars,
            )
            status = "passed" if proc.returncode == 0 else "failed"
            results: List[dict] = [
                {"id": "pytest", "returncode": proc.returncode, "targets": pytest_targets or ["<all>"]}
            ]
            return TestReport(
                task_id=test_plan.task_id,
                overall_status=status,
                results=results,
                raw_output=proc.stdout + "\n" + proc.stderr,
            )
        except Exception as e:
            return TestReport(
                task_id=test_plan.task_id,
                overall_status="failed",
                results=[{"id": "pytest", "error": str(e)}],
                raw_output=str(e),
            )
