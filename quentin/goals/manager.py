"""
GoalManager: Minimal stub for tracking goals and blueprint gaps.

Tracks:
- Active goals (currently being pursued)
- Completed goals (successfully addressed)
- Failed goals (attempted but failed)
- Recently addressed blueprint gaps

Provides summaries for BlueprintImprover to understand context.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional
import json
import logging
import uuid

from quentin.goals.schema import GoalSpec
from quentin.utils.time import now_utc_iso

logger = logging.getLogger(__name__)


@dataclass
class GoalOutcome:
    """
    Record of a goal execution outcome.

    - goal_id: Reference to GoalSpec
    - status: "active" / "completed" / "failed"
    - start_time: When goal was activated
    - end_time: When goal was completed/failed (None if still active)
    - success_count: Number of successful attempts
    - failure_count: Number of failed attempts
    - total_cost_tokens: Total tokens spent on this goal
    - total_latency_ms: Total latency across attempts
    - notes: Additional context or failure reasons
    - blueprint_gaps_addressed: List of gap IDs this goal addressed
    """
    goal_id: str
    status: str = "active"  # "active" / "completed" / "failed"
    start_time: str = field(default_factory=now_utc_iso)
    end_time: Optional[str] = None
    success_count: int = 0
    failure_count: int = 0
    total_cost_tokens: int = 0
    total_latency_ms: int = 0
    notes: str = ""
    blueprint_gaps_addressed: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> "GoalOutcome":
        return GoalOutcome(
            goal_id=data["goal_id"],
            status=data.get("status", "active"),
            start_time=data.get("start_time", now_utc_iso()),
            end_time=data.get("end_time"),
            success_count=data.get("success_count", 0),
            failure_count=data.get("failure_count", 0),
            total_cost_tokens=data.get("total_cost_tokens", 0),
            total_latency_ms=data.get("total_latency_ms", 0),
            notes=data.get("notes", ""),
            blueprint_gaps_addressed=data.get("blueprint_gaps_addressed", []),
        )


@dataclass
class BlueprintGapOutcome:
    """
    Record of addressing a blueprint gap.

    - gap_id: Capability ID from blueprint
    - status: "in_progress" / "addressed" / "abandoned"
    - goal_ids: Goals that attempted to address this gap
    - patches_generated: Patch IDs generated for this gap
    - success: Whether gap was successfully addressed
    - timestamp: When this record was updated
    """
    gap_id: str
    status: str = "in_progress"  # "in_progress" / "addressed" / "abandoned"
    goal_ids: List[str] = field(default_factory=list)
    patches_generated: List[str] = field(default_factory=list)
    success: bool = False
    timestamp: str = field(default_factory=now_utc_iso)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> "BlueprintGapOutcome":
        return BlueprintGapOutcome(
            gap_id=data["gap_id"],
            status=data.get("status", "in_progress"),
            goal_ids=data.get("goal_ids", []),
            patches_generated=data.get("patches_generated", []),
            success=data.get("success", False),
            timestamp=data.get("timestamp", now_utc_iso()),
        )


class GoalManager:
    """
    Minimal GoalManager stub for tracking goals and blueprint gaps.

    Storage: JSON file (in-memory cache + persistent file)

    Features:
    - Track active/completed/failed goals
    - Record success/failure metrics
    - Link goals to blueprint gaps
    - Provide summaries for BlueprintImprover
    """

    def __init__(
        self,
        *,
        repo_root: str | Path = ".",
        storage_path: Optional[str | Path] = None,
    ):
        self.repo_root = Path(repo_root).resolve()

        if storage_path is None:
            self.storage_path = self.repo_root / "data" / "goals" / "goal_outcomes.json"
        else:
            self.storage_path = Path(storage_path)

        self.storage_path.parent.mkdir(parents=True, exist_ok=True)

        # In-memory cache
        self._goal_outcomes: Dict[str, GoalOutcome] = {}
        self._gap_outcomes: Dict[str, BlueprintGapOutcome] = {}

        self._load()

    def _load(self) -> None:
        """Load from persistent storage."""
        if not self.storage_path.exists():
            return

        try:
            with self.storage_path.open("r", encoding="utf-8") as f:
                data = json.load(f)

            # Load goal outcomes
            for item in data.get("goal_outcomes", []):
                try:
                    outcome = GoalOutcome.from_dict(item)
                    self._goal_outcomes[outcome.goal_id] = outcome
                except Exception:
                    logger.exception("Failed to load goal outcome")

            # Load gap outcomes
            for item in data.get("gap_outcomes", []):
                try:
                    outcome = BlueprintGapOutcome.from_dict(item)
                    self._gap_outcomes[outcome.gap_id] = outcome
                except Exception:
                    logger.exception("Failed to load gap outcome")

            logger.info(
                f"Loaded {len(self._goal_outcomes)} goal outcomes, "
                f"{len(self._gap_outcomes)} gap outcomes from {self.storage_path}"
            )
        except Exception:
            logger.exception("Failed to load goal manager storage")

    def _save(self) -> None:
        """Save to persistent storage."""
        data = {
            "goal_outcomes": [o.to_dict() for o in self._goal_outcomes.values()],
            "gap_outcomes": [o.to_dict() for o in self._gap_outcomes.values()],
        }

        try:
            # Write to temp file first
            tmp_path = self.storage_path.with_suffix(".tmp")
            with tmp_path.open("w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

            # Atomic replace
            tmp_path.replace(self.storage_path)

            logger.debug(f"Saved goal manager state to {self.storage_path}")
        except Exception:
            logger.exception("Failed to save goal manager storage")

    # ---- Goal Management ----

    def activate_goal(
        self,
        goal: GoalSpec,
        *,
        blueprint_gaps: Optional[List[str]] = None,
    ) -> GoalOutcome:
        """
        Activate a new goal for tracking.

        Args:
            goal: GoalSpec to track
            blueprint_gaps: Optional list of blueprint gap IDs this goal addresses

        Returns:
            GoalOutcome record
        """
        outcome = GoalOutcome(
            goal_id=goal.goal_id,
            status="active",
            blueprint_gaps_addressed=blueprint_gaps or [],
        )

        self._goal_outcomes[goal.goal_id] = outcome

        # If blueprint gaps are provided, create/update corresponding BlueprintGapOutcome
        for gap_id in (blueprint_gaps or []):
            self._update_gap_outcome(gap_id, goal.goal_id, success=False) # Initially not successful

        self._save()

        logger.info(f"Activated goal {goal.goal_id}: {goal.title}")
        return outcome

    def record_attempt(
        self,
        goal_id: str,
        *,
        success: bool,
        cost_tokens: int = 0,
        latency_ms: int = 0,
    ) -> None:
        """
        Record an attempt for a goal.

        Args:
            goal_id: Goal ID
            success: Whether attempt succeeded
            cost_tokens: Tokens used in this attempt
            latency_ms: Latency of this attempt
        """
        outcome = self._goal_outcomes.get(goal_id)
        if outcome is None:
            logger.warning(f"Goal {goal_id} not found, creating new outcome")
            outcome = GoalOutcome(goal_id=goal_id)
            self._goal_outcomes[goal_id] = outcome

        if success:
            outcome.success_count += 1
        else:
            outcome.failure_count += 1

        outcome.total_cost_tokens += cost_tokens
        outcome.total_latency_ms += latency_ms

        self._save()

    def complete_goal(
        self,
        goal_id: str,
        *,
        success: bool,
        notes: str = "",
    ) -> GoalOutcome:
        """
        Mark a goal as completed or failed.

        Args:
            goal_id: Goal ID
            success: Whether goal was successfully completed
            notes: Additional context

        Returns:
            Updated GoalOutcome
        """
        outcome = self._goal_outcomes.get(goal_id)
        if outcome is None:
            logger.warning(f"Goal {goal_id} not found")
            return None

        outcome.status = "completed" if success else "failed"
        outcome.end_time = now_utc_iso()
        outcome.notes = notes

        # Update gap outcomes if this goal addressed any gaps
        if success:
            for gap_id in outcome.blueprint_gaps_addressed:
                self._update_gap_outcome(gap_id, goal_id, success=True)

        self._save()

        logger.info(
            f"Goal {goal_id} {'completed' if success else 'failed'} "
            f"(success={outcome.success_count}, failures={outcome.failure_count})"
        )
        return outcome

    # ---- Gap Management ----

    def _update_gap_outcome(
        self,
        gap_id: str,
        goal_id: str,
        *,
        success: bool,
        patch_id: Optional[str] = None,
    ) -> None:
        """Internal: Update gap outcome."""
        gap_outcome = self._gap_outcomes.get(gap_id)
        if gap_outcome is None:
            gap_outcome = BlueprintGapOutcome(gap_id=gap_id)
            self._gap_outcomes[gap_id] = gap_outcome

        if goal_id not in gap_outcome.goal_ids:
            gap_outcome.goal_ids.append(goal_id)

        if patch_id and patch_id not in gap_outcome.patches_generated:
            gap_outcome.patches_generated.append(patch_id)

        if success:
            gap_outcome.status = "addressed"
            gap_outcome.success = True

        gap_outcome.timestamp = now_utc_iso()

    def record_gap_patch(
        self,
        gap_id: str,
        patch_id: str,
        goal_id: Optional[str] = None,
    ) -> None:
        """
        Record that a patch was generated for a gap.

        Args:
            gap_id: Blueprint gap ID
            patch_id: Patch ID
            goal_id: Optional associated goal ID
        """
        gap_outcome = self._gap_outcomes.get(gap_id)
        if gap_outcome is None:
            gap_outcome = BlueprintGapOutcome(gap_id=gap_id)
            self._gap_outcomes[gap_id] = gap_outcome

        if patch_id not in gap_outcome.patches_generated:
            gap_outcome.patches_generated.append(patch_id)

        if goal_id and goal_id not in gap_outcome.goal_ids:
            gap_outcome.goal_ids.append(goal_id)

        gap_outcome.timestamp = now_utc_iso()

        self._save()

    # ---- Query & Summary ----

    def get_active_goals(self) -> List[GoalOutcome]:
        """Get all active goals."""
        return [
            outcome for outcome in self._goal_outcomes.values()
            if outcome.status == "active"
        ]

    def get_recently_completed(self, limit: int = 10) -> List[GoalOutcome]:
        """Get recently completed/failed goals."""
        completed = [
            outcome for outcome in self._goal_outcomes.values()
            if outcome.status in ("completed", "failed") and outcome.end_time
        ]

        # Sort by end_time descending
        completed.sort(key=lambda x: x.end_time or "", reverse=True)

        return completed[:limit]

    def get_gap_outcome(self, gap_id: str) -> Optional[BlueprintGapOutcome]:
        """Get outcome for a specific gap."""
        return self._gap_outcomes.get(gap_id)

    def get_recently_addressed_gaps(self, limit: int = 20) -> List[BlueprintGapOutcome]:
        """Get recently addressed gaps."""
        gaps = list(self._gap_outcomes.values())

        # Sort by timestamp descending
        gaps.sort(key=lambda x: x.timestamp, reverse=True)

        return gaps[:limit]

    def get_summary_for_improver(self) -> Dict[str, Any]:
        """
        Generate summary for BlueprintImprover context.

        Returns dict with:
        - active_goal_count
        - recent_success_rate
        - recently_addressed_gaps (list of gap_ids)
        - top_failure_reasons
        """
        active = self.get_active_goals()
        recent_completed = self.get_recently_completed(limit=20)
        recent_gaps = self.get_recently_addressed_gaps(limit=20)

        # Calculate success rate
        if recent_completed:
            success_count = sum(1 for o in recent_completed if o.status == "completed")
            success_rate = success_count / len(recent_completed)
        else:
            success_rate = 0.0

        # Extract failure reasons
        failure_reasons = []
        for outcome in recent_completed:
            if outcome.status == "failed" and outcome.notes:
                failure_reasons.append({
                    "goal_id": outcome.goal_id,
                    "reason": outcome.notes,
                })

        return {
            "active_goal_count": len(active),
            "recent_success_rate": success_rate,
            "total_recent_attempts": len(recent_completed),
            "recently_addressed_gaps": [g.gap_id for g in recent_gaps if g.status == "addressed"],
            "gaps_in_progress": [g.gap_id for g in recent_gaps if g.status == "in_progress"],
            "top_failure_reasons": failure_reasons[:5],
            "active_goals": [
                {
                    "goal_id": o.goal_id,
                    "success_count": o.success_count,
                    "failure_count": o.failure_count,
                    "gaps": o.blueprint_gaps_addressed,
                }
                for o in active
            ],
        }

    def get_statistics(self) -> Dict[str, Any]:
        """Get overall statistics."""
        total = len(self._goal_outcomes)
        active = len([o for o in self._goal_outcomes.values() if o.status == "active"])
        completed = len([o for o in self._goal_outcomes.values() if o.status == "completed"])
        failed = len([o for o in self._goal_outcomes.values() if o.status == "failed"])

        total_gaps = len(self._gap_outcomes)
        addressed_gaps = len([g for g in self._gap_outcomes.values() if g.status == "addressed"])

        return {
            "total_goals": total,
            "active_goals": active,
            "completed_goals": completed,
            "failed_goals": failed,
            "total_gaps_tracked": total_gaps,
            "addressed_gaps": addressed_gaps,
        }
