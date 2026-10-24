from __future__ import annotations

from pathlib import Path

from quentin.blueprint.evidence_emitter import emit_blueprint_spec_v3_evidence
from quentin.blueprint.tracker import BlueprintGapTracker


def test_blueprint_scan_can_be_made_fully_green(tmp_path: Path, monkeypatch) -> None:
    repo_root = Path(__file__).resolve().parents[2]
    spec_path = (repo_root / "blueprint" / "spec_v3.json").resolve()

    kv_path = (tmp_path / "kv_store.sqlite3").resolve()
    traces_root = tmp_path

    # Ensure the tracker reads experiments from our temp KV.
    monkeypatch.setenv("QUENTIN_KVSTORE_PATH", str(kv_path))

    emit_blueprint_spec_v3_evidence(
        repo_root=traces_root,
        spec_path=spec_path,  # absolute ok
        kv_path=kv_path,
    )

    tracker = BlueprintGapTracker(
        repo_root=repo_root,
        spec_path=spec_path,  # absolute ok
        trace_file_path=(traces_root / "data" / "traces" / "events.jsonl").resolve(),
    )
    report = tracker.scan()

    assert report.total_items > 0
    assert abs(report.avg_score - 1.0) < 1e-9
    for it in report.items:
        assert it.file_implemented, it.spec.id
        assert it.has_traces, it.spec.id
        assert it.has_experiments, it.spec.id

