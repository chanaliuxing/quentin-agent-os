from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional
import json
import logging
import uuid

from quentin.llm.router import ModelRouter
from quentin.council.manager import CouncilManager
from quentin.council.done import DoneCouncil, DoneDecision
from quentin.traces.execution_trace import ExecutionTrace, ExecutionTraceStore
from quentin.traces.core import TraceRecorder, JsonlTraceRecorder, TraceEventType, new_trace_event
from quentin.runtime.session_write_lock import acquire_session_write_lock
from quentin.utils.time import now_iso
from quentin.utils.time import now_utc_iso

logger = logging.getLogger(__name__)

# --- Phase 5.4: Global Serialization Guard ---
def _safe_serialize_recursive(obj: Any) -> Any:
    """
    Compatibility wrapper for historical call sites.

    NOTE: This must be cycle-safe because Goal/Done payloads may include
    deep objects and accidental circular references.
    """
    from quentin.utils.json import make_jsonable

    return make_jsonable(obj, max_depth=12, max_items=200, max_str=8000)

# ---------- Data Models ----------

@dataclass
class GoalSpec:
    goal_id: str
    title: str
    description: str
    domain: str
    environment: str
    success_criteria: List[str] = field(default_factory=list)
    hard_constraints: List[str] = field(default_factory=list)
    soft_preferences: List[str] = field(default_factory=list)
    created_by: str = "agent"
    parent_task_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=now_utc_iso)

    def to_dict(self) -> Dict[str, Any]:
        return _safe_serialize_recursive(self)

    @classmethod
    def new(cls, **kwargs) -> "GoalSpec":
        # P5: Robust Initialization - prevent crashes on missing mandatory fields
        kwargs.setdefault("goal_id", str(uuid.uuid4()))
        kwargs.setdefault("title", str(kwargs.get("description", "Unnamed Task"))[:64])
        kwargs.setdefault("domain", "core")
        kwargs.setdefault("environment", "sandbox")
        kwargs.setdefault("metadata", {})
        return cls(**kwargs)


@dataclass
class DoneCheckContext:
    task_id: str
    plan_summary: str
    actions_summary: str
    final_output: str
    metrics: Dict[str, Any] = field(default_factory=dict)
    logs_excerpt: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return _safe_serialize_recursive(self)


@dataclass
class DoneCheckResult:
    is_done: bool
    confidence: float
    reasons: List[str] = field(default_factory=list)
    violated_constraints: List[str] = field(default_factory=list)
    improvement_suggestions: List[str] = field(default_factory=list)
    raw_answer: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return _safe_serialize_recursive(self)


class GoalStore:
    def __init__(self, *, repo_root: str | Path = ".", goals_path: str | Path = "data/goals.jsonl"):
        self.repo_root = Path(repo_root).resolve()
        self.goals_path = self.repo_root / goals_path
        self.goals_path.parent.mkdir(parents=True, exist_ok=True)

    def save(self, goal: GoalSpec) -> None:
        rec = goal.to_dict()
        try:
            lock = acquire_session_write_lock(session_file=self.goals_path)
            try:
                with self.goals_path.open("a", encoding="utf-8") as f:
                    f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            finally:
                lock["release"]()
        except Exception:
            logger.exception("GoalStore.save: failed to append goal")

    def load_all(self) -> List[GoalSpec]:
        if not self.goals_path.exists():
            return []
        res: List[GoalSpec] = []
        try:
            with self.goals_path.open("r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line: continue
                    try:
                        obj = json.loads(line)
                        res.append(GoalSpec(**obj))
                    except: pass
        except Exception:
            logger.exception("GoalStore.load_all failed")
        return res

    def find_latest_by_task_id(self, task_id: str) -> Optional[GoalSpec]:
        all_goals = self.load_all()
        for goal in reversed(all_goals):
            if goal.parent_task_id == task_id:
                return goal
        return None

class GoalDoneManager:
    def __init__(
        self,
        *,
        repo_root: str | Path = ".",
        goal_store: Optional[GoalStore] = None,
        router: Optional[ModelRouter] = None,
        traces_store: Optional[ExecutionTraceStore] = None,
        domain: str = "core",
        done_council: Optional[DoneCouncil] = None,
        trace_recorder: Optional[TraceRecorder] = None,
    ) -> None:
        self.repo_root = Path(repo_root).resolve()
        self.goal_store = goal_store or GoalStore(repo_root=self.repo_root)
        self.router = router or ModelRouter()
        self.traces_store = traces_store or ExecutionTraceStore(repo_root=self.repo_root)
        self.domain = domain
        self.trace_recorder = trace_recorder or JsonlTraceRecorder(repo_root=str(self.repo_root))
        
        if done_council:
            self.council = done_council
        else:
            cm = CouncilManager(repo_root=self.repo_root, model_router=self.router)
            self.council = DoneCouncil(council_manager=cm)

    def create_and_save_goal(self, **params) -> GoalSpec:
        goal = GoalSpec.new(**params)
        self.goal_store.save(goal)
        return goal

    def get_latest_goal_for_task(self, task_id: str) -> Optional[GoalSpec]:
        return self.goal_store.find_latest_by_task_id(task_id)

    def check_done_and_record(self, *, goal: GoalSpec, context: DoneCheckContext) -> DoneCheckResult:
        exec_summary = {
             "plan_summary": context.plan_summary,
             "actions_summary": context.actions_summary,
             "final_output": context.final_output,
             "logs_excerpt": context.logs_excerpt
        }
        
        decision: DoneDecision = self.council.assess(
            goal=goal,
            execution_summary=exec_summary,
            metrics=context.metrics
        )

        final_dict = decision.raw.final if hasattr(decision.raw, "final") else {}
        violated = final_dict.get("violated_constraints") or []
        suggestions = final_dict.get("improvement_suggestions") or []
        raw_conf = final_dict.get("confidence")
        try:
            confidence = float(raw_conf) if raw_conf is not None else (1.0 if decision.is_done else 0.5)
        except Exception:
            confidence = 1.0 if decision.is_done else 0.5
        confidence = max(0.0, min(1.0, confidence))

        result = DoneCheckResult(
            is_done=decision.is_done,
            confidence=confidence,
            reasons=[decision.reason],
            violated_constraints=violated if isinstance(violated, list) else [str(violated)],
            improvement_suggestions=suggestions if isinstance(suggestions, list) else [str(suggestions)],
            raw_answer=json.dumps(decision.to_dict(), ensure_ascii=False)
        )
        
        # Audit trace
        try:
            # P5: FULL Trace - include all member replies and arbiter reasoning for deep auditing
            member_details = []
            arbiter_output = None
            if hasattr(decision.raw, "member_replies"):
                for r in decision.raw.member_replies:
                    member_details.append({
                        "member_id": r.member_id,
                        "raw_output": r.raw_output, # FULL CONTENT
                        "parsed": r.parsed,
                        "error": r.error
                    })
            if hasattr(decision.raw, "arbiter_raw"):
                arbiter_output = decision.raw.arbiter_raw

            self.trace_recorder.record_event(
                trace_id=getattr(goal, "parent_task_id", "system"),
                event_type=TraceEventType.DECISION,
                payload={
                    "action": "done_check",
                    "goal_id": goal.goal_id,
                    "is_done": result.is_done,
                    "confidence": result.confidence,
                    "council_details": member_details,
                    "arbiter_raw": arbiter_output,
                    "reasoning": decision.reason
                }
            )
        except Exception: pass

        # Record trace
        trace = ExecutionTrace(
            trace_id=uuid.uuid4().hex,
            task_id=context.task_id,
            component_id="goal_done_definition",
            success=True,
            metrics={"confidence": result.confidence, "is_done_flag": 1.0 if result.is_done else 0.0},
            tags={"goal_id": goal.goal_id}
        )
        self.traces_store.append(trace)

        return result
