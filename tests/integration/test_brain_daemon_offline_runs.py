import os
import subprocess
import sys
from pathlib import Path


def test_brain_daemon_one_iteration_offline(tmp_path: Path):
    env = dict(os.environ)
    env["LLM_STUB"] = "1"
    env["QUENTIN_TRACES_DIR"] = str(tmp_path / "traces")
    env["QUENTIN_AUDIT_PATH"] = str(tmp_path / "audit.jsonl")
    env["QUENTIN_POLICY_DECISIONS_PATH"] = str(tmp_path / "policy.jsonl")

    proc = subprocess.run(
        [sys.executable, "scripts/run_brain_daemon.py", "--input-text", "hello", "--max-iterations", "1"],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    assert (tmp_path / "traces" / "events.jsonl").exists()


def test_brain_daemon_runs_queue_offline(tmp_path: Path):
    env = dict(os.environ)
    env["LLM_STUB"] = "1"
    env["QUENTIN_TRACES_DIR"] = str(tmp_path / "traces")
    env["QUENTIN_AUDIT_PATH"] = str(tmp_path / "audit.jsonl")
    env["QUENTIN_POLICY_DECISIONS_PATH"] = str(tmp_path / "policy.jsonl")
    env["QUENTIN_TASK_QUEUE_PATH"] = str(tmp_path / "queue.jsonl")

    # Enqueue 2 tasks, then run queue for 2 tasks.
    proc1 = subprocess.run(
        [sys.executable, "-m", "quentin.cli.qctl", "task-enqueue", "--input-text", "t1"],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    assert proc1.returncode == 0, proc1.stderr
    proc2 = subprocess.run(
        [sys.executable, "-m", "quentin.cli.qctl", "task-enqueue", "--input-text", "t2"],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    assert proc2.returncode == 0, proc2.stderr

    proc3 = subprocess.run(
        [sys.executable, "-m", "quentin.cli.qctl", "task-run-queue", "--max-tasks", "2", "--worker-id", "test-worker"],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    assert proc3.returncode == 0, proc3.stderr
    assert (tmp_path / "queue.jsonl").exists()
