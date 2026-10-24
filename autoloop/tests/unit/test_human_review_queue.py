import json
from pathlib import Path

from app.review import (
    build_review_task_patch,
    latest_human_review,
    latest_review_resolution,
    list_human_reviews,
    resolve_human_review,
)


def test_list_human_reviews_reads_hook_payloads(tmp_path):
    hooks_dir = tmp_path / "runtime" / "hooks"
    hooks_dir.mkdir(parents=True, exist_ok=True)
    hook_file = hooks_dir / "phase_01_human_review_required.json"
    hook_file.write_text(
        json.dumps(
            {
                "phase_id": "phase_01",
                "status": "human_review_required",
                "acceptance_status": "rejected",
                "failed_modules": ["module_main"],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    rows = list_human_reviews(hooks_dir)
    assert len(rows) == 1
    assert rows[0]["phase_id"] == "phase_01"
    assert rows[0]["hook_file"] == str(hook_file)


def test_latest_human_review_returns_newest_entry(tmp_path):
    hooks_dir = tmp_path / "runtime" / "hooks"
    hooks_dir.mkdir(parents=True, exist_ok=True)
    old_file = hooks_dir / "phase_01_human_review_required.json"
    old_file.write_text(json.dumps({"phase_id": "phase_01"}), encoding="utf-8")
    new_file = hooks_dir / "phase_02_human_review_required.json"
    new_file.write_text(json.dumps({"phase_id": "phase_02"}), encoding="utf-8")

    latest = latest_human_review(hooks_dir)
    assert latest is not None
    assert latest["phase_id"] == "phase_02"
    assert Path(latest["hook_file"]).name == "phase_02_human_review_required.json"


def test_resolve_human_review_archives_required_hook(tmp_path):
    hooks_dir = tmp_path / "runtime" / "hooks"
    hooks_dir.mkdir(parents=True, exist_ok=True)
    hook_file = hooks_dir / "phase_01_human_review_required.json"
    hook_file.write_text(
        json.dumps({"phase_id": "phase_01", "project_id": "p1", "prd_path": "/tmp/prd.md"}),
        encoding="utf-8",
    )

    payload = resolve_human_review(
        phase_id="phase_01",
        decision="approved",
        reviewer="lead",
        notes="looks good",
        policy_version="manual_review_v1",
        hooks_dir=hooks_dir,
    )
    resolution_file = Path(payload["resolution_file"])
    archived_hook = Path(payload["archived_required_hook"])

    assert resolution_file.exists()
    assert archived_hook.exists()
    assert not hook_file.exists()
    resolution = json.loads(resolution_file.read_text(encoding="utf-8"))
    assert resolution["decision"] == "approved"
    assert resolution["policy_version"] == "manual_review_v1"


def test_latest_review_resolution_and_patch(tmp_path):
    hooks_dir = tmp_path / "runtime" / "hooks"
    hooks_dir.mkdir(parents=True, exist_ok=True)
    resolution_file = hooks_dir / "phase_01_human_review_resolution.json"
    resolution_file.write_text(
        json.dumps(
            {
                "phase_id": "phase_01",
                "decision": "approved",
                "reviewer": "lead",
                "notes": "add explicit required test mapping",
            }
        ),
        encoding="utf-8",
    )

    latest_resolution = latest_review_resolution(hooks_dir)
    assert latest_resolution is not None
    assert latest_resolution["decision"] == "approved"

    patch = build_review_task_patch(phase_id="phase_01", module_name="module_main", hooks_dir=hooks_dir)
    assert patch is not None
    assert patch["reviewer"] == "lead"
    assert "required test mapping" in patch["notes"]


def test_resolve_human_review_includes_repair_template_from_evidence(tmp_path):
    hooks_dir = tmp_path / "runtime" / "hooks"
    hooks_dir.mkdir(parents=True, exist_ok=True)
    evidence_file = tmp_path / "runtime" / "evidence" / "run_01" / "phase_01" / "evidence_01.json"
    evidence_file.parent.mkdir(parents=True, exist_ok=True)
    evidence_file.write_text(
        json.dumps(
            {
                "first_failure_stage": "required_test_missing",
                "failure_signature": "required_test_missing:integration",
            }
        ),
        encoding="utf-8",
    )
    required_hook = hooks_dir / "phase_01_human_review_required.json"
    required_hook.write_text(
        json.dumps(
            {
                "phase_id": "phase_01",
                "project_id": "p1",
                "evidence_file": str(evidence_file),
                "trace_id": "run_01:phase_01:0",
            }
        ),
        encoding="utf-8",
    )

    payload = resolve_human_review(
        phase_id="phase_01",
        decision="approved",
        reviewer="lead",
        hooks_dir=hooks_dir,
    )
    assert payload["repair_template"]
    assert payload["trace_id"] == "run_01:phase_01:0"
