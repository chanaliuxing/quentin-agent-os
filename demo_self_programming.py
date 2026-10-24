#!/usr/bin/env python3
"""
Demo script to verify self-programming with LLM actually works.
"""
import os
import sys
from pathlib import Path

# Add repo root to path
repo_root = Path(__file__).parent
sys.path.insert(0, str(repo_root))

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

from meta_agent.self_programming.engine import SelfProgrammingEngine
from meta_agent.self_programming.metrics_store import JsonlMetricsStore
from meta_agent.self_programming.schema import ProgrammingTask


def create_demo_task(tmp_dir: Path) -> ProgrammingTask:
    """Create a simple demo task."""
    # Create a simple Python file to modify
    demo_file = tmp_dir / "calculator.py"
    demo_file.write_text("""# Simple calculator
def add(a, b):
    return a + b

def subtract(a, b):
    return a - b
""")

    return ProgrammingTask(
        task_id="demo_task_001",
        origin="experiment",
        description=(
            "Add a multiply function to calculator.py.\n"
            "The function should take two numbers and return their product.\n"
            "Follow the same style as existing functions."
        ),
        repo_root=str(tmp_dir),
        related_files=["calculator.py"],
        context_summary="Adding multiplication feature",
        constraints={
            "preserve_existing": True,
            "follow_style": True,
        },
        acceptance_criteria=[
            "multiply function exists",
            "multiply(2, 3) returns 6",
            "Code style matches existing functions",
        ],
    )


def main():
    """Run a simple self-programming demo."""
    import tempfile
    import shutil

    print("=" * 60)
    print("Self-Programming Demo with LLM")
    print("=" * 60)

    # Create temporary directory for demo
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        print(f"\nDemo directory: {tmp_path}")

        # Initialize git repo
        import subprocess
        subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
        subprocess.run(
            ["git", "config", "user.email", "demo@test.com"],
            cwd=tmp_path, check=True, capture_output=True
        )
        subprocess.run(
            ["git", "config", "user.name", "Demo User"],
            cwd=tmp_path, check=True, capture_output=True
        )

        # Create initial commit
        task = create_demo_task(tmp_path)
        subprocess.run(["git", "add", "."], cwd=tmp_path, check=True, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "Initial commit"],
            cwd=tmp_path, check=True, capture_output=True
        )

        print("\n📝 Created demo task:")
        print(f"   Task ID: {task.task_id}")
        print(f"   Description: {task.description[:80]}...")
        print(f"   Related files: {task.related_files}")

        # Setup engine
        print("\n🔧 Initializing SelfProgrammingEngine...")
        metrics_store = JsonlMetricsStore(repo_root=str(tmp_path))
        engine = SelfProgrammingEngine(
            repo_root=str(tmp_path),
            metrics_store=metrics_store,
            enable_governance=False,  # Disable for demo
        )

        # Check LLM availability
        llm_model = os.getenv("LLM_MODEL", "qwen3-vl:latest")
        llm_base_url = os.getenv("LLM_BASE_URL", "http://localhost:11434")
        print(f"   LLM Model: {llm_model}")
        print(f"   LLM Base URL: {llm_base_url}")

        # Check if we should use stub mode
        use_stub = os.getenv("LOCAL_LLM_STUB", "false").lower() in {"1", "true", "yes"}
        if use_stub:
            print("   ⚠️  Using STUB mode (no real LLM calls)")
        else:
            print("   ✅ Using real LLM")

        # Run the task
        print("\n🚀 Running self-programming task...")
        print("   This may take a minute...")

        try:
            result = engine.run_task(task)

            if result:
                print("\n✅ Task completed!")
                print(f"   Review status: {result.review.status}")
                print(f"   Test status: {result.test_report.overall_status}")

                # Check git history
                git_log = subprocess.run(
                    ["git", "log", "--oneline", "-5"],
                    cwd=tmp_path,
                    capture_output=True,
                    text=True,
                    check=True,
                )

                print(f"\n📋 Git commits:")
                for line in git_log.stdout.strip().split("\n"):
                    print(f"   {line}")

                # Show modified file
                calculator_content = (tmp_path / "calculator.py").read_text()
                print(f"\n📄 Modified calculator.py:")
                print("   " + "\n   ".join(calculator_content.split("\n")))

                # Check metrics
                runs = metrics_store.get_runs_by_status("approved", limit=1)
                if runs:
                    print(f"\n📊 Metrics logged:")
                    print(f"   Task ID: {runs[0]['task_id']}")
                    print(f"   Status: {runs[0]['status']}")

                return 0
            else:
                print("\n❌ Task failed or returned None")
                return 1

        except Exception as e:
            print(f"\n❌ Error during execution: {e}")
            import traceback
            traceback.print_exc()
            return 1


if __name__ == "__main__":
    # Enable stub mode for quick testing without LLM
    if "--stub" in sys.argv:
        os.environ["LOCAL_LLM_STUB"] = "true"
        print("🔧 Stub mode enabled (no LLM calls)\n")

    sys.exit(main())
