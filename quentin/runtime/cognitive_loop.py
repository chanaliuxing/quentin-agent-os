from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Dict, Optional
import uuid

from quentin.memory.models import MemoryTier
from quentin.traces.core import (
    ExecutionSummary,
    LessonsLearned,
    TraceEventType,
    new_trace_event,
)
from quentin.utils.time import now_iso


@dataclass
class TaskRequest:
    task_id: str
    description: str
    payload: Dict[str, Any]
    context: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class TaskResult:
    task_id: str
    trace_id: str
    status: str
    output: Any
    summary: ExecutionSummary
    lessons: Optional[LessonsLearned]


class CognitiveLoop:
    """
    Runtime compatibility facade.

    Canonical execution is delegated to `Container(...).cognitive_loop`.
    This module only preserves the legacy TaskRequest/TaskResult contract.
    """

    def __init__(
        self,
        *,
        trace_recorder: Any,
        memory_fabric: Any,
        critic: Any,
        runtime: Any,
        delegate_to_core: bool = True,
        core_loop: Any = None,
    ) -> None:
        self.trace_recorder = trace_recorder
        self.memory_fabric = memory_fabric
        self.critic = critic
        self.runtime = runtime
        # Kept for backward compatibility; execution is always delegated to core.
        self.delegate_to_core = bool(delegate_to_core)
        self._core_loop = core_loop

    def _resolve_core_loop(self) -> Any:
        if self._core_loop is not None:
            return self._core_loop
        from quentin.bootstrap.container import Container

        repo_root = getattr(self.runtime, "repo_root", ".")
        self._core_loop = Container(repo_root=repo_root).cognitive_loop
        return self._core_loop

    def run_task(
        self,
        description: str,
        payload: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None,
    ) -> TaskResult:
        task_id = str(uuid.uuid4())
        trace_id = f"trace-{task_id}"
        ctx = dict(context or {})
        payload_obj = dict(payload or {})

        self.trace_recorder.record_event(
            new_trace_event(
                trace_id,
                TraceEventType.TASK_RECEIVED,
                {"task_id": task_id, "description": description, "context": ctx},
            )
        )
        self.trace_recorder.record_event(
            new_trace_event(
                trace_id,
                TraceEventType.PLANNING,
                {"task_id": task_id, "note": "delegated_to_container_core_loop"},
            )
        )

        status = "success"
        lessons: Optional[LessonsLearned] = None
        output: Dict[str, Any] = {}

        try:
            if self.delegate_to_core:
                from quentin.cognitive.loop import CognitiveTask

                core_task = CognitiveTask(
                    input_text=description,
                    task_id=task_id,
                    domain=str(ctx.get("domain") or "core"),
                    environment=str(ctx.get("environment") or "sandbox"),
                    metadata={
                        **ctx,
                        "payload": payload_obj,
                        "context": ctx,
                        "session_id": str(
                            ctx.get("session_id")
                            or (payload_obj.get("session_id") if isinstance(payload_obj, dict) else "")
                            or "runtime"
                        ),
                        "source": "runtime.cognitive_loop.facade",
                    },
                )
                result = self._resolve_core_loop().run_goal(core_task)
                output = {
                    "goal_id": getattr(result, "goal_id", ""),
                    "final_output": getattr(result, "final_output", "") or "",
                    "raw_output": getattr(result, "final_output", "") or "",
                    "plan_summary": getattr(result, "plan_summary", "") or "",
                    "actions_summary": getattr(result, "actions_summary", "") or "",
                    "done": bool(getattr(result, "done", False)),
                    "done_confidence": float(getattr(result, "done_confidence", 0.0) or 0.0),
                    "raw_executor_result": getattr(result, "raw_executor_result", None),
                    "self_awareness": dict(getattr(result, "self_awareness", {}) or {}),
                }
            else:
                raw_output = self.runtime.execute_task(
                    task_id=task_id,
                    description=description,
                    payload=payload_obj,
                    context=ctx,
                    trace_id=trace_id,
                    trace_recorder=self.trace_recorder,
                )
                if isinstance(raw_output, dict):
                    output = raw_output
                else:
                    output = {"raw_output": raw_output}
                if isinstance(output, dict) and output.get("error"):
                    status = "failed"
        except Exception as e:  # noqa: BLE001
            status = "failed"
            output = {"error": repr(e)}
            self.trace_recorder.record_event(
                new_trace_event(
                    trace_id,
                    TraceEventType.ERROR,
                    {"task_id": task_id, "error": repr(e)},
                )
            )

        preview = str(output)[:400]
        summary = ExecutionSummary(
            trace_id=trace_id,
            task_id=task_id,
            status=status,
            result_preview=preview,
            meta={"description": description, "timestamp": now_iso()},
        )
        self.trace_recorder.record_summary(summary)

        try:
            critic_out = self.critic.evaluate(summary=preview, context={"trace_id": trace_id}) if self.critic else {}
            comment = str((critic_out or {}).get("comment", ""))[:1000]
            lessons = LessonsLearned(
                trace_id=trace_id,
                task_id=task_id,
                content=comment,
                tags=["runtime_facade", f"status:{status}"],
                meta={"critic_score": (critic_out or {}).get("score")},
            )
            self.trace_recorder.record_lessons(lessons)
            if self.memory_fabric is not None:
                self.memory_fabric.remember_atomic(
                    content=lessons.content,
                    source="runtime_facade",
                    tier=MemoryTier.STS,
                    importance=(critic_out or {}).get("score", 0.5),
                    tags=["reflection", str(ctx.get("domain") or "generic")],
                    metadata={"task_id": task_id, "trace_id": trace_id, "status": status},
                )
        except Exception:
            lessons = lessons

        return TaskResult(
            task_id=task_id,
            trace_id=trace_id,
            status=status,
            output=output,
            summary=summary,
            lessons=lessons,
        )
