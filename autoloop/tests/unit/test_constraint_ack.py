from pathlib import Path

from app.temporal.activities import _requires_constraint_ack


def test_requires_constraint_ack_detects_repair_block(tmp_path: Path):
    task_file = tmp_path / "task.md"
    task_file.write_text(
        "# Task\n\n## Enforced Repair Constraints (Machine-Readable)\n```json\n{}\n```",
        encoding="utf-8",
    )
    assert _requires_constraint_ack(task_file) is True


def test_requires_constraint_ack_false_when_absent(tmp_path: Path):
    task_file = tmp_path / "task.md"
    task_file.write_text("# Task", encoding="utf-8")
    assert _requires_constraint_ack(task_file) is False
