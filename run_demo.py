# run_demo.py
import sys
import os
from meta_agent.self_programming.engine import SelfProgrammingEngine
from meta_agent.self_programming.schema import ProgrammingTask

# This is to ensure that the git commands work correctly, as the script is in the root.
# The GitSafetyLayer needs to know the repo root.
REPO_ROOT = os.path.dirname(os.path.abspath(__file__))

import subprocess

def main():
    print(f"Current working directory: {os.getcwd()}")
    sys.path.insert(0, os.getcwd())  # Ensure current directory is in sys.path
    print(f"sys.path: {sys.path}")
    if os.getenv("RUN_DEMO_DEBUG_BREAK"):
        breakpoint()
    print("Resetting workspace to a clean state...")
    subprocess.run(['git', 'reset', '--hard', 'HEAD'], check=True)
    subprocess.run(['git', 'clean', '-fd'], check=True)

    print("Starting self-programming demo...")

    # Ensure we are on a clean branch before starting
    # For this demo, we can just assume we start from a clean 'main' or 'master'
    # The GitSafetyLayer will create a new branch.

    task = ProgrammingTask(
        task_id="demo-add-comment",
        origin="refactor",
        description="Add a comment '# v2' to the foo function in demo.py.",
        repo_root=REPO_ROOT,
        related_files=["demo.py"],
        context_summary="A simple test to add a comment.",
        constraints={},
        acceptance_criteria=["pytest passes for tests/test_demo.py"],
    )

    engine = SelfProgrammingEngine(repo_root=REPO_ROOT)
    
    print(f"Running task: {task.task_id}")
    result = engine.run_task(task)
    
    if result:
        print("\n--- Self-Programming Task Result ---")
        print(f"Task ID: {result.task.task_id}")
        print(f"Final Review Status: {result.review.status}")
        print(f"Review Summary: {result.review.summary}")
        
        if result.review.status == "approve":
            print("\n✅ Task approved and changes committed.")
        else:
            print("\n❌ Task rejected and changes rolled back.")
            print("Issues:", result.review.issues)

        print("\nTest Report:")
        print(f"  Overall Status: {result.test_report.overall_status}")
        print(f"  Raw Output:\n{result.test_report.raw_output}")

    else:
        print("\n💥 An unexpected fatal error occurred in the engine.")

if __name__ == "__main__":
    main()
