from __future__ import annotations

from dataclasses import dataclass
import os
import time
import asyncio
import inspect
import json
import logging
from pathlib import Path
from collections import deque
from dataclasses import is_dataclass, asdict
from typing import Optional, Dict, Any, Deque

from quentin.bootstrap.container import Container
from quentin.cognitive.loop import CognitiveTask
from quentin.traces.core import JsonlTraceRecorder, TraceEventType, new_trace_event
from quentin.runtime.task_queue import TaskQueue, TaskQueueItem
from quentin.runtime.task_sources import run_task_sources_once
from quentin.runtime.system_events import SystemEventQueue
from quentin.runtime.cron_runner import CronRunner, CronRunnerConfig
from quentin.blueprint.auto_patcher import BlueprintGapAutoPatcher
from meta_agent.patchflow.orchestrator import PatchFlowOrchestrator
from quentin.observability.service import ObservabilityService
from quentin.infra.concurrency.session_registry import SessionRegistry
from quentin.infra.sessions.session_store import SessionStore
from quentin.governance.error_budget import ErrorBudgetController
from quentin.config.feature_flags import feature_flags as q_feature_flags


logger = logging.getLogger(__name__)


@dataclass
class BrainDaemonConfig:
    session_id: str = "brain"
    domain: str = "core"
    environment: str = "sandbox"
    sleep_seconds: float = 1.0
    run_sleep_loop: bool = True
    run_immune_loop: bool = True
    run_patchflow: bool = False
    run_task_sources: bool = False
    task_sources_every_sec: float = 60.0
    run_blueprint_autopatch: bool = False
    blueprint_autopatch_every_sec: float = 300.0
    run_cron_runner: bool = True
    cron_runner_every_sec: float = 15.0
    cron_runner_max_tasks_per_tick: int = 20
    cron_runner_auto_assign_pending: bool = True


class BrainDaemon:
    """
    Minimal "brain runs itself" loop:
    - Pulls an input task (currently: single provided text)
    - Runs CognitiveLoop
    - Optionally runs SleepLoop + ImmuneLoop

    Default behavior remains offline-friendly when `LLM_STUB=1`.
    """

    def __init__(self, *, config: Optional[BrainDaemonConfig] = None, container: Optional[Container] = None) -> None:
        self.config = config or BrainDaemonConfig()
        self.container = container or Container()
        self.repo_root = Path(".").resolve()
        self.trace = JsonlTraceRecorder(repo_root=str(getattr(self.container, "settings", None).repo_root if hasattr(getattr(self.container, "settings", None), "repo_root") else "."))
        self.task_queue = TaskQueue(repo_root=".")
        self.system_event_queue = SystemEventQueue(repo_root=".")
        self.session_registry = SessionRegistry(repo_root=".")
        self.session_store = SessionStore(repo_root=".")
        self.patchflow = PatchFlowOrchestrator()
        self.error_budget = ErrorBudgetController()
        self._last_task_sources_at = 0.0
        self._last_blueprint_autopatch_at = 0.0
        self._last_cron_runner_at = 0.0
        self._guardrail_until = 0.0
        self._recover_task_sources_until = 0.0
        self._recover_patchflow_until = 0.0
        self._guardrail_tuning = {
            "cooldown_mult": 1.0,
            "recover_task_sources_mult": 1.0,
            "recover_patchflow_mult": 1.0,
        }
        self._recovery_outcomes: Deque[bool] = deque(maxlen=8)
        self._intelligence_recovery_outcomes: Deque[bool] = deque(maxlen=12)
        self._tuning_history: Deque[Dict[str, Any]] = deque(maxlen=20)
        self._last_tuning_adjustment: Dict[str, Any] = {}
        self._tuning_adjustment_count = 0
        self._last_tuning_summary_at_count = 0
        self._tuning_summary_worsening_streak = 0
        self._intelligence_strict_until = 0.0
        self._intelligence_strict_reasons: Deque[str] = deque(maxlen=12)
        self._last_intelligence_eval_at = 0.0
        self._done_council_strict_baseline = str(os.getenv("QUENTIN_DONE_COUNCIL_STRICT_REASONING", "") or "")
        self._done_council_strict_reasons_baseline = str(os.getenv("QUENTIN_DONE_COUNCIL_STRICT_REASONS", "") or "")
        self._guardrail_state_path = self._resolve_guardrail_state_path()
        self._load_guardrail_state()
        self._sync_done_council_strict_env(now=time.time())
        self.cron_runner = CronRunner(
            CronRunnerConfig(
                repo_root=".",
                tick_seconds=max(0.2, float(self.config.cron_runner_every_sec or 15.0)),
                max_tasks_per_tick=max(1, int(self.config.cron_runner_max_tasks_per_tick or 20)),
                reconcile_assignments=True,
                auto_assign_pending=bool(self.config.cron_runner_auto_assign_pending),
            )
        )

    def run_once(self, *, input_text: str, metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        meta = metadata or {}
        trace_id = f"brain::{int(time.time()*1000)}"
        
        from quentin.runtime.tenant_context import TenantContext
        
        tenant_id = meta.get("tenant_id") or "brain_system"
        session_id = meta.get("session_id") or self.config.session_id or "brain"
        
        context = TenantContext(
            tenant_id=tenant_id,
            session_id=session_id,
            domain=self.config.domain,
            metadata=meta
        )

        try:
            self.trace.record_event(
                new_trace_event(
                    trace_id=trace_id,
                    event_type=TraceEventType.DECISION,
                    payload={"action": "brain_cycle_start", **context.to_dict()},
                )
            )
        except Exception:
            pass

        task = CognitiveTask(
            input_text=input_text,
            domain=self.config.domain,
            environment=self.config.environment,
            metadata={**context.to_dict()},
        )
        session_key = str((task.metadata or {}).get("session_id") or self.config.session_id or "brain")
        from quentin.infra.concurrency.lanes import LANE_MAIN, LANE_MAINTENANCE
        session_state = self.session_store.load_or_create(session_key, metadata={"source": "brain_daemon"})
        
        # P2-D: Separate global lanes for maintenance vs interaction (OpenClaw inspired)
        global_lane = LANE_MAIN
        if task.domain == "maintenance" or (task.metadata or {}).get("kind") == "self_awareness_recovery":
            global_lane = LANE_MAINTENANCE
            
        # P5-A: SLO Degradation
        if q_feature_flags.slo_governance_v1 and self.error_budget.is_degradation_required():
            degrade_config = self.error_budget.get_degradation_mode()
            if task.domain == "maintenance" and degrade_config.get("disable_high_risk_evolution"):
                 logger.info("BrainDaemon: Skipping maintenance task due to error budget exhaustion.")
                 return {"status": "degraded", "reason": "error_budget_exhausted"}

        # Preserve previous global lane semantics via tenant_id while session lane/abort/lock are owned by SessionState.
        tenant_id = "brain_maintenance" if global_lane == LANE_MAINTENANCE else "brain_main"
        loop_obj = self.container.cognitive_loop
        run_async = getattr(loop_obj, "run_task_async", None)
        run_sync = getattr(loop_obj, "run_task", None)
        if callable(run_async):
            # Avoid nested lane/session orchestration deadlocks: run_task_async already
            # routes through session-aware lane orchestration internally.
            result = asyncio.run(run_async(task))
        elif callable(run_sync):
            from quentin.infra.concurrency.lane_orchestrator import lane_orchestrator
            result = lane_orchestrator.run_sync_in_session(
                session_state,
                lambda: asyncio.to_thread(run_sync, task),
                session_store=self.session_store,
                tenant_id=tenant_id,
            )
        else:
            raise AttributeError("cognitive_loop missing run_task_async/run_task")

        def _jsonable(x: Any) -> Any:
            if x is None:
                return None
            if isinstance(x, (str, int, float, bool)):
                return x
            if isinstance(x, dict):
                return {str(k): _jsonable(v) for k, v in x.items()}
            if isinstance(x, list):
                return [_jsonable(v) for v in x]
            if hasattr(x, "to_dict"):
                try:
                    return _jsonable(x.to_dict())
                except Exception:
                    pass
            if is_dataclass(x):
                try:
                    return _jsonable(asdict(x))
                except Exception:
                    pass
            return {"type": x.__class__.__name__, "repr": repr(x)[:2000]}

        sleep_report = None
        if self.config.run_sleep_loop:
            try:
                sleep_report = self.container.sleep_loop.run_once()
                if inspect.isawaitable(sleep_report):
                    sleep_report = asyncio.run(sleep_report)
            except Exception:
                sleep_report = {"status": "error"}
        sleep_report = _jsonable(sleep_report)

        immune_report = None
        if self.config.run_immune_loop:
            try:
                immune_report = self.container.immune_loop.process_trace()
                if inspect.isawaitable(immune_report):
                    immune_report = asyncio.run(immune_report)
            except Exception:
                immune_report = {"status": "error"}
        immune_report = _jsonable(immune_report)

        patchflow_report = None
        if self.config.run_patchflow:
            try:
                patchflow_report = self.patchflow.run_cycle()
            except Exception as e:  # noqa: BLE001
                patchflow_report = {"status": "error", "error": repr(e)}
        patchflow_report = _jsonable(patchflow_report)

        now = time.time()
        guardrail_state = self._guardrail_state(now=now)
        out = {
            "task_id": result.task_id,
            "goal_id": result.goal_id,
            "done": result.done,
            "done_confidence": float(result.done_confidence),
            "final_output_preview": (result.final_output or "")[:800],
            "self_awareness": dict(getattr(result, "self_awareness", {}) or {}),
            "runtime_mode": guardrail_state["runtime_mode"],
            "guardrail_state": guardrail_state,
            "sleep_report": sleep_report,
            "immune_report": immune_report,
            "patchflow_report": patchflow_report,
        }
        try:
            self._apply_self_awareness_guardrails(
                self_awareness=dict(getattr(result, "self_awareness", {}) or {}),
                session_id=str((task.metadata or {}).get("session_id") or self.config.session_id),
                goal_id=str(getattr(result, "goal_id", "") or ""),
            )
        except Exception:
            pass
        try:
            self.trace.record_event(
                new_trace_event(
                    trace_id=trace_id,
                    event_type=TraceEventType.DECISION,
                    payload={"action": "brain_cycle_done", **out},
                )
            )
        except Exception:
            pass
        return out

    def run_forever(self, *, input_text: str, max_iterations: int = 0) -> None:
        i = 0
        while True:
            i += 1
            _ = self.run_once(input_text=input_text, metadata={"iter": i})
            if max_iterations and i >= max_iterations:
                break
            time.sleep(float(self.config.sleep_seconds))

    def run_queue_forever(self, *, worker_id: str, max_tasks: int = 0) -> None:
        done = 0
        while True:
            self._sync_done_council_strict_env()
            self._refresh_intelligence_autoregression_if_needed()
            self._drain_self_awareness_events_into_guardrails()
            item = self._claim_next_item(worker_id=worker_id)
            if item is None:
                now = time.time()
                # Self-directed mode: periodically populate the queue with maintenance work.
                if self.config.run_task_sources:
                    if self._can_run_task_sources(now=now) and (
                        now - float(self._last_task_sources_at or 0.0) >= float(self.config.task_sources_every_sec or 60.0)
                    ):
                        try:
                            # Fixed: run_task_sources_once is now async
                            report = asyncio.run(
                                run_task_sources_once(
                                    repo_root=".",
                                    max_blueprint_tasks=int(os.getenv("QUENTIN_TASK_SOURCE_BLUEPRINT_MAX", "25") or "25"),
                                )
                            )
                            # Sensing: record why sources produced 0 tasks vs disabled/error.
                            try:
                                sources = getattr(report, "sources", []) or []
                                src_dicts = []
                                for s in sources:
                                    if hasattr(s, "to_dict"):
                                        src_dicts.append(s.to_dict())
                                    elif isinstance(s, dict):
                                        src_dicts.append(dict(s))
                                note = "; ".join(
                                    [
                                        f"{d.get('source_id')}:{d.get('status')}:{d.get('reason')}:enq={d.get('enqueued')}:err={d.get('errors')}"
                                        for d in src_dicts
                                    ]
                                )[:2000]
                                self.system_event_queue.enqueue_event(
                                    session_id=str(self.config.session_id or "brain"),
                                    event_type="task_source_run_report",
                                    payload={
                                        "enqueued": int(getattr(report, "enqueued", 0) or 0),
                                        "skipped": int(getattr(report, "skipped", 0) or 0),
                                        "sources": src_dicts,
                                        "self_awareness_note": note,
                                    },
                                    source="brain_daemon",
                                )
                                try:
                                    self.trace.record_event(
                                        new_trace_event(
                                            trace_id=f"brain_task_sources::{int(time.time()*1000)}",
                                            event_type=TraceEventType.DECISION,
                                            payload={
                                                "action": "task_sources_run",
                                                "session_id": str(self.config.session_id or "brain"),
                                                "enqueued": int(getattr(report, "enqueued", 0) or 0),
                                                "sources": src_dicts,
                                                "self_awareness_note": note,
                                            },
                                        )
                                    )
                                except Exception:
                                    pass
                            except Exception:
                                pass
                        except Exception:
                            pass
                        self._last_task_sources_at = now
                if self.config.run_blueprint_autopatch and str(self.config.environment or "sandbox") == "sandbox":
                    if self._can_run_blueprint_autopatch(now=now) and (
                        now - float(self._last_blueprint_autopatch_at or 0.0) >= float(self.config.blueprint_autopatch_every_sec or 300.0)
                    ):
                        try:
                            max_gaps = int(os.getenv("QUENTIN_BRAIN_AUTOPATCH_MAX_GAPS", "3") or "3")
                        except Exception:
                            max_gaps = 3
                        # Use self-programming engine to propose patches; it does not auto-apply from this entrypoint.
                        try:
                            os.environ.setdefault("QUENTIN_BLUEPRINT_AUTOPATCH_MAX_GAPS", str(max_gaps))
                            autopatcher = BlueprintGapAutoPatcher(blueprint_path=os.getenv("QUENTIN_BLUEPRINT_PATH", "blueprint/spec_v3.json"))
                            _ = autopatcher.propose_patches_for_gaps(
                                status_filter=["missing", "partial"],
                                auto_eval=False,
                                run_selfprog=True,
                            )
                        except Exception:
                            pass
                        self._last_blueprint_autopatch_at = now
                
                # Phase D: Always run patchflow cycle when idle if enabled
                if self.config.run_patchflow:
                    if self._can_run_patchflow(now=now):
                        try:
                            self.patchflow.run_cycle()
                        except Exception:
                            pass
                if self.config.run_cron_runner:
                    self._run_cron_runner_if_due(now=now)

                time.sleep(float(self.config.sleep_seconds))
                continue
            ok = True
            err = ""
            try:
                _ = self.run_once(
                    input_text=item.input_text,
                    metadata={"iter": done + 1, "session_id": item.session_id, "queue_task_id": item.task_id},
                )
            except Exception as e:  # noqa: BLE001
                ok = False
                err = repr(e)
            finally:
                # Release cognitive lock for this session
                self.session_registry.release(item.session_id, worker_id)

            self.task_queue.mark_done(item.task_id, ok=ok, error=err)
            try:
                from quentin.tools.execution_parity import nodes_tool

                _ = nodes_tool(
                    {
                        "action": "release_task",
                        "task_id": str(item.task_id or ""),
                        "final_status": "done" if ok else "failed",
                        "release_reason": "brain_daemon_task_done",
                        "source": "brain_daemon",
                    },
                    {"repo_root": "."},
                )
            except Exception:
                pass
            try:
                kind = str((item.metadata or {}).get("kind") or "")
                if kind == "self_awareness_recovery":
                    self._update_guardrail_tuning_from_recovery_outcome(ok=ok)
                if kind == "intelligence_regression_recovery":
                    self._record_intelligence_recovery_outcome(
                        ok=ok,
                        task_id=str(item.task_id or ""),
                        reason_key=str((item.metadata or {}).get("reason_key") or ""),
                    )
            except Exception:
                pass
            done += 1
            if max_tasks and done >= max_tasks:
                break

    def _claim_next_item(self, *, worker_id: str) -> Optional[TaskQueueItem]:
        now = time.time()
        mode = self._runtime_mode(now=now)
        if mode == "normal":
            return self.task_queue.claim_next(worker_id=worker_id)

        # Guardrail active:
        # 1) Preempt self-awareness recovery tasks.
        # 2) Defer higher-risk maintenance tasks (blueprint/patchflow backlog).
        try:
            items = self.task_queue.load_all(limit=5000)
        except Exception:
            return self.task_queue.claim_next(worker_id=worker_id)
        pending = [it for it in items if str(getattr(it, "status", "")) == "pending"]
        if not pending:
            return None
        pending.sort(key=lambda x: (-int(getattr(x, "priority", 0) or 0), str(getattr(x, "created_at", "") or "")))

        def _kind(it: TaskQueueItem) -> str:
            md = dict(getattr(it, "metadata", {}) or {})
            return str(md.get("kind") or "").strip()

        def _is_high_risk(it: TaskQueueItem) -> bool:
            md = dict(getattr(it, "metadata", {}) or {})
            risk = str(md.get("risk_level") or "").strip().lower()
            return risk in {"high", "critical"}

        for it in pending:
            # P5: Cognitive Consistency - Check if session is already being processed by another worker
            if self.session_registry.is_active(it.session_id):
                continue

            if _kind(it) == "self_awareness_recovery":
                if self.session_registry.acquire(it.session_id, worker_id):
                    claimed = self.task_queue.claim_by_id(task_id=it.task_id, worker_id=worker_id)
                    if claimed is not None:
                        return claimed
                    self.session_registry.release(it.session_id, worker_id)

        blocked_kinds = {"blueprint_gap", "patchflow_backlog"}
        for it in pending:
            # P5: Skip active sessions
            if self.session_registry.is_active(it.session_id):
                continue

            if _kind(it) in blocked_kinds:
                continue
            if _is_high_risk(it):
                continue
            
            if self.session_registry.acquire(it.session_id, worker_id):
                claimed = self.task_queue.claim_by_id(task_id=it.task_id, worker_id=worker_id)
                if claimed is not None:
                    return claimed
                self.session_registry.release(it.session_id, worker_id)

        return None

    def _runtime_mode(self, *, now: Optional[float] = None) -> str:
        ts = float(now if now is not None else time.time())
        if ts < float(self._guardrail_until or 0.0):
            return "guardrail"
        if ts < float(self._intelligence_strict_until or 0.0):
            return "intelligence_strict"
        if ts < float(self._recover_task_sources_until or 0.0):
            return "recover_task_sources"
        if ts < float(self._recover_patchflow_until or 0.0):
            return "recover_patchflow"
        return "normal"

    def _guardrail_state(self, *, now: Optional[float] = None) -> Dict[str, Any]:
        ts = float(now if now is not None else time.time())
        mode = self._runtime_mode(now=ts)
        guardrail_remaining_sec = max(0.0, float(self._guardrail_until or 0.0) - ts)
        recover_task_sources_remaining_sec = max(0.0, float(self._recover_task_sources_until or 0.0) - ts)
        recover_patchflow_remaining_sec = max(0.0, float(self._recover_patchflow_until or 0.0) - ts)
        intelligence_strict_remaining_sec = max(0.0, float(self._intelligence_strict_until or 0.0) - ts)
        return {
            "runtime_mode": mode,
            "guardrail_until": float(self._guardrail_until or 0.0),
            "intelligence_strict_until": float(self._intelligence_strict_until or 0.0),
            "recover_task_sources_until": float(self._recover_task_sources_until or 0.0),
            "recover_patchflow_until": float(self._recover_patchflow_until or 0.0),
            "guardrail_remaining_sec": guardrail_remaining_sec,
            "intelligence_strict_remaining_sec": intelligence_strict_remaining_sec,
            "recover_task_sources_remaining_sec": recover_task_sources_remaining_sec,
            "recover_patchflow_remaining_sec": recover_patchflow_remaining_sec,
            "intelligence_strict_reasons": list(self._intelligence_strict_reasons),
            "last_intelligence_eval_at": float(self._last_intelligence_eval_at or 0.0),
            "can_run_task_sources": self._can_run_task_sources(now=ts),
            "can_run_patchflow": self._can_run_patchflow(now=ts),
            "can_run_blueprint_autopatch": self._can_run_blueprint_autopatch(now=ts),
            "tuning": dict(self._guardrail_tuning),
            "recovery_success_rate": self._recovery_success_rate(),
            "intelligence_recovery_success_rate": self._intelligence_recovery_success_rate(),
            "intelligence_recovery_outcomes_tail": list(self._intelligence_recovery_outcomes)[-8:],
            "last_tuning_adjustment": dict(self._last_tuning_adjustment or {}),
            "tuning_history_tail": list(self._tuning_history)[-5:],
            "tuning_adjustment_count": int(self._tuning_adjustment_count or 0),
            "last_tuning_summary_at_count": int(self._last_tuning_summary_at_count or 0),
            "tuning_summary_worsening_streak": int(self._tuning_summary_worsening_streak or 0),
        }

    def _can_run_task_sources(self, *, now: Optional[float] = None) -> bool:
        mode = self._runtime_mode(now=now)
        return mode in {"recover_task_sources", "recover_patchflow", "normal"}

    def _can_run_patchflow(self, *, now: Optional[float] = None) -> bool:
        mode = self._runtime_mode(now=now)
        return mode in {"recover_patchflow", "normal"}

    def _can_run_cron_runner(self, *, now: Optional[float] = None) -> bool:
        _ = now
        return bool(self.config.run_cron_runner)

    def _run_cron_runner_if_due(self, *, now: Optional[float] = None) -> None:
        ts = float(now if now is not None else time.time())
        if not self._can_run_cron_runner(now=ts):
            return
        if ts - float(self._last_cron_runner_at or 0.0) < max(0.2, float(self.config.cron_runner_every_sec or 15.0)):
            return
        try:
            report = self.cron_runner.run_once()
        except Exception as e:  # noqa: BLE001
            report = {"status": "error", "error": repr(e)}
        self._last_cron_runner_at = ts
        try:
            self.system_event_queue.enqueue_event(
                session_id=str(self.config.session_id or "brain"),
                event_type="cron_runner_tick",
                payload={"report": report},
                source="brain_daemon",
            )
        except Exception:
            pass
        try:
            self.trace.record_event(
                new_trace_event(
                    trace_id=f"brain_cron_runner::{int(ts*1000)}",
                    event_type=TraceEventType.DECISION,
                    payload={
                        "action": "cron_runner_tick",
                        "session_id": str(self.config.session_id or "brain"),
                        "report": report,
                    },
                )
            )
        except Exception:
            pass

    def _can_run_blueprint_autopatch(self, *, now: Optional[float] = None) -> bool:
        return self._runtime_mode(now=now) == "normal"

    def _drain_self_awareness_events_into_guardrails(self) -> None:
        try:
            events = self.system_event_queue.drain_events(session_id=self.config.session_id, limit=20)
            events += self.system_event_queue.drain_events(session_id="global", limit=20)
        except Exception:
            return
        kept: list[Any] = []
        for e in events:
            if str(getattr(e, "event_type", "") or "") == "self_awareness_alert":
                payload = dict(getattr(e, "payload", {}) or {})
                self._apply_self_awareness_guardrails(
                    self_awareness=payload,
                    session_id=str(getattr(e, "session_id", "") or self.config.session_id),
                    goal_id=str(payload.get("goal_id") or ""),
                )
            else:
                kept.append(e)
        for e in kept:
            try:
                self.system_event_queue.enqueue_event(
                    session_id=str(getattr(e, "session_id", "") or "global"),
                    event_type=str(getattr(e, "event_type", "") or "system_event"),
                    payload=dict(getattr(e, "payload", {}) or {}),
                    source=str(getattr(e, "source", "") or ""),
                )
            except Exception:
                pass

    def _apply_self_awareness_guardrails(
        self,
        *,
        self_awareness: Dict[str, Any],
        session_id: str,
        goal_id: str,
    ) -> None:
        status = str(self_awareness.get("status") or "").strip().lower()
        if status not in {"warning", "critical"}:
            return
        cooldown = float(os.getenv("QUENTIN_BRAIN_GUARDRAIL_COOLDOWN_SEC", "180") or "180")
        if status == "critical":
            cooldown = max(cooldown, 300.0)
        cooldown *= float(self._guardrail_tuning.get("cooldown_mult", 1.0) or 1.0)
        now = time.time()
        self._guardrail_until = max(float(self._guardrail_until or 0.0), now + cooldown)
        rec_task_sources = float(os.getenv("QUENTIN_BRAIN_RECOVER_TASK_SOURCES_SEC", "60") or "60")
        rec_patchflow = float(os.getenv("QUENTIN_BRAIN_RECOVER_PATCHFLOW_SEC", "120") or "120")
        rec_task_sources *= float(self._guardrail_tuning.get("recover_task_sources_mult", 1.0) or 1.0)
        rec_patchflow *= float(self._guardrail_tuning.get("recover_patchflow_mult", 1.0) or 1.0)
        self._recover_task_sources_until = max(
            float(self._recover_task_sources_until or 0.0),
            float(self._guardrail_until or 0.0) + max(0.0, rec_task_sources),
        )
        self._recover_patchflow_until = max(
            float(self._recover_patchflow_until or 0.0),
            float(self._recover_task_sources_until or 0.0) + max(0.0, rec_patchflow),
        )

        reason = str(self_awareness.get("anti_pattern_reason") or self_awareness.get("failover_reason") or "").strip()
        suggested_actions = self_awareness.get("suggested_actions")
        if not isinstance(suggested_actions, list):
            suggested_actions = []

        md = {
            "source": "brain_daemon_guardrail",
            "kind": "self_awareness_recovery",
            "goal_id": goal_id,
            "status": status,
            "reason": reason,
        }
        exists = False
        try:
            for it in self.task_queue.load_all(limit=5000):
                meta = dict(getattr(it, "metadata", {}) or {})
                if meta.get("kind") == "self_awareness_recovery" and meta.get("goal_id") == goal_id and str(getattr(it, "status", "")) in {"pending", "claimed"}:
                    exists = True
                    break
        except Exception:
            exists = False
        if not exists:
            self.task_queue.append(
                TaskQueueItem.new(
                    input_text=(
                        "[maintenance] Self-awareness recovery: switch to non-interactive fs workflow, "
                        "summarize progress, and avoid repeated failing tool patterns."
                    ),
                    domain="core",
                    environment="sandbox",
                    session_id=str(session_id or self.config.session_id),
                    priority=9 if status == "critical" else 7,
                    metadata={
                        **md,
                        "suggested_actions": list(suggested_actions)[:6],
                    },
                )
            )
        try:
            self.system_event_queue.enqueue_event(
                session_id=str(session_id or self.config.session_id),
                event_type="brain_guardrail_activated",
                payload={
                    "goal_id": goal_id,
                    "status": status,
                    "reason": reason,
                    "guardrail_until": self._guardrail_until,
                    "runtime_mode": self._runtime_mode(),
                    "guardrail_state": self._guardrail_state(),
                },
                source="brain_daemon",
            )
        except Exception:
            pass
        self._save_guardrail_state()

    def _recovery_success_rate(self) -> float:
        if not self._recovery_outcomes:
            return 0.0
        ok = sum(1 for v in self._recovery_outcomes if v)
        return float(ok) / float(len(self._recovery_outcomes))

    def _intelligence_recovery_success_rate(self) -> float:
        if not self._intelligence_recovery_outcomes:
            return 0.0
        ok = sum(1 for v in self._intelligence_recovery_outcomes if v)
        return float(ok) / float(len(self._intelligence_recovery_outcomes))

    def _update_guardrail_tuning_from_recovery_outcome(self, *, ok: bool) -> None:
        self._recovery_outcomes.append(bool(ok))
        up = float(os.getenv("QUENTIN_BRAIN_GUARDRAIL_TUNE_UP", "1.2") or "1.2")
        down = float(os.getenv("QUENTIN_BRAIN_GUARDRAIL_TUNE_DOWN", "0.9") or "0.9")
        min_mult = float(os.getenv("QUENTIN_BRAIN_GUARDRAIL_TUNE_MIN", "0.5") or "0.5")
        max_mult = float(os.getenv("QUENTIN_BRAIN_GUARDRAIL_TUNE_MAX", "3.0") or "3.0")

        recent = list(self._recovery_outcomes)
        success_rate = self._recovery_success_rate()
        fail_streak = 0
        for v in reversed(recent):
            if v:
                break
            fail_streak += 1

        factor = 1.0
        trigger_reason = ""
        if fail_streak >= 2 or (len(recent) >= 4 and success_rate < 0.5):
            factor = up
            trigger_reason = "fail_streak" if fail_streak >= 2 else "low_success_rate"
        elif len(recent) >= 4 and success_rate >= 0.6:
            factor = down
            trigger_reason = "high_success_rate"
        if factor == 1.0:
            return

        before = dict(self._guardrail_tuning)
        for key in ("cooldown_mult", "recover_task_sources_mult", "recover_patchflow_mult"):
            current = float(self._guardrail_tuning.get(key, 1.0) or 1.0)
            next_v = current * factor
            if next_v < min_mult:
                next_v = min_mult
            if next_v > max_mult:
                next_v = max_mult
            self._guardrail_tuning[key] = next_v

        adjustment = {
            "timestamp": time.time(),
            "outcome_ok": bool(ok),
            "trigger_reason": trigger_reason,
            "factor": float(factor),
            "success_rate": float(success_rate),
            "fail_streak": int(fail_streak),
            "before": before,
            "after": dict(self._guardrail_tuning),
        }
        self._last_tuning_adjustment = adjustment
        self._tuning_history.append(adjustment)
        self._tuning_adjustment_count = int(self._tuning_adjustment_count or 0) + 1
        self._emit_guardrail_tuning_event(adjustment)
        self._emit_guardrail_tuning_summary_if_needed()
        self._save_guardrail_state()

    def _emit_guardrail_tuning_event(self, adjustment: Dict[str, Any]) -> None:
        try:
            self.system_event_queue.enqueue_event(
                session_id=str(self.config.session_id or "brain"),
                event_type="brain_guardrail_tuned",
                payload=dict(adjustment or {}),
                source="brain_daemon",
            )
        except Exception:
            pass

    def _emit_guardrail_tuning_summary_if_needed(self) -> None:
        every = int(os.getenv("QUENTIN_BRAIN_GUARDRAIL_TUNE_SUMMARY_EVERY", "5") or "5")
        if every <= 0:
            return
        count = int(self._tuning_adjustment_count or 0)
        if count <= 0 or (count % every) != 0:
            return
        if count == int(self._last_tuning_summary_at_count or 0):
            return

        tail = list(self._tuning_history)[-every:]
        if not tail:
            return
        reason_counts: Dict[str, int] = {}
        factors: list[float] = []
        for item in tail:
            reason = str(item.get("trigger_reason") or "unknown")
            reason_counts[reason] = int(reason_counts.get(reason, 0)) + 1
            try:
                factors.append(float(item.get("factor") or 1.0))
            except Exception:
                pass
        avg_factor = (sum(factors) / len(factors)) if factors else 1.0
        payload = {
            "window_size": int(len(tail)),
            "tuning_adjustment_count": count,
            "avg_factor": float(avg_factor),
            "reason_counts": reason_counts,
            "recovery_success_rate": float(self._recovery_success_rate()),
            "current_tuning": dict(self._guardrail_tuning),
        }
        try:
            self.system_event_queue.enqueue_event(
                session_id=str(self.config.session_id or "brain"),
                event_type="brain_guardrail_tuning_summary",
                payload=payload,
                source="brain_daemon",
            )
            self._last_tuning_summary_at_count = count
        except Exception:
            pass
        self._apply_tuning_summary_intelligence_escalation(payload)

    def _apply_tuning_summary_intelligence_escalation(self, payload: Dict[str, Any]) -> None:
        reason_counts = payload.get("reason_counts") if isinstance(payload.get("reason_counts"), dict) else {}
        fail_reasons = int(reason_counts.get("fail_streak", 0) or 0) + int(reason_counts.get("low_success_rate", 0) or 0)
        avg_factor = float(payload.get("avg_factor") or 1.0)
        factor_warn = float(os.getenv("QUENTIN_BRAIN_GUARDRAIL_TUNE_FACTOR_WARN", "1.05") or "1.05")
        fail_count_warn = int(os.getenv("QUENTIN_BRAIN_GUARDRAIL_TUNE_FAIL_REASON_WARN", "1") or "1")
        worsening = avg_factor >= factor_warn and fail_reasons >= max(1, fail_count_warn)

        prev_streak = int(self._tuning_summary_worsening_streak or 0)
        self._tuning_summary_worsening_streak = (prev_streak + 1) if worsening else 0

        if self._tuning_summary_worsening_streak != prev_streak:
            self._save_guardrail_state()
        min_streak = int(os.getenv("QUENTIN_BRAIN_GUARDRAIL_TUNE_WORSENING_STREAK", "2") or "2")
        if self._tuning_summary_worsening_streak < max(1, min_streak):
            return

        now = time.time()
        strict_sec = float(os.getenv("QUENTIN_BRAIN_GUARDRAIL_TUNE_STRICT_SEC", "120") or "120")
        strict_sec = max(30.0, strict_sec)
        was_active = now < float(self._intelligence_strict_until or 0.0)
        old_until = float(self._intelligence_strict_until or 0.0)
        self._intelligence_strict_until = max(old_until, now + strict_sec)
        if "guardrail_tuning_summary_worsening" not in self._intelligence_strict_reasons:
            self._intelligence_strict_reasons.append("guardrail_tuning_summary_worsening")
        self._sync_done_council_strict_env(now=now)

        if self._intelligence_strict_until > old_until + 0.01:
            try:
                self.system_event_queue.enqueue_event(
                    session_id=str(self.config.session_id or "brain"),
                    event_type="brain_intelligence_strict_mode_changed",
                    payload={
                        "enabled": True,
                        "reasons": list(self._intelligence_strict_reasons),
                        "strict_until": float(self._intelligence_strict_until or 0.0),
                        "trigger": "guardrail_tuning_summary",
                        "worsening_streak": int(self._tuning_summary_worsening_streak or 0),
                        "already_active": bool(was_active),
                    },
                    source="brain_daemon",
                )
            except Exception:
                pass
            self._save_guardrail_state()

    def _resolve_guardrail_state_path(self) -> Path:
        override = str(os.getenv("QUENTIN_BRAIN_GUARDRAIL_STATE_PATH", "") or "").strip()
        if override:
            p = Path(override).expanduser()
            if not p.is_absolute():
                p = (self.repo_root / p).resolve()
            p.parent.mkdir(parents=True, exist_ok=True)
            return p
        p = (self.repo_root / "data" / "runtime" / "brain_guardrail_state.json").resolve()
        p.parent.mkdir(parents=True, exist_ok=True)
        return p

    def _load_guardrail_state(self) -> None:
        p = self._guardrail_state_path
        if not p.exists():
            return
        try:
            raw = json.loads(p.read_text(encoding="utf-8") or "{}")
        except Exception:
            return
        if not isinstance(raw, dict):
            return
        tuning = raw.get("tuning")
        if isinstance(tuning, dict):
            for k in ("cooldown_mult", "recover_task_sources_mult", "recover_patchflow_mult"):
                try:
                    v = float(tuning.get(k, self._guardrail_tuning.get(k, 1.0)))
                    self._guardrail_tuning[k] = v
                except Exception:
                    pass
        outcomes = raw.get("recovery_outcomes")
        if isinstance(outcomes, list):
            vals = [bool(x) for x in outcomes][-8:]
            self._recovery_outcomes = deque(vals, maxlen=8)
        intel_outcomes = raw.get("intelligence_recovery_outcomes")
        if isinstance(intel_outcomes, list):
            vals = [bool(x) for x in intel_outcomes][-12:]
            self._intelligence_recovery_outcomes = deque(vals, maxlen=12)
        history = raw.get("tuning_history")
        if isinstance(history, list):
            items: list[Dict[str, Any]] = []
            for h in history[-20:]:
                if isinstance(h, dict):
                    items.append(dict(h))
            self._tuning_history = deque(items, maxlen=20)
        last_adj = raw.get("last_tuning_adjustment")
        if isinstance(last_adj, dict):
            self._last_tuning_adjustment = dict(last_adj)
        try:
            self._tuning_adjustment_count = int(raw.get("tuning_adjustment_count") or 0)
        except Exception:
            self._tuning_adjustment_count = 0
        try:
            self._last_tuning_summary_at_count = int(raw.get("last_tuning_summary_at_count") or 0)
        except Exception:
            self._last_tuning_summary_at_count = 0
        try:
            self._tuning_summary_worsening_streak = int(raw.get("tuning_summary_worsening_streak") or 0)
        except Exception:
            self._tuning_summary_worsening_streak = 0
        try:
            self._intelligence_strict_until = float(raw.get("intelligence_strict_until") or 0.0)
        except Exception:
            self._intelligence_strict_until = 0.0
        reasons = raw.get("intelligence_strict_reasons")
        if isinstance(reasons, list):
            vals = [str(x).strip() for x in reasons if str(x).strip()]
            self._intelligence_strict_reasons = deque(vals[-12:], maxlen=12)
        try:
            self._last_intelligence_eval_at = float(raw.get("last_intelligence_eval_at") or 0.0)
        except Exception:
            self._last_intelligence_eval_at = 0.0

    def _save_guardrail_state(self) -> None:
        p = self._guardrail_state_path
        data = {
            "tuning": dict(self._guardrail_tuning),
            "recovery_outcomes": list(self._recovery_outcomes),
            "intelligence_recovery_outcomes": list(self._intelligence_recovery_outcomes),
            "tuning_history": list(self._tuning_history),
            "last_tuning_adjustment": dict(self._last_tuning_adjustment or {}),
            "tuning_adjustment_count": int(self._tuning_adjustment_count or 0),
            "last_tuning_summary_at_count": int(self._last_tuning_summary_at_count or 0),
            "tuning_summary_worsening_streak": int(self._tuning_summary_worsening_streak or 0),
            "intelligence_strict_until": float(self._intelligence_strict_until or 0.0),
            "intelligence_strict_reasons": list(self._intelligence_strict_reasons),
            "last_intelligence_eval_at": float(self._last_intelligence_eval_at or 0.0),
            "updated_at": time.time(),
        }
        try:
            tmp = p.with_suffix(".tmp")
            tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            tmp.replace(p)
        except Exception:
            pass

    def _refresh_intelligence_autoregression_if_needed(self) -> None:
        now = time.time()
        interval = float(os.getenv("QUENTIN_BRAIN_INTELLIGENCE_EVERY_SEC", "45") or "45")
        interval = max(0.0, interval)
        if interval > 0.0 and (now - float(self._last_intelligence_eval_at or 0.0) < interval):
            self._sync_done_council_strict_env(now=now)
            return
        self._last_intelligence_eval_at = now

        overview = self._load_observability_overview()
        if not isinstance(overview, dict):
            self._sync_done_council_strict_env(now=now)
            return
        intel = overview.get("intelligence")
        if not isinstance(intel, dict):
            self._sync_done_council_strict_env(now=now)
            return

        planner = intel.get("planner_repairs") if isinstance(intel.get("planner_repairs"), dict) else {}
        blocked = intel.get("blocked_action_recurrence") if isinstance(intel.get("blocked_action_recurrence"), dict) else {}
        done_q = intel.get("done_council_quality") if isinstance(intel.get("done_council_quality"), dict) else {}

        triggered: list[str] = []
        planner_rate = float(planner.get("repair_rate") or 0.0)
        if planner_rate >= float(os.getenv("QUENTIN_BRAIN_INTELLIGENCE_PLANNER_REPAIR_WARN", "0.45") or "0.45"):
            triggered.append("planner_repair_rate_high")

        blocked_repeat = float(blocked.get("repeat_ratio") or 0.0)
        if blocked_repeat >= float(os.getenv("QUENTIN_BRAIN_INTELLIGENCE_BLOCKED_REPEAT_WARN", "0.30") or "0.30"):
            triggered.append("blocked_action_repeat_high")

        discovery_precheck = planner.get("discovery_precheck") if isinstance(planner.get("discovery_precheck"), dict) else {}
        discovery_compliance = float(discovery_precheck.get("compliance_rate") or 0.0)
        if discovery_compliance < float(os.getenv("QUENTIN_BRAIN_INTELLIGENCE_DISCOVERY_COMPLIANCE_WARN", "0.80") or "0.80"):
            triggered.append("discovery_precheck_compliance_low")

        weak_resolution_rate = done_q.get("weak_resolution_rate")
        if weak_resolution_rate is not None:
            try:
                weak_v = float(weak_resolution_rate)
                if weak_v < float(os.getenv("QUENTIN_BRAIN_INTELLIGENCE_DONE_WEAK_RESOLUTION_WARN", "0.50") or "0.50"):
                    triggered.append("done_weak_resolution_low")
            except Exception:
                pass

        was_active = now < float(self._intelligence_strict_until or 0.0)
        if triggered:
            strict_sec = float(os.getenv("QUENTIN_BRAIN_INTELLIGENCE_STRICT_SEC", "180") or "180")
            self._intelligence_strict_until = max(float(self._intelligence_strict_until or 0.0), now + max(30.0, strict_sec))
            self._intelligence_strict_reasons = deque(sorted(set(triggered)), maxlen=12)
            self._enqueue_intelligence_recovery_task(
                reasons=list(self._intelligence_strict_reasons),
                intelligence=intel,
            )
            if not was_active:
                try:
                    self.system_event_queue.enqueue_event(
                        session_id=str(self.config.session_id or "brain"),
                        event_type="brain_intelligence_strict_mode_changed",
                        payload={
                            "enabled": True,
                            "reasons": list(self._intelligence_strict_reasons),
                            "strict_until": float(self._intelligence_strict_until or 0.0),
                        },
                        source="brain_daemon",
                    )
                except Exception:
                    pass
            self._save_guardrail_state()
        elif not was_active and self._intelligence_strict_reasons:
            self._intelligence_strict_reasons.clear()
            self._save_guardrail_state()

        self._sync_done_council_strict_env(now=now)

    def _enqueue_intelligence_recovery_task(self, *, reasons: list[str], intelligence: Dict[str, Any]) -> None:
        reasons = [str(x).strip() for x in (reasons or []) if str(x).strip()]
        if not reasons:
            return
        reason_key = "|".join(sorted(reasons))
        try:
            for it in self.task_queue.load_all(limit=5000):
                meta = dict(getattr(it, "metadata", {}) or {})
                if (
                    meta.get("kind") == "intelligence_regression_recovery"
                    and meta.get("reason_key") == reason_key
                    and str(getattr(it, "status", "")) in {"pending", "claimed"}
                ):
                    return
        except Exception:
            pass

        blocked_top = []
        try:
            blocked = intelligence.get("blocked_action_recurrence") if isinstance(intelligence.get("blocked_action_recurrence"), dict) else {}
            top = blocked.get("top_actions") if isinstance(blocked.get("top_actions"), list) else []
            blocked_top = [str((x or {}).get("action") or "") for x in top[:3] if isinstance(x, dict)]
        except Exception:
            blocked_top = []
        blocked_line = ", ".join([x for x in blocked_top if x]) if blocked_top else "none"
        focus = self._classify_intelligence_recovery_focus(reasons=reasons)
        focused_lines = self._build_intelligence_recovery_template_lines(
            reasons=reasons,
            blocked_top=blocked_top,
        )
        recover_prompt = (
            "[maintenance] Intelligence regression recovery task.\n"
            "Requirements:\n"
            "1) First perform environment discovery (`ls`, `which`, `find`, `cat`/`fs.read_file`) before any risky action.\n"
            "2) Use only non-interactive tools; do not use editor TTY commands.\n"
            "3) Decompose into at least 3 steps: discovery -> targeted change -> verification summary.\n"
            "4) If blocked actions recur, explicitly avoid them and use fs/shell non-interactive alternatives.\n"
            f"5) Recovery focus: {focus}.\n"
            "Focused actions:\n"
            f"{focused_lines}\n"
            f"Regression reasons: {', '.join(reasons)}.\n"
            f"Top blocked actions: {blocked_line}."
        )
        try:
            self.task_queue.append(
                TaskQueueItem.new(
                    input_text=recover_prompt,
                    domain="core",
                    environment="sandbox",
                    session_id=str(self.config.session_id or "brain"),
                    priority=8,
                    metadata={
                        "source": "brain_daemon_intelligence_guardrail",
                        "kind": "intelligence_regression_recovery",
                        "reason_key": reason_key,
                        "reasons": reasons[:8],
                        "recovery_focus": focus,
                        "blocked_top_actions": blocked_top,
                    },
                )
            )
        except Exception:
            pass

    @staticmethod
    def _classify_intelligence_recovery_focus(*, reasons: list[str]) -> str:
        rs = {str(x).strip() for x in (reasons or []) if str(x).strip()}
        if {"planner_repair_rate_high", "discovery_precheck_compliance_low"} & rs:
            return "guessing_trap"
        if {"done_weak_resolution_low"} & rs:
            return "semantic_stagnation"
        if {"strategy_regression_detected"} & rs:
            return "strategy_regression"
        if {"blocked_action_repeat_high", "blocked_action_repeated_detected"} & rs:
            return "self_awareness_gap"
        return "general_regression"

    @staticmethod
    def _build_intelligence_recovery_template_lines(*, reasons: list[str], blocked_top: list[str]) -> str:
        rs = {str(x).strip() for x in (reasons or []) if str(x).strip()}
        lines: list[str] = []
        if {"planner_repair_rate_high", "discovery_precheck_compliance_low"} & rs:
            lines.append("- Guessing trap: add explicit probe commands before every risky change, then bind edits to discovered files only.")
        if {"done_weak_resolution_low"} & rs:
            lines.append("- Semantic stagnation: collect concrete evidence (error text, failing command, unmet criterion) and cite it in done reasoning.")
        if {"strategy_regression_detected"} & rs:
            lines.append("- Strategy regression: preserve or rebuild a multi-step plan; do not collapse to single all-in-one step.")
        if {"blocked_action_repeat_high", "blocked_action_repeated_detected"} & rs:
            blocked_line = ", ".join([str(x).strip() for x in blocked_top if str(x).strip()]) or "none"
            lines.append(f"- Self-awareness gap: blacklist repeated blocked actions this run ({blocked_line}) and choose safe alternatives.")
        if not lines:
            lines.append("- General hardening: tighten discovery, decomposition, and evidence-backed verification.")
        return "\n".join(lines)

    def _record_intelligence_recovery_outcome(self, *, ok: bool, task_id: str, reason_key: str) -> None:
        self._intelligence_recovery_outcomes.append(bool(ok))
        payload = {
            "task_id": str(task_id or ""),
            "ok": bool(ok),
            "reason_key": str(reason_key or ""),
            "success_rate": float(self._intelligence_recovery_success_rate()),
            "sample_size": int(len(self._intelligence_recovery_outcomes)),
        }
        try:
            self.system_event_queue.enqueue_event(
                session_id=str(self.config.session_id or "brain"),
                event_type="brain_intelligence_recovery_outcome",
                payload=payload,
                source="brain_daemon",
            )
        except Exception:
            pass
        self._save_guardrail_state()

    def _sync_done_council_strict_env(self, *, now: Optional[float] = None) -> None:
        ts = float(now if now is not None else time.time())
        active = ts < float(self._intelligence_strict_until or 0.0)
        key = "QUENTIN_DONE_COUNCIL_STRICT_REASONING"
        reason_key = "QUENTIN_DONE_COUNCIL_STRICT_REASONS"
        if active:
            os.environ[key] = "1"
            reasons = [str(x).strip() for x in self._intelligence_strict_reasons if str(x).strip()]
            if reasons:
                os.environ[reason_key] = ",".join(reasons)
            else:
                os.environ.pop(reason_key, None)
            return
        if self._done_council_strict_baseline.strip():
            os.environ[key] = self._done_council_strict_baseline.strip()
        else:
            os.environ.pop(key, None)
        if self._done_council_strict_reasons_baseline.strip():
            os.environ[reason_key] = self._done_council_strict_reasons_baseline.strip()
        else:
            os.environ.pop(reason_key, None)

    def _load_observability_overview(self) -> Optional[Dict[str, Any]]:
        svc: Optional[Any] = None
        try:
            svc = getattr(self.container, "observability_service", None)
        except Exception:
            svc = None
        if svc is None:
            try:
                svc = ObservabilityService(repo_root=self.repo_root)
            except Exception:
                svc = None
        if svc is None or not hasattr(svc, "get_overview"):
            return None
        try:
            out = svc.get_overview()
            if inspect.isawaitable(out):
                try:
                    out = asyncio.run(out)
                except RuntimeError:
                    loop = asyncio.new_event_loop()
                    try:
                        out = loop.run_until_complete(out)
                    finally:
                        loop.close()
            if isinstance(out, dict):
                return out
        except Exception as e:  # noqa: BLE001
            logger.debug("brain daemon observability overview unavailable: %s", e)
        return None


def brain_daemon_from_env() -> BrainDaemon:
    cfg = BrainDaemonConfig(
        session_id=os.getenv("QUENTIN_BRAIN_SESSION", "brain"),
        domain=os.getenv("QUENTIN_DOMAIN", "core"),
        environment=os.getenv("QUENTIN_ENV", "sandbox"),
        sleep_seconds=float(os.getenv("QUENTIN_BRAIN_SLEEP", "1.0")),
        run_sleep_loop=os.getenv("QUENTIN_BRAIN_RUN_SLEEP", "1").strip().lower() in ("1", "true", "yes"),
        run_immune_loop=os.getenv("QUENTIN_BRAIN_RUN_IMMUNE", "1").strip().lower() in ("1", "true", "yes"),
        run_patchflow=os.getenv("META_AGENT_PATCHFLOW_RUN", "0").strip().lower() in ("1", "true", "yes"),
        run_task_sources=os.getenv("QUENTIN_TASK_SOURCES_ENABLE", "0").strip().lower() in ("1", "true", "yes"),
        task_sources_every_sec=float(os.getenv("QUENTIN_TASK_SOURCES_EVERY_SEC", "60.0")),
        run_blueprint_autopatch=os.getenv("QUENTIN_BRAIN_RUN_BLUEPRINT_AUTOPATCH", "0").strip().lower() in ("1", "true", "yes"),
        blueprint_autopatch_every_sec=float(os.getenv("QUENTIN_BRAIN_BLUEPRINT_AUTOPATCH_EVERY_SEC", "300.0")),
    )
    return BrainDaemon(config=cfg)
