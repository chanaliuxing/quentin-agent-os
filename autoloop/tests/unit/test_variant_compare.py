from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from app.metrics.variant_compare import (
    filter_variant_rows,
    load_execution_summaries,
    summarize_variant,
)


def _write_summary(runtime_dir: Path, workflow_id: str, primary_failure_type: str, terminal_state: str, acceptance_status: str) -> None:
    phase_dir = runtime_dir / "evidence" / workflow_id / "phase_01"
    target = phase_dir / "execution_summary.json"
    phase_dir.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(
            {
                "workflow_id": workflow_id,
                "phase_id": "phase_01",
                "primary_failure_type": primary_failure_type,
                "terminal_state": terminal_state,
                "acceptance_status": acceptance_status,
            }
        ),
        encoding="utf-8",
    )
    if primary_failure_type == "AGENT_SUBPROCESS_NONZERO_EXIT":
        (phase_dir / "evidence_phase_01_0001.json").write_text(
            json.dumps(
                {
                    "failure_events": [
                        {
                            "cause_type": "AGENT_SUBPROCESS_NONZERO_EXIT",
                            "stage": "planner",
                            "payload": {"subprocess_detail": {"exit_code": 2}},
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )


def test_variant_compare_summarize(tmp_path: Path):
    runtime_dir = tmp_path / "runtime"
    _write_summary(runtime_dir, "variantA-001", "MISSING_REQUIRED_TEST", "REJECTED", "rejected")
    _write_summary(runtime_dir, "variantA-002", "GRADER_FAILED", "REJECTED", "rejected")
    _write_summary(runtime_dir, "variantB-001", "", "ACCEPTED", "passed")
    rows = load_execution_summaries(runtime_dir / "evidence")
    rows_a = filter_variant_rows(rows=rows, variant_tag="variantA", match_mode="prefix", window_size=10)
    rows_b = filter_variant_rows(rows=rows, variant_tag="variantB", match_mode="prefix", window_size=10)
    summary_a = summarize_variant(name="variantA", rows=rows_a)
    summary_b = summarize_variant(name="variantB", rows=rows_b)
    assert summary_a.total_runs == 2
    assert summary_b.total_runs == 1
    assert summary_b.acceptance_pass_rate == 1.0
    assert summary_a.primary_failure_distribution.get("MISSING_REQUIRED_TEST", 0) == 1
    assert summary_a.subprocess_nonzero_exit_count == 0


def test_variant_compare_summarize_subprocess_breakdown(tmp_path: Path):
    runtime_dir = tmp_path / "runtime"
    _write_summary(runtime_dir, "variantA-001", "AGENT_SUBPROCESS_NONZERO_EXIT", "REJECTED", "rejected")
    rows = load_execution_summaries(runtime_dir / "evidence")
    rows_a = filter_variant_rows(rows=rows, variant_tag="variantA", match_mode="prefix", window_size=10)
    summary_a = summarize_variant(name="variantA", rows=rows_a)
    assert summary_a.subprocess_nonzero_exit_count == 1
    assert summary_a.subprocess_nonzero_exit_stage_distribution.get("planner", 0) == 1
    assert summary_a.subprocess_nonzero_exit_owner_distribution.get("planner", 0) == 1
    assert summary_a.subprocess_nonzero_exit_action_distribution.get("retry_same_plan", 0) == 1


def test_compare_agent_variants_script(tmp_path: Path):
    root = Path(__file__).resolve().parents[2]
    runtime_dir = tmp_path / "runtime"
    _write_summary(runtime_dir, "variantA-001", "MISSING_REQUIRED_TEST", "REJECTED", "rejected")
    _write_summary(runtime_dir, "variantB-001", "", "ACCEPTED", "passed")
    env = dict(os.environ)
    env.update({"AUTOLOOP_DATA_DIR": str(runtime_dir), "PYTHONPATH": str(root)})
    completed = subprocess.run(
        [
            sys.executable,
            str(root / "scripts" / "compare_agent_variants.py"),
            "--variant-a",
            "variantA",
            "--variant-b",
            "variantB",
            "--match-mode",
            "prefix",
        ],
        cwd=root,
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    outputs = [line.strip() for line in completed.stdout.splitlines() if line.strip()]
    assert any("variant_compare_variantA_vs_variantB.json" in line for line in outputs)
    assert any("compare_variantA_vs_variantB.md" in line for line in outputs)
    json_path = runtime_dir / "metrics" / "variant_compare_variantA_vs_variantB.json"
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert "subprocess_nonzero_exit_count" in payload["variant_a"]


def test_compare_agent_variants_script_only_subprocess(tmp_path: Path):
    root = Path(__file__).resolve().parents[2]
    runtime_dir = tmp_path / "runtime"
    _write_summary(runtime_dir, "variantA-001", "AGENT_SUBPROCESS_NONZERO_EXIT", "REJECTED", "rejected")
    _write_summary(runtime_dir, "variantB-001", "", "ACCEPTED", "passed")
    env = dict(os.environ)
    env.update({"AUTOLOOP_DATA_DIR": str(runtime_dir), "PYTHONPATH": str(root)})
    completed = subprocess.run(
        [
            sys.executable,
            str(root / "scripts" / "compare_agent_variants.py"),
            "--variant-a",
            "variantA",
            "--variant-b",
            "variantB",
            "--match-mode",
            "prefix",
            "--only-subprocess",
        ],
        cwd=root,
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    outputs = [line.strip() for line in completed.stdout.splitlines() if line.strip()]
    assert any("compare_variantA_vs_variantB.md" in line for line in outputs)
    md_path = runtime_dir / "reports" / "compare_variantA_vs_variantB.md"
    content = md_path.read_text(encoding="utf-8")
    assert "Subprocess Compare" in content
    assert "subprocess_nonzero_exit_count" in content
