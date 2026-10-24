import json

from app.evidence import EventRecord, EventStore, ExecutionSummary, ExecutionSummaryStore
from app.temporal.workflow import _derive_failure_diagnostics


def test_event_store_appends_and_reads(tmp_path):
    store = EventStore(base_dir=tmp_path / "events")
    event = EventRecord(
        event_id="wf.phase.workflow.001",
        event_time="2026-03-08T00:00:00Z",
        workflow_id="wf",
        run_id="wf",
        phase_id="phase_01",
        stage="workflow",
        actor="workflow",
        event_type="WORKFLOW_STARTED",
        cause_class="terminal",
    )
    path = store.append(event)
    assert path.exists()
    loaded = store.read("wf", "phase_01")
    assert loaded[0]["event_id"] == "wf.phase.workflow.001"


def test_execution_summary_store_writes_file(tmp_path):
    store = ExecutionSummaryStore(base_dir=tmp_path / "evidence")
    summary = ExecutionSummary(
        workflow_id="wf",
        phase_id="phase_01",
        primary_failure_type="PATH_CONFLICT",
        secondary_failure_types=["RUNNER_BLOCKED"],
        first_failure_at="2026-03-08T00:00:00Z",
        first_failure_event_id="wf.phase.reviewer.004",
        final_status_label="REJECTED",
        terminal_state="REJECTED",
        finalized_at="2026-03-08T00:00:05Z",
        terminal_event_id="wf.phase.workflow.999",
        recovery_action="replan_from_spec",
        acceptance_status="rejected",
    )
    path = store.write(summary)
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["workflow_id"] == "wf"
    assert payload["terminal_state"] == "REJECTED"


def test_failure_diagnostics_prefers_event_log_candidates():
    diagnostics = _derive_failure_diagnostics(
        results={},
        test_results={"status": "failed", "acceptance_status": "rejected"},
        failed_modules=[],
        events=[
            {
                "event_id": "wf.phase.workflow.001",
                "event_time": "2026-03-08T00:59:59Z",
                "failure_type": None,
                "stage": "workflow",
                "actor": "workflow",
            },
            {
                "event_id": "wf.phase.reviewer.004",
                "event_time": "2026-03-08T01:00:00Z",
                "failure_type": "PATH_CONFLICT",
                "stage": "reviewer",
                "actor": "activity",
                "cause_class": "business",
            },
            {
                "event_id": "wf.phase.workflow.007",
                "event_time": "2026-03-08T01:00:05Z",
                "failure_type": "RUNNER_BLOCKED",
                "stage": "workflow",
                "actor": "workflow",
                "cause_class": "execution",
            },
        ],
    )
    assert diagnostics["primary_failure_type"] == "PATH_CONFLICT"
    assert diagnostics["first_failure_event_id"] == "wf.phase.reviewer.004"
    assert "RUNNER_BLOCKED" in diagnostics["secondary_failure_types"]
