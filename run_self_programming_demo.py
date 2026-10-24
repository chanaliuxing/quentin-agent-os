import os
import sys
from pathlib import Path

# Add the project root to the sys.path to allow imports from meta_agent
project_root = Path(__file__).resolve().parent
sys.path.insert(0, str(project_root))

from meta_agent.self_programming.engine import SelfProgrammingEngine
from meta_agent.self_programming.schema import ProgrammingTask

def run_demo():
    task = ProgrammingTask(
        task_id="demo-rename-foo",
        origin="refactor",
        description="Rename foo() to foo_v2() and keep behavior",
        repo_root=str(project_root),
        related_files=["demo.py", "tests/test_demo.py"], # Include the test file to be modified
        context_summary="just a test of self-programming engine v0",
        constraints={},
        acceptance_criteria=["pytest passes"],
    )

    print(f"Running self-programming engine for task: {task.task_id}")
    engine = SelfProgrammingEngine(repo_root=str(project_root))
    result = engine.run_task(task)

    if result:
        print(f"\nSelf-programming task '{task.task_id}' completed with status: {result.review.status}")
        print(f"Test report overall status: {result.test_report.overall_status}")
        print(f"Review summary: {result.review.summary}")
        if result.test_report.raw_output:
            print("\nRaw Test Report Output:\n")
            print(result.test_report.raw_output)
    else:
        print(f"\nSelf-programming task '{task.task_id}' failed with a fatal error.")

if __name__ == "__main__":
    run_demo()
