import os
from pathlib import Path
from quentin.self_programming.skill_evaluator import PatchEvaluator, PatchStatus
from meta_agent.patches.models import PatchProposal

def test_eval_plugins():
    print("Testing Eval Plugins...")
    os.environ["QUENTIN_EVAL_PLUGINS_ENABLED"] = "1"
    # Disable actual testing to avoid subprocess calls
    os.environ["QUENTIN_SELF_PROG_EVAL_RUN_TESTS"] = "0"
    
    evaluator = PatchEvaluator()
    
    patch = PatchProposal(
        id="test-patch",
        target_files=["test.py"],
        diff="",
        intent="Test",
        status="proposed"
    )
    
    print("Running evaluation...")
    report = evaluator.evaluate(patch)
    
    print(f"Report status: {report.status}")
    print(f"Report summary: {report.summary}")
    
    # Should have run skill_tests plugin
    assert report.status == PatchStatus.NEEDS_REVIEW
    assert "human review" in report.summary
    
    print("\nEval Plugins check PASSED.")

if __name__ == "__main__":
    try:
        test_eval_plugins()
    except Exception as e:
        print(f"FAILED: {e}")
        import traceback
        traceback.print_exc()
        exit(1)
