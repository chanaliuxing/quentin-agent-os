from __future__ import annotations

import json
import os
import time
from types import SimpleNamespace

from quentin.runtime.brain_daemon import BrainDaemon, BrainDaemonConfig
from quentin.runtime.system_events import SystemEventQueue
from quentin.runtime.task_queue import TaskQueueItem


class _DummyLoop:
    def __init__(self, status: str) -> None:
        self._status = status

    def run_task(self, task):  # type: ignore[no-untyped-def]
        _ = task
        return SimpleNamespace(
            task_id="t1",
            goal_id="g1",
            done=False,
            done_confidence=0.0,
            final_output="",
            self_awareness={
                "status": self._status,
                "failover_reason": "timeout",
                "anti_pattern_reason": "interactive_editor_command",
                "suggested_actions": ["switch_to_fs_read_and_write_flow"],
            },
        )


class _DummySleep:
    def run_once(self):  # type: ignore[no-untyped-def]
        return {"status": "ok"}


class _DummyImmune:
    def process_trace(self):  # type: ignore[no-untyped-def]
        return {"status": "ok"}


def _build_container(status: str) -> object:
    return SimpleNamespace(
        cognitive_loop=_DummyLoop(status=status),
        sleep_loop=_DummySleep(),
        immune_loop=_DummyImmune(),
    )


def test_brain_daemon_applies_guardrail_and_enqueues_recovery(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("QUENTIN_TASK_QUEUE_PATH", str(tmp_path / "queue.jsonl"))
    monkeypatch.setenv("QUENTIN_BRAIN_GUARDRAIL_COOLDOWN_SEC", "60")

    daemon = BrainDaemon(
        config=BrainDaemonConfig(run_sleep_loop=False, run_immune_loop=False),
        container=_build_container("critical"),  # type: ignore[arg-type]
    )

    out = daemon.run_once(input_text="x")
    assert out["self_awareness"]["status"] == "critical"
    assert out["runtime_mode"] in {"guardrail", "intelligence_strict", "recover_task_sources", "recover_patchflow", "normal"}
    guardrail_state = out.get("guardrail_state") or {}
    assert "guardrail_remaining_sec" in guardrail_state
    assert "can_run_task_sources" in guardrail_state
    assert daemon._guardrail_until > time.time()

    items = daemon.task_queue.load_all(limit=100)
    assert any((it.metadata or {}).get("kind") == "self_awareness_recovery" for it in items)


def test_brain_daemon_drain_keeps_non_awareness_events(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("QUENTIN_TASK_QUEUE_PATH", str(tmp_path / "queue.jsonl"))

    daemon = BrainDaemon(
        config=BrainDaemonConfig(run_sleep_loop=False, run_immune_loop=False),
        container=_build_container("healthy"),  # type: ignore[arg-type]
    )

    queue = SystemEventQueue(repo_root=tmp_path)
    daemon.system_event_queue = queue
    queue.enqueue_event(
        session_id=daemon.config.session_id,
        event_type="self_awareness_alert",
        payload={"status": "warning", "goal_id": "g2", "failover_reason": "timeout"},
        source="test",
    )
    queue.enqueue_event(
        session_id=daemon.config.session_id,
        event_type="self_programming_patch_applied",
        payload={"patch_id": "p1"},
        source="test",
    )

    daemon._drain_self_awareness_events_into_guardrails()

    events = queue.drain_events(session_id=daemon.config.session_id, limit=20)
    assert any(e.event_type == "self_programming_patch_applied" for e in events)


def test_guardrail_claim_preempts_recovery_task(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("QUENTIN_TASK_QUEUE_PATH", str(tmp_path / "queue.jsonl"))
    daemon = BrainDaemon(
        config=BrainDaemonConfig(run_sleep_loop=False, run_immune_loop=False),
        container=_build_container("healthy"),  # type: ignore[arg-type]
    )
    daemon._guardrail_until = time.time() + 120.0

    daemon.task_queue.append(
        TaskQueueItem.new(
            input_text="high risk gap",
            priority=10,
            metadata={"kind": "blueprint_gap"},
        )
    )
    daemon.task_queue.append(
        TaskQueueItem.new(
            input_text="recovery",
            priority=1,
            metadata={"kind": "self_awareness_recovery"},
        )
    )
    daemon.task_queue.append(
        TaskQueueItem.new(
            input_text="normal task",
            priority=9,
            metadata={"kind": "generic"},
        )
    )

    claimed = daemon._claim_next_item(worker_id="w1")
    assert claimed is not None
    assert (claimed.metadata or {}).get("kind") == "self_awareness_recovery"


def test_guardrail_claim_defers_blocked_and_claims_safe(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("QUENTIN_TASK_QUEUE_PATH", str(tmp_path / "queue.jsonl"))
    daemon = BrainDaemon(
        config=BrainDaemonConfig(run_sleep_loop=False, run_immune_loop=False),
        container=_build_container("healthy"),  # type: ignore[arg-type]
    )
    daemon._guardrail_until = time.time() + 120.0

    daemon.task_queue.append(
        TaskQueueItem.new(
            input_text="backlog",
            priority=10,
            metadata={"kind": "patchflow_backlog"},
        )
    )
    daemon.task_queue.append(
        TaskQueueItem.new(
            input_text="safe low priority",
            priority=1,
            metadata={"kind": "generic"},
        )
    )

    claimed = daemon._claim_next_item(worker_id="w1")
    assert claimed is not None
    assert (claimed.metadata or {}).get("kind") == "generic"


def test_no_guardrail_claims_highest_priority_normally(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("QUENTIN_TASK_QUEUE_PATH", str(tmp_path / "queue.jsonl"))
    daemon = BrainDaemon(
        config=BrainDaemonConfig(run_sleep_loop=False, run_immune_loop=False),
        container=_build_container("healthy"),  # type: ignore[arg-type]
    )
    daemon._guardrail_until = 0.0

    daemon.task_queue.append(
        TaskQueueItem.new(
            input_text="low",
            priority=1,
            metadata={"kind": "generic"},
        )
    )
    daemon.task_queue.append(
        TaskQueueItem.new(
            input_text="high",
            priority=9,
            metadata={"kind": "blueprint_gap"},
        )
    )

    claimed = daemon._claim_next_item(worker_id="w1")
    assert claimed is not None
    assert claimed.input_text == "high"


def test_runtime_mode_staged_recovery_windows(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("QUENTIN_TASK_QUEUE_PATH", str(tmp_path / "queue.jsonl"))

    daemon = BrainDaemon(
        config=BrainDaemonConfig(run_sleep_loop=False, run_immune_loop=False),
        container=_build_container("healthy"),  # type: ignore[arg-type]
    )

    base = time.time()
    daemon._guardrail_until = base + 50.0
    daemon._recover_task_sources_until = base + 80.0
    daemon._recover_patchflow_until = base + 120.0

    assert daemon._runtime_mode(now=base + 10.0) == "guardrail"
    assert daemon._runtime_mode(now=base + 60.0) == "recover_task_sources"
    assert daemon._runtime_mode(now=base + 100.0) == "recover_patchflow"
    assert daemon._runtime_mode(now=base + 130.0) == "normal"

    assert daemon._can_run_task_sources(now=base + 10.0) is False
    assert daemon._can_run_task_sources(now=base + 60.0) is True
    assert daemon._can_run_patchflow(now=base + 60.0) is False
    assert daemon._can_run_patchflow(now=base + 100.0) is True
    assert daemon._can_run_blueprint_autopatch(now=base + 100.0) is False
    assert daemon._can_run_blueprint_autopatch(now=base + 130.0) is True


def test_apply_guardrail_sets_recovery_stages(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("QUENTIN_TASK_QUEUE_PATH", str(tmp_path / "queue.jsonl"))
    monkeypatch.setenv("QUENTIN_BRAIN_GUARDRAIL_COOLDOWN_SEC", "10")
    monkeypatch.setenv("QUENTIN_BRAIN_RECOVER_TASK_SOURCES_SEC", "5")
    monkeypatch.setenv("QUENTIN_BRAIN_RECOVER_PATCHFLOW_SEC", "7")

    daemon = BrainDaemon(
        config=BrainDaemonConfig(run_sleep_loop=False, run_immune_loop=False),
        container=_build_container("healthy"),  # type: ignore[arg-type]
    )
    daemon._apply_self_awareness_guardrails(
        self_awareness={"status": "warning", "goal_id": "g3"},
        session_id="brain",
        goal_id="g3",
    )
    assert daemon._guardrail_until > time.time()
    assert daemon._recover_task_sources_until >= daemon._guardrail_until + 5.0
    assert daemon._recover_patchflow_until >= daemon._recover_task_sources_until + 7.0


def test_guardrail_tuning_increases_after_recovery_failures(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("QUENTIN_TASK_QUEUE_PATH", str(tmp_path / "queue.jsonl"))
    monkeypatch.setenv("QUENTIN_BRAIN_GUARDRAIL_TUNE_UP", "1.2")
    daemon = BrainDaemon(
        config=BrainDaemonConfig(run_sleep_loop=False, run_immune_loop=False),
        container=_build_container("healthy"),  # type: ignore[arg-type]
    )
    before = dict(daemon._guardrail_tuning)
    daemon._update_guardrail_tuning_from_recovery_outcome(ok=False)
    daemon._update_guardrail_tuning_from_recovery_outcome(ok=False)
    after = dict(daemon._guardrail_tuning)
    assert after["cooldown_mult"] > before["cooldown_mult"]
    assert after["recover_task_sources_mult"] > before["recover_task_sources_mult"]
    assert daemon._last_tuning_adjustment.get("trigger_reason") == "fail_streak"
    assert daemon._last_tuning_adjustment.get("factor", 1.0) > 1.0


def test_guardrail_tuning_emits_event_with_explanation(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("QUENTIN_TASK_QUEUE_PATH", str(tmp_path / "queue.jsonl"))
    daemon = BrainDaemon(
        config=BrainDaemonConfig(run_sleep_loop=False, run_immune_loop=False),
        container=_build_container("healthy"),  # type: ignore[arg-type]
    )
    daemon._update_guardrail_tuning_from_recovery_outcome(ok=False)
    daemon._update_guardrail_tuning_from_recovery_outcome(ok=False)
    events = daemon.system_event_queue.drain_events(session_id=daemon.config.session_id, limit=50)
    tuned = [e for e in events if e.event_type == "brain_guardrail_tuned"]
    assert tuned
    payload = tuned[-1].payload
    assert str(payload.get("trigger_reason") or "") == "fail_streak"
    assert float(payload.get("factor") or 1.0) > 1.0
    assert isinstance(payload.get("before"), dict)
    assert isinstance(payload.get("after"), dict)


def test_guardrail_tuning_emits_summary_every_n_adjustments(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("QUENTIN_TASK_QUEUE_PATH", str(tmp_path / "queue.jsonl"))
    monkeypatch.setenv("QUENTIN_BRAIN_GUARDRAIL_TUNE_SUMMARY_EVERY", "2")
    daemon = BrainDaemon(
        config=BrainDaemonConfig(run_sleep_loop=False, run_immune_loop=False),
        container=_build_container("healthy"),  # type: ignore[arg-type]
    )
    # Produce two adjustments: each pair of failures triggers one adjustment.
    daemon._update_guardrail_tuning_from_recovery_outcome(ok=False)
    daemon._update_guardrail_tuning_from_recovery_outcome(ok=False)
    daemon._update_guardrail_tuning_from_recovery_outcome(ok=False)
    daemon._update_guardrail_tuning_from_recovery_outcome(ok=False)

    events = daemon.system_event_queue.drain_events(session_id=daemon.config.session_id, limit=100)
    summary = [e for e in events if e.event_type == "brain_guardrail_tuning_summary"]
    assert summary
    payload = summary[-1].payload
    assert int(payload.get("window_size") or 0) == 2
    assert int(payload.get("tuning_adjustment_count") or 0) >= 2
    assert isinstance(payload.get("reason_counts"), dict)


def test_guardrail_tuning_summary_worsening_escalates_intelligence_strict(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("QUENTIN_TASK_QUEUE_PATH", str(tmp_path / "queue.jsonl"))
    monkeypatch.setenv("QUENTIN_DONE_COUNCIL_STRICT_REASONING", "0")
    monkeypatch.setenv("QUENTIN_BRAIN_GUARDRAIL_TUNE_SUMMARY_EVERY", "1")
    monkeypatch.setenv("QUENTIN_BRAIN_GUARDRAIL_TUNE_WORSENING_STREAK", "2")
    monkeypatch.setenv("QUENTIN_BRAIN_GUARDRAIL_TUNE_STRICT_SEC", "60")
    daemon = BrainDaemon(
        config=BrainDaemonConfig(run_sleep_loop=False, run_immune_loop=False),
        container=_build_container("healthy"),  # type: ignore[arg-type]
    )

    daemon._update_guardrail_tuning_from_recovery_outcome(ok=False)
    daemon._update_guardrail_tuning_from_recovery_outcome(ok=False)
    assert daemon._intelligence_strict_until <= time.time()

    daemon._update_guardrail_tuning_from_recovery_outcome(ok=False)
    daemon._update_guardrail_tuning_from_recovery_outcome(ok=False)
    assert daemon._runtime_mode() == "intelligence_strict"
    assert "guardrail_tuning_summary_worsening" in list(daemon._intelligence_strict_reasons)
    assert os.getenv("QUENTIN_DONE_COUNCIL_STRICT_REASONING") == "1"
    state = daemon._guardrail_state()
    assert int(state.get("tuning_summary_worsening_streak") or 0) >= 2

    events = daemon.system_event_queue.drain_events(session_id=daemon.config.session_id, limit=200)
    strict_changed = [e for e in events if e.event_type == "brain_intelligence_strict_mode_changed"]
    assert strict_changed
    payload = strict_changed[-1].payload
    assert str(payload.get("trigger") or "") == "guardrail_tuning_summary"


def test_guardrail_tuning_summary_worsening_streak_resets_on_stable_summary(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("QUENTIN_TASK_QUEUE_PATH", str(tmp_path / "queue.jsonl"))
    monkeypatch.setenv("QUENTIN_BRAIN_GUARDRAIL_TUNE_SUMMARY_EVERY", "1")
    monkeypatch.setenv("QUENTIN_BRAIN_GUARDRAIL_TUNE_WORSENING_STREAK", "2")
    monkeypatch.setenv("QUENTIN_BRAIN_GUARDRAIL_TUNE_STRICT_SEC", "60")
    monkeypatch.setenv("QUENTIN_BRAIN_GUARDRAIL_TUNE_DOWN", "0.9")
    daemon = BrainDaemon(
        config=BrainDaemonConfig(run_sleep_loop=False, run_immune_loop=False),
        container=_build_container("healthy"),  # type: ignore[arg-type]
    )

    daemon._update_guardrail_tuning_from_recovery_outcome(ok=False)
    daemon._update_guardrail_tuning_from_recovery_outcome(ok=False)
    assert int(daemon._tuning_summary_worsening_streak or 0) >= 1

    daemon._recovery_outcomes.clear()
    for _ in range(4):
        daemon._update_guardrail_tuning_from_recovery_outcome(ok=True)
    assert int(daemon._tuning_summary_worsening_streak or 0) == 0


def test_guardrail_tuning_decreases_after_stable_recovery(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("QUENTIN_TASK_QUEUE_PATH", str(tmp_path / "queue.jsonl"))
    monkeypatch.setenv("QUENTIN_BRAIN_GUARDRAIL_TUNE_DOWN", "0.9")
    daemon = BrainDaemon(
        config=BrainDaemonConfig(run_sleep_loop=False, run_immune_loop=False),
        container=_build_container("healthy"),  # type: ignore[arg-type]
    )
    daemon._guardrail_tuning["cooldown_mult"] = 2.0
    daemon._guardrail_tuning["recover_task_sources_mult"] = 2.0
    daemon._guardrail_tuning["recover_patchflow_mult"] = 2.0
    for _ in range(5):
        daemon._update_guardrail_tuning_from_recovery_outcome(ok=True)
    assert daemon._guardrail_tuning["cooldown_mult"] < 2.0
    assert daemon._guardrail_tuning["recover_patchflow_mult"] < 2.0


def test_apply_guardrail_uses_tuned_multipliers(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("QUENTIN_TASK_QUEUE_PATH", str(tmp_path / "queue.jsonl"))
    monkeypatch.setenv("QUENTIN_BRAIN_GUARDRAIL_COOLDOWN_SEC", "10")
    monkeypatch.setenv("QUENTIN_BRAIN_RECOVER_TASK_SOURCES_SEC", "5")
    monkeypatch.setenv("QUENTIN_BRAIN_RECOVER_PATCHFLOW_SEC", "7")
    daemon = BrainDaemon(
        config=BrainDaemonConfig(run_sleep_loop=False, run_immune_loop=False),
        container=_build_container("healthy"),  # type: ignore[arg-type]
    )
    daemon._guardrail_tuning["cooldown_mult"] = 2.0
    daemon._guardrail_tuning["recover_task_sources_mult"] = 2.0
    daemon._guardrail_tuning["recover_patchflow_mult"] = 2.0
    start = time.time()
    daemon._apply_self_awareness_guardrails(
        self_awareness={"status": "warning", "goal_id": "g4"},
        session_id="brain",
        goal_id="g4",
    )
    assert daemon._guardrail_until >= start + 19.0
    assert daemon._recover_task_sources_until >= daemon._guardrail_until + 9.0
    assert daemon._recover_patchflow_until >= daemon._recover_task_sources_until + 13.0


def test_guardrail_state_exposes_remaining_windows(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("QUENTIN_TASK_QUEUE_PATH", str(tmp_path / "queue.jsonl"))
    daemon = BrainDaemon(
        config=BrainDaemonConfig(run_sleep_loop=False, run_immune_loop=False),
        container=_build_container("healthy"),  # type: ignore[arg-type]
    )
    base = time.time()
    daemon._guardrail_until = base + 10.0
    daemon._recover_task_sources_until = base + 20.0
    daemon._recover_patchflow_until = base + 30.0
    state = daemon._guardrail_state(now=base + 1.0)
    assert state["runtime_mode"] == "guardrail"
    assert state["guardrail_remaining_sec"] > 0
    assert state["recover_patchflow_remaining_sec"] > state["recover_task_sources_remaining_sec"]


def test_guardrail_tuning_persists_across_daemon_restart(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("QUENTIN_TASK_QUEUE_PATH", str(tmp_path / "queue.jsonl"))
    monkeypatch.setenv("QUENTIN_BRAIN_GUARDRAIL_STATE_PATH", str(tmp_path / "brain_guardrail_state.json"))

    daemon1 = BrainDaemon(
        config=BrainDaemonConfig(run_sleep_loop=False, run_immune_loop=False),
        container=_build_container("healthy"),  # type: ignore[arg-type]
    )
    daemon1._update_guardrail_tuning_from_recovery_outcome(ok=False)
    daemon1._update_guardrail_tuning_from_recovery_outcome(ok=False)
    tuned = dict(daemon1._guardrail_tuning)
    assert tuned["cooldown_mult"] > 1.0

    daemon2 = BrainDaemon(
        config=BrainDaemonConfig(run_sleep_loop=False, run_immune_loop=False),
        container=_build_container("healthy"),  # type: ignore[arg-type]
    )
    assert daemon2._guardrail_tuning["cooldown_mult"] == tuned["cooldown_mult"]
    assert daemon2._recovery_success_rate() == 0.0
    assert daemon2._last_tuning_adjustment.get("trigger_reason") == "fail_streak"


def test_guardrail_state_file_written_on_activation(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("QUENTIN_TASK_QUEUE_PATH", str(tmp_path / "queue.jsonl"))
    state_path = tmp_path / "brain_guardrail_state.json"
    monkeypatch.setenv("QUENTIN_BRAIN_GUARDRAIL_STATE_PATH", str(state_path))

    daemon = BrainDaemon(
        config=BrainDaemonConfig(run_sleep_loop=False, run_immune_loop=False),
        container=_build_container("healthy"),  # type: ignore[arg-type]
    )
    daemon._apply_self_awareness_guardrails(
        self_awareness={"status": "warning", "goal_id": "g5"},
        session_id="brain",
        goal_id="g5",
    )
    assert state_path.exists()
    raw = json.loads(state_path.read_text(encoding="utf-8") or "{}")
    assert "tuning" in raw
    assert "recovery_outcomes" in raw


def test_intelligence_strict_mode_enables_done_council_strict_env(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("QUENTIN_TASK_QUEUE_PATH", str(tmp_path / "queue.jsonl"))
    monkeypatch.setenv("QUENTIN_DONE_COUNCIL_STRICT_REASONING", "0")
    monkeypatch.setenv("QUENTIN_BRAIN_INTELLIGENCE_EVERY_SEC", "0")
    monkeypatch.setenv("QUENTIN_BRAIN_INTELLIGENCE_STRICT_SEC", "60")

    daemon = BrainDaemon(
        config=BrainDaemonConfig(run_sleep_loop=False, run_immune_loop=False),
        container=_build_container("healthy"),  # type: ignore[arg-type]
    )
    daemon._load_observability_overview = lambda: {  # type: ignore[method-assign]
        "intelligence": {
            "planner_repairs": {
                "repair_rate": 0.6,
                "discovery_precheck": {"compliance_rate": 0.5},
            },
            "blocked_action_recurrence": {"repeat_ratio": 0.4},
            "done_council_quality": {"weak_resolution_rate": 0.4},
        }
    }

    daemon._refresh_intelligence_autoregression_if_needed()

    assert daemon._runtime_mode() == "intelligence_strict"
    assert os.getenv("QUENTIN_DONE_COUNCIL_STRICT_REASONING") == "1"
    strict_reasons_env = str(os.getenv("QUENTIN_DONE_COUNCIL_STRICT_REASONS") or "")
    assert "blocked_action_repeat_high" in strict_reasons_env
    state = daemon._guardrail_state()
    assert state["intelligence_strict_remaining_sec"] > 0.0
    assert "blocked_action_repeat_high" in state["intelligence_strict_reasons"]
    items = daemon.task_queue.load_all(limit=100)
    rec = [it for it in items if (it.metadata or {}).get("kind") == "intelligence_regression_recovery"]
    assert rec
    assert "blocked_action_repeat_high" in ((rec[0].metadata or {}).get("reasons") or [])


def test_intelligence_strict_mode_clears_and_restores_env_after_expire(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("QUENTIN_TASK_QUEUE_PATH", str(tmp_path / "queue.jsonl"))
    monkeypatch.setenv("QUENTIN_DONE_COUNCIL_STRICT_REASONING", "0")
    monkeypatch.setenv("QUENTIN_DONE_COUNCIL_STRICT_REASONS", "baseline_reason")
    monkeypatch.setenv("QUENTIN_BRAIN_INTELLIGENCE_EVERY_SEC", "0")

    daemon = BrainDaemon(
        config=BrainDaemonConfig(run_sleep_loop=False, run_immune_loop=False),
        container=_build_container("healthy"),  # type: ignore[arg-type]
    )
    daemon._intelligence_strict_until = time.time() + 30.0
    daemon._intelligence_strict_reasons.append("planner_repair_rate_high")
    daemon._sync_done_council_strict_env()
    assert os.getenv("QUENTIN_DONE_COUNCIL_STRICT_REASONING") == "1"
    assert "planner_repair_rate_high" in str(os.getenv("QUENTIN_DONE_COUNCIL_STRICT_REASONS") or "")

    daemon._intelligence_strict_until = time.time() - 1.0
    daemon._load_observability_overview = lambda: {  # type: ignore[method-assign]
        "intelligence": {
            "planner_repairs": {
                "repair_rate": 0.0,
                "discovery_precheck": {"compliance_rate": 1.0},
            },
            "blocked_action_recurrence": {"repeat_ratio": 0.0},
            "done_council_quality": {"weak_resolution_rate": 1.0},
        }
    }
    daemon._refresh_intelligence_autoregression_if_needed()

    assert daemon._runtime_mode() == "normal"
    assert os.getenv("QUENTIN_DONE_COUNCIL_STRICT_REASONING") == "0"
    assert os.getenv("QUENTIN_DONE_COUNCIL_STRICT_REASONS") == "baseline_reason"
    assert list(daemon._intelligence_strict_reasons) == []


def test_intelligence_recovery_task_is_deduplicated_by_reason_key(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("QUENTIN_TASK_QUEUE_PATH", str(tmp_path / "queue.jsonl"))
    monkeypatch.setenv("QUENTIN_BRAIN_INTELLIGENCE_EVERY_SEC", "0")
    daemon = BrainDaemon(
        config=BrainDaemonConfig(run_sleep_loop=False, run_immune_loop=False),
        container=_build_container("healthy"),  # type: ignore[arg-type]
    )
    daemon._load_observability_overview = lambda: {  # type: ignore[method-assign]
        "intelligence": {
            "planner_repairs": {"repair_rate": 0.7, "discovery_precheck": {"compliance_rate": 0.3}},
            "blocked_action_recurrence": {
                "repeat_ratio": 0.6,
                "top_actions": [{"action": "nano", "count": 3}],
            },
            "done_council_quality": {"weak_resolution_rate": 0.2},
        }
    }
    daemon._refresh_intelligence_autoregression_if_needed()
    daemon._refresh_intelligence_autoregression_if_needed()

    items = daemon.task_queue.load_all(limit=200)
    rec = [it for it in items if (it.metadata or {}).get("kind") == "intelligence_regression_recovery"]
    assert len(rec) == 1


def test_intelligence_recovery_task_uses_reason_specific_template(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("QUENTIN_TASK_QUEUE_PATH", str(tmp_path / "queue.jsonl"))
    monkeypatch.setenv("QUENTIN_BRAIN_INTELLIGENCE_EVERY_SEC", "0")
    daemon = BrainDaemon(
        config=BrainDaemonConfig(run_sleep_loop=False, run_immune_loop=False),
        container=_build_container("healthy"),  # type: ignore[arg-type]
    )
    daemon._load_observability_overview = lambda: {  # type: ignore[method-assign]
        "intelligence": {
            "planner_repairs": {"repair_rate": 0.8, "discovery_precheck": {"compliance_rate": 0.3}},
            "blocked_action_recurrence": {
                "repeat_ratio": 0.6,
                "top_actions": [{"action": "nano", "count": 3}],
            },
            "done_council_quality": {"weak_resolution_rate": 0.2},
        }
    }
    daemon._refresh_intelligence_autoregression_if_needed()

    items = daemon.task_queue.load_all(limit=100)
    rec = [it for it in items if (it.metadata or {}).get("kind") == "intelligence_regression_recovery"]
    assert rec
    md = rec[0].metadata or {}
    text = rec[0].input_text or ""
    assert md.get("recovery_focus") == "guessing_trap"
    assert "Guessing trap" in text
    assert "Semantic stagnation" in text
    assert "Self-awareness gap" in text
    assert "nano" in text


def test_intelligence_recovery_outcome_updates_state_and_event(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("QUENTIN_TASK_QUEUE_PATH", str(tmp_path / "queue.jsonl"))
    daemon = BrainDaemon(
        config=BrainDaemonConfig(run_sleep_loop=False, run_immune_loop=False),
        container=_build_container("healthy"),  # type: ignore[arg-type]
    )
    daemon._record_intelligence_recovery_outcome(ok=False, task_id="t1", reason_key="a|b")
    daemon._record_intelligence_recovery_outcome(ok=True, task_id="t2", reason_key="a|b")

    state = daemon._guardrail_state()
    assert state["intelligence_recovery_success_rate"] == 0.5
    assert state["intelligence_recovery_outcomes_tail"][-2:] == [False, True]

    events = daemon.system_event_queue.drain_events(session_id=daemon.config.session_id, limit=50)
    rec_events = [e for e in events if e.event_type == "brain_intelligence_recovery_outcome"]
    assert len(rec_events) >= 2
    assert float((rec_events[-1].payload or {}).get("success_rate") or 0.0) == 0.5


def test_intelligence_recovery_outcomes_persist_across_restart(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("QUENTIN_TASK_QUEUE_PATH", str(tmp_path / "queue.jsonl"))
    monkeypatch.setenv("QUENTIN_BRAIN_GUARDRAIL_STATE_PATH", str(tmp_path / "brain_guardrail_state.json"))
    daemon1 = BrainDaemon(
        config=BrainDaemonConfig(run_sleep_loop=False, run_immune_loop=False),
        container=_build_container("healthy"),  # type: ignore[arg-type]
    )
    daemon1._record_intelligence_recovery_outcome(ok=True, task_id="t1", reason_key="k")
    daemon1._record_intelligence_recovery_outcome(ok=False, task_id="t2", reason_key="k")
    assert daemon1._intelligence_recovery_success_rate() == 0.5

    daemon2 = BrainDaemon(
        config=BrainDaemonConfig(run_sleep_loop=False, run_immune_loop=False),
        container=_build_container("healthy"),  # type: ignore[arg-type]
    )
    assert daemon2._intelligence_recovery_success_rate() == 0.5
