import json
import signal
from pathlib import Path

import pytest

from app.config import settings
from app.control.shutdown import ShutdownManager
from app.control.terminal_writer import write_terminal_event_once
from app.evidence import EventRecord, EventStore
from app.main import _write_shutdown_terminal_fallback


def _prepare_runtime(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "project_root", tmp_path)
    monkeypatch.setattr(settings, "autoloop_data_dir", "runtime")
    settings.ensure_dirs()


def test_sigint_shutdown_writes_terminal_event(monkeypatch, tmp_path):
    _prepare_runtime(monkeypatch, tmp_path)
    manager = ShutdownManager()
    with pytest.raises(KeyboardInterrupt):
        manager._handle_signal(signal.SIGINT, None)
    assert manager.state.shutdown_requested is True
    assert manager.state.signal_name == "SIGINT"
    write_terminal_event_once(
        project_id="sigint-run",
        phase_id="phase_01",
        terminal_state="ABORTED",
        final_status_label="ABORTED_BY_SIGNAL",
        recommended_action="escalate_to_human",
        acceptance_status="rejected",
        primary_failure_type="",
        secondary_failure_types=[],
        failure_events=[],
        termination_reason=manager.state.termination_reason,
        trace_id="sigint-run:phase_01",
    )
    events = EventStore().read("sigint-run", "phase_01")
    assert any(event.get("event_type") == "WORKFLOW_TERMINATED" for event in events)


def test_sigterm_shutdown_writes_terminal_event(monkeypatch, tmp_path):
    _prepare_runtime(monkeypatch, tmp_path)
    manager = ShutdownManager()
    with pytest.raises(KeyboardInterrupt):
        manager._handle_signal(signal.SIGTERM, None)
    assert manager.state.shutdown_requested is True
    assert manager.state.signal_name == "SIGTERM"
    write_terminal_event_once(
        project_id="sigterm-run",
        phase_id="phase_01",
        terminal_state="ABORTED",
        final_status_label="ABORTED_BY_SIGNAL",
        recommended_action="escalate_to_human",
        acceptance_status="rejected",
        primary_failure_type="",
        secondary_failure_types=[],
        failure_events=[],
        termination_reason=manager.state.termination_reason,
        trace_id="sigterm-run:phase_01",
    )
    events = EventStore().read("sigterm-run", "phase_01")
    assert any(event.get("event_type") == "WORKFLOW_TERMINATED" for event in events)


def test_timeout_abort_terminal_preserves_primary_failure(monkeypatch, tmp_path):
    _prepare_runtime(monkeypatch, tmp_path)
    output = write_terminal_event_once(
        project_id="timeout-run",
        phase_id="phase_01",
        terminal_state="TIMEOUT",
        final_status_label="GLOBAL_TIMEOUT",
        recommended_action="replan_from_spec",
        acceptance_status="rejected",
        primary_failure_type="PATH_CONFLICT",
        secondary_failure_types=["GLOBAL_TIMEOUT"],
        failure_events=[
            {
                "event_id": "timeout-run.phase_01.reviewer.001",
                "event_time": "2026-03-08T00:00:00Z",
                "stage": "reviewer",
                "actor": "activity",
                "attempt": 1,
                "cause_type": "PATH_CONFLICT",
                "cause_class": "business",
                "is_primary_candidate": True,
            }
        ],
        termination_reason="global_timeout",
        trace_id="timeout-run:phase_01",
    )
    summary_file = output["execution_summary_file"]
    summary = json.loads(Path(summary_file).read_text(encoding="utf-8"))
    assert summary["primary_failure_type"] == "PATH_CONFLICT"
    assert summary["terminal_state"] == "TIMEOUT"


def test_accepted_terminal_clears_primary_failure(monkeypatch, tmp_path):
    _prepare_runtime(monkeypatch, tmp_path)
    output = write_terminal_event_once(
        project_id="accepted-run",
        phase_id="phase_01",
        terminal_state="ACCEPTED",
        final_status_label="ACCEPTED",
        recommended_action="advance",
        acceptance_status="passed",
        primary_failure_type="UNCLASSIFIED_ENVIRONMENT_FAILURE",
        secondary_failure_types=["STATE_DB_DEGRADED"],
        failure_events=[],
        termination_reason="workflow_completed",
        trace_id="accepted-run:phase_01",
    )
    summary = json.loads(Path(output["execution_summary_file"]).read_text(encoding="utf-8"))
    assert summary["primary_failure_type"] == ""
    assert summary["secondary_failure_types"] == []
    assert summary["terminal_state"] == "ACCEPTED"


def test_terminal_writer_is_idempotent(monkeypatch, tmp_path):
    _prepare_runtime(monkeypatch, tmp_path)
    first = write_terminal_event_once(
        project_id="idem-run",
        phase_id="phase_01",
        terminal_state="ABORTED",
        final_status_label="ABORTED_BY_SIGNAL",
        recommended_action="escalate_to_human",
        acceptance_status="rejected",
        primary_failure_type="PATH_CONFLICT",
        secondary_failure_types=[],
        failure_events=[],
        termination_reason="signal_sigint",
        trace_id="idem-run:phase_01",
    )
    second = write_terminal_event_once(
        project_id="idem-run",
        phase_id="phase_01",
        terminal_state="ABORTED",
        final_status_label="ABORTED_BY_SIGNAL",
        recommended_action="escalate_to_human",
        acceptance_status="rejected",
        primary_failure_type="PATH_CONFLICT",
        secondary_failure_types=[],
        failure_events=[],
        termination_reason="signal_sigint",
        trace_id="idem-run:phase_01",
    )
    events = EventStore().read("idem-run", "phase_01")
    terminated = [event for event in events if event.get("event_type") == "WORKFLOW_TERMINATED"]
    assert len(terminated) == 1
    assert first["terminal_event_id"] == second["terminal_event_id"]


def test_shutdown_fallback_keeps_existing_primary(monkeypatch, tmp_path):
    _prepare_runtime(monkeypatch, tmp_path)
    write_terminal_event_once(
        project_id="fallback-run",
        phase_id="phase_01",
        terminal_state="REJECTED",
        final_status_label="ACCEPTANCE_REJECTED",
        recommended_action="replan_from_spec",
        acceptance_status="rejected",
        primary_failure_type="MISSING_REQUIRED_TEST",
        secondary_failure_types=[],
        failure_events=[],
        termination_reason="workflow_rejected",
        trace_id="fallback-run:phase_01",
    )
    _write_shutdown_terminal_fallback(
        project_id="fallback-run",
        phase_id="phase_01",
        termination_reason="signal_sigterm",
    )
    summary_file = (
        settings.runtime_dir / "evidence" / "fallback-run" / "phase_01" / "execution_summary.json"
    )
    summary = json.loads(summary_file.read_text(encoding="utf-8"))
    assert summary["primary_failure_type"] == "MISSING_REQUIRED_TEST"


def test_shutdown_fallback_derives_timeout_from_event_log(monkeypatch, tmp_path):
    _prepare_runtime(monkeypatch, tmp_path)
    EventStore().append(
        EventRecord(
            event_id="timeout-fallback.phase_01.reviewer.001",
            event_time="2026-03-09T00:00:00Z",
            workflow_id="timeout-fallback",
            run_id="timeout-fallback",
            phase_id="phase_01",
            stage="reviewer",
            actor="activity",
            event_type="STAGE_TIMEOUT",
            cause_class="execution",
            failure_type="GLOBAL_TIMEOUT",
            payload={"reason": "Timeout after 1800s"},
            trace_id="timeout-fallback:phase_01",
        )
    )

    _write_shutdown_terminal_fallback(
        project_id="timeout-fallback",
        phase_id="phase_01",
        termination_reason="signal_sigterm",
    )

    summary_file = (
        settings.runtime_dir / "evidence" / "timeout-fallback" / "phase_01" / "execution_summary.json"
    )
    summary = json.loads(summary_file.read_text(encoding="utf-8"))
    assert summary["primary_failure_type"] == "GLOBAL_TIMEOUT"
    assert summary["terminal_state"] == "TIMEOUT"
    events = EventStore().read("timeout-fallback", "phase_01")
    assert any(event.get("event_type") == "WORKFLOW_TERMINATED" for event in events)


def test_shutdown_fallback_forced_timeout_from_signal(monkeypatch, tmp_path):
    _prepare_runtime(monkeypatch, tmp_path)
    monkeypatch.setenv("AUTOLOOP_TIMEOUT_TERMINATES_AS_GLOBAL_TIMEOUT", "1")

    _write_shutdown_terminal_fallback(
        project_id="forced-timeout-fallback",
        phase_id="phase_01",
        termination_reason="signal_sigterm",
    )

    summary_file = (
        settings.runtime_dir
        / "evidence"
        / "forced-timeout-fallback"
        / "phase_01"
        / "execution_summary.json"
    )
    summary = json.loads(summary_file.read_text(encoding="utf-8"))
    assert summary["primary_failure_type"] == "GLOBAL_TIMEOUT"
    assert summary["terminal_state"] == "TIMEOUT"
