from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


@dataclass
class GoalAttempt:
    timestamp: float
    success: bool
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class GoalRecord:
    goal_id: str
    description: Optional[str] = None
    status: str = "pending"
    attempts: list[GoalAttempt] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    completed_at: Optional[float] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "goal_id": self.goal_id,
            "description": self.description,
            "status": self.status,
            "attempts": [asdict(a) for a in self.attempts],
            "created_at": self.created_at,
            "completed_at": self.completed_at,
            "metadata": self.metadata,
        }


class GoalManager:
    """
    Minimal goal tracker used by runtime loops to mark progress.

    Persisted state is optional; callers can inject a storage_path to keep a simple JSON ledger.
    """

    def __init__(self, storage_path: Optional[str | Path] = None) -> None:
        self.storage_path = Path(storage_path) if storage_path else None
        self.goals: Dict[str, GoalRecord] = {}

        if self.storage_path:
            self.storage_path.parent.mkdir(parents=True, exist_ok=True)
            self._load()

    def activate_goal(self, goal_id: str, description: Optional[str] = None, metadata: Optional[Dict[str, Any]] = None) -> GoalRecord:
        record = self.goals.get(goal_id) or GoalRecord(goal_id=goal_id)
        record.status = "active"
        if description:
            record.description = description
        if metadata:
            record.metadata.update(metadata)
        self.goals[goal_id] = record
        self._persist()
        logger.debug("Activated goal %s", goal_id)
        return record

    def record_attempt(self, goal_id: str, success: bool, metadata: Optional[Dict[str, Any]] = None) -> GoalRecord:
        record = self.goals.get(goal_id) or GoalRecord(goal_id=goal_id)
        attempt = GoalAttempt(timestamp=time.time(), success=success, metadata=metadata or {})
        record.attempts.append(attempt)
        if record.status == "pending":
            record.status = "active"
        self.goals[goal_id] = record
        self._persist()
        logger.debug("Recorded attempt for goal %s (success=%s)", goal_id, success)
        return record

    def complete_goal(self, goal_id: str, success: bool, metadata: Optional[Dict[str, Any]] = None) -> GoalRecord:
        record = self.goals.get(goal_id) or GoalRecord(goal_id=goal_id)
        record.status = "completed" if success else "failed"
        record.completed_at = time.time()
        if metadata:
            record.metadata.update(metadata)
        self.goals[goal_id] = record
        self._persist()
        logger.debug("Completed goal %s (success=%s)", goal_id, success)
        return record

    def get_goal(self, goal_id: str) -> Optional[GoalRecord]:
        return self.goals.get(goal_id)

    def _persist(self) -> None:
        if not self.storage_path:
            return
        try:
            payload = [record.to_dict() for record in self.goals.values()]
            self.storage_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            logger.exception("Failed to persist goals to %s", self.storage_path)

    def _load(self) -> None:
        if not self.storage_path or not self.storage_path.exists():
            return
        try:
            raw = json.loads(self.storage_path.read_text(encoding="utf-8"))
            for item in raw:
                attempts = [GoalAttempt(**a) for a in item.get("attempts", [])]
                record = GoalRecord(
                    goal_id=item.get("goal_id"),
                    description=item.get("description"),
                    status=item.get("status", "pending"),
                    attempts=attempts,
                    created_at=item.get("created_at", time.time()),
                    completed_at=item.get("completed_at"),
                    metadata=item.get("metadata", {}),
                )
                self.goals[record.goal_id] = record
        except Exception:
            logger.exception("Failed to load goals from %s", self.storage_path)
