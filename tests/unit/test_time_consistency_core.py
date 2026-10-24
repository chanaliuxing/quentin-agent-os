from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from quentin.utils.time import now_iso, now_utc_iso, normalize_to_utc_iso
from quentin.goals.schema import GoalSpec
from quentin.goals.manager import GoalOutcome
from quentin.execution.skill_executor import StepExecutionRecord
from quentin.traces.execution_trace import ExecutionTrace
from quentin.runtime.system_events import SystemEventQueue


def _assert_tz_aware_iso(ts: str) -> None:
    dt = datetime.fromisoformat(ts)
    assert dt.tzinfo is not None
    assert dt.tzinfo == timezone.utc


def test_now_iso_defaults_to_utc_tz_aware() -> None:
    _assert_tz_aware_iso(now_iso())
    _assert_tz_aware_iso(now_utc_iso())


def test_core_models_use_tz_aware_utc_defaults(tmp_path: Path) -> None:
    goal = GoalSpec(
        goal_id="g1",
        title="t",
        description="d",
        domain="core",
        environment="sandbox",
    )
    _assert_tz_aware_iso(goal.created_at)

    outcome = GoalOutcome(goal_id="g1")
    _assert_tz_aware_iso(outcome.start_time)

    rec = StepExecutionRecord(
        step_id="s1",
        description="desc",
        skill_id=None,
        executor_mode="llm",
        success=False,
    )
    _assert_tz_aware_iso(rec.started_at)
    _assert_tz_aware_iso(rec.finished_at)

    trace = ExecutionTrace(
        trace_id="t1",
        task_id="task1",
        component_id="cog",
    )
    _assert_tz_aware_iso(trace.start_time)
    _assert_tz_aware_iso(trace.end_time)

    q = SystemEventQueue(repo_root=tmp_path)
    ev = q.enqueue_event(session_id="s1", event_type="evt", payload={"ok": True}, source="test")
    _assert_tz_aware_iso(ev.created_at)


def test_normalize_to_utc_iso_handles_naive_and_aware_inputs() -> None:
    naive = "2026-02-10T12:00:00"
    aware = "2026-02-10T12:00:00-05:00"
    n1 = normalize_to_utc_iso(naive)
    n2 = normalize_to_utc_iso(aware)
    _assert_tz_aware_iso(n1)
    _assert_tz_aware_iso(n2)
    assert n2.startswith("2026-02-10T17:00:00")
