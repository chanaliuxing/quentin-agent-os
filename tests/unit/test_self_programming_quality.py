from pathlib import Path

from meta_agent.self_programming.evaluator import evaluate_patch_set
from meta_agent.self_programming.schema import CodePatchSet, FileModification, TestReport


def test_evaluate_patch_set_basic(tmp_path: Path) -> None:
    repo_root = tmp_path
    target = repo_root / "example.py"
    target.write_text("def add(a: int, b: int) -> int:\n    return a + b\n")

    patch_set = CodePatchSet(
        task_id="t1",
        files=[
            FileModification(
                file_path="example.py",
                action="modify",
                original_snippet=None,
                new_content=target.read_text(),
            )
        ],
        summary="test",
    )
    test_report = TestReport(
        task_id="t1",
        overall_status="passed",
        results=[{"status": "passed"}],
        raw_output="ok",
    )

    metrics = evaluate_patch_set(patch_set, repo_root=repo_root, test_report=test_report)

    assert metrics["file_count"] == 1
    assert "overall_score" in metrics
    assert 0.0 <= metrics["overall_score"] <= 1.0
