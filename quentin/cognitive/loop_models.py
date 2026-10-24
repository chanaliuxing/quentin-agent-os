from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional
import uuid

from quentin.goals.done_definition import DoneCheckResult
from quentin.utils.time import now_utc_iso


@dataclass
class PlannerResult:
    goal_id: str
    raw_output: str
    steps: List[Dict[str, Any]]
    used_skills: List[Dict[str, Any]] = field(default_factory=list)


PlannerFn = Callable[["CognitiveTask", Any], str]
ExecutorFn = Callable[["CognitiveTask", Any, str], Dict[str, Any]]


@dataclass
class CognitiveTask:
    input_text: str
    task_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    domain: str = "core"
    environment: str = "sandbox"
    goal_title: Optional[str] = None
    goal_description: Optional[str] = None
    success_criteria: List[str] = field(default_factory=list)
    hard_constraints: List[str] = field(default_factory=list)
    soft_preferences: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        meta = dict(self.metadata or {}) if isinstance(self.metadata, dict) else {}
        meta.pop("cancel_token", None)
        return {
            "input_text": self.input_text,
            "task_id": self.task_id,
            "domain": self.domain,
            "environment": self.environment,
            "goal_title": self.goal_title,
            "goal_description": self.goal_description,
            "success_criteria": list(self.success_criteria or []),
            "hard_constraints": list(self.hard_constraints or []),
            "soft_preferences": list(self.soft_preferences or []),
            "metadata": meta,
        }

    def to_goal_spec(self) -> Dict[str, Any]:
        title = self.goal_title or self._auto_title()
        desc = self.goal_description or self.input_text
        return {
            "title": title,
            "description": desc,
            "domain": self.domain,
            "environment": self.environment,
            "success_criteria": self.success_criteria,
            "hard_constraints": self.hard_constraints,
            "soft_preferences": self.soft_preferences,
            "created_by": "agent",
            "parent_task_id": self.task_id,
            "metadata": self.metadata,
        }

    def _auto_title(self, max_len: int = 80) -> str:
        text = (self.goal_title or "").strip()
        if not text:
            text = (self.input_text or "").strip()
        if len(text) > max_len:
            text = text[: max_len - 3] + "..."
        return text or "Unnamed Cognitive Task"


@dataclass
class CognitiveResult:
    task_id: str
    goal_id: str
    final_output: str
    plan_summary: str
    actions_summary: str
    done_result: DoneCheckResult
    done: bool
    done_confidence: float
    raw_executor_result: Any = None
    self_awareness: Dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=now_utc_iso)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "goal_id": self.goal_id,
            "final_output": self.final_output,
            "plan_summary": self.plan_summary,
            "actions_summary": self.actions_summary,
            "done": self.done,
            "done_confidence": self.done_confidence,
            "self_awareness": dict(self.self_awareness or {}),
            "done_result": self.done_result.to_dict(),
            "created_at": self.created_at,
        }
