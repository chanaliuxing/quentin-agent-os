from __future__ import annotations

from pathlib import Path

from quentin.diagnostics.intelligence_auditor import build_intelligence_audit


def test_intelligence_auditor_replay_fixture_exact_alignment() -> None:
    fixture = Path(__file__).resolve().parent / "fixtures" / "intelligence_auditor_mixed_replay.jsonl"
    assert fixture.exists()

    import tempfile

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        events = root / "data" / "traces" / "events.jsonl"
        events.parent.mkdir(parents=True, exist_ok=True)
        events.write_text(fixture.read_text(encoding="utf-8"), encoding="utf-8")

        report = build_intelligence_audit(repo_root=root)
        switching = (report.get("strategy_regression") or {}).get("strategy_switching") or {}

        # Multi-trace mixed replay fixture: fs/shell/browser-like steps + noisy tool channels.
        assert int(switching.get("plan_execution_expected_steps") or 0) == 10
        assert int(switching.get("plan_execution_consistency_total") or 0) == 10
        assert int(switching.get("plan_execution_exact_match_total") or 0) >= 9
        assert float(switching.get("plan_execution_observed_coverage") or 0.0) == 1.0
        assert float(switching.get("plan_execution_call_tool_coverage") or 0.0) == 0.2
        assert float(switching.get("plan_execution_exact_match_rate") or 0.0) >= 0.95
        assert float(switching.get("plan_execution_consistency_rate") or 0.0) >= 0.95
