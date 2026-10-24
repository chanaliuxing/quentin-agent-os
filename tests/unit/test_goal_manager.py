"""
Unit tests for GoalManager.

Tests the goal and gap tracking functionality.
"""
import pytest
import json
from pathlib import Path
from quentin.goals.manager import GoalManager, GoalOutcome, BlueprintGapOutcome
from quentin.goals.schema import GoalSpec


class TestGoalManager:
    """Test GoalManager basic functionality."""

    def test_initialization(self, tmp_path):
        """Test GoalManager initializes correctly."""
        manager = GoalManager(repo_root=tmp_path)

        assert manager.repo_root == tmp_path
        assert manager.storage_path == tmp_path / "data" / "goals" / "goal_outcomes.json"
        assert len(manager.get_active_goals()) == 0

    def test_custom_storage_path(self, tmp_path):
        """Test custom storage path."""
        custom_path = tmp_path / "custom" / "goals.json"
        manager = GoalManager(repo_root=tmp_path, storage_path=custom_path)

        assert manager.storage_path == custom_path

    def test_activate_goal(self, tmp_path):
        """Test activating a new goal."""
        manager = GoalManager(repo_root=tmp_path)

        goal = GoalSpec(
            goal_id="goal-001",
            title="Test Goal",
            description="A test goal",
            domain="core",
            environment="sandbox",
        )

        outcome = manager.activate_goal(goal)

        assert outcome.goal_id == "goal-001"
        assert outcome.status == "active"
        assert outcome.success_count == 0
        assert outcome.failure_count == 0

        # Check it's in active goals
        active = manager.get_active_goals()
        assert len(active) == 1
        assert active[0].goal_id == "goal-001"

    def test_activate_goal_with_gaps(self, tmp_path):
        """Test activating goal with blueprint gaps."""
        manager = GoalManager(repo_root=tmp_path)

        goal = GoalSpec(
            goal_id="goal-002",
            title="Fix Gap",
            description="Address blueprint gap",
            domain="core",
            environment="sandbox",
        )

        outcome = manager.activate_goal(
            goal,
            blueprint_gaps=["capability-123", "capability-456"],
        )

        assert outcome.blueprint_gaps_addressed == ["capability-123", "capability-456"]

    def test_record_attempt_success(self, tmp_path):
        """Test recording successful attempts."""
        manager = GoalManager(repo_root=tmp_path)

        goal = GoalSpec(
            goal_id="goal-003",
            title="Test",
            description="Test",
            domain="core",
            environment="sandbox",
        )
        manager.activate_goal(goal)

        # Record 3 successful attempts
        for _ in range(3):
            manager.record_attempt(
                "goal-003",
                success=True,
                cost_tokens=100,
                latency_ms=500,
            )

        outcome = manager._goal_outcomes["goal-003"]
        assert outcome.success_count == 3
        assert outcome.failure_count == 0
        assert outcome.total_cost_tokens == 300
        assert outcome.total_latency_ms == 1500

    def test_record_attempt_failure(self, tmp_path):
        """Test recording failed attempts."""
        manager = GoalManager(repo_root=tmp_path)

        goal = GoalSpec(
            goal_id="goal-004",
            title="Test",
            description="Test",
            domain="core",
            environment="sandbox",
        )
        manager.activate_goal(goal)

        # Record 2 failures
        for _ in range(2):
            manager.record_attempt(
                "goal-004",
                success=False,
                cost_tokens=50,
                latency_ms=200,
            )

        outcome = manager._goal_outcomes["goal-004"]
        assert outcome.success_count == 0
        assert outcome.failure_count == 2
        assert outcome.total_cost_tokens == 100
        assert outcome.total_latency_ms == 400

    def test_complete_goal_success(self, tmp_path):
        """Test completing a goal successfully."""
        manager = GoalManager(repo_root=tmp_path)

        goal = GoalSpec(
            goal_id="goal-005",
            title="Complete This",
            description="Test completion",
            domain="core",
            environment="sandbox",
        )
        manager.activate_goal(goal)

        outcome = manager.complete_goal(
            "goal-005",
            success=True,
            notes="All tasks completed",
        )

        assert outcome.status == "completed"
        assert outcome.end_time is not None
        assert outcome.notes == "All tasks completed"

        # Should not be in active goals
        active = manager.get_active_goals()
        assert len(active) == 0

        # Should be in recently completed
        recent = manager.get_recently_completed()
        assert len(recent) == 1
        assert recent[0].goal_id == "goal-005"

    def test_complete_goal_failure(self, tmp_path):
        """Test marking goal as failed."""
        manager = GoalManager(repo_root=tmp_path)

        goal = GoalSpec(
            goal_id="goal-006",
            title="Fail This",
            description="Test failure",
            domain="core",
            environment="sandbox",
        )
        manager.activate_goal(goal)

        outcome = manager.complete_goal(
            "goal-006",
            success=False,
            notes="Timeout exceeded",
        )

        assert outcome.status == "failed"
        assert outcome.end_time is not None
        assert outcome.notes == "Timeout exceeded"

    def test_complete_goal_updates_gaps(self, tmp_path):
        """Test that completing goal updates gap outcomes."""
        manager = GoalManager(repo_root=tmp_path)

        goal = GoalSpec(
            goal_id="goal-007",
            title="Fix Gaps",
            description="Address gaps",
            domain="core",
            environment="sandbox",
        )
        manager.activate_goal(goal, blueprint_gaps=["gap-001", "gap-002"])

        manager.complete_goal("goal-007", success=True, notes="Done")

        # Check gap outcomes
        gap1 = manager.get_gap_outcome("gap-001")
        assert gap1 is not None
        assert gap1.status == "addressed"
        assert gap1.success is True
        assert "goal-007" in gap1.goal_ids

        gap2 = manager.get_gap_outcome("gap-002")
        assert gap2 is not None
        assert gap2.status == "addressed"

    def test_record_gap_patch(self, tmp_path):
        """Test recording patches for gaps."""
        manager = GoalManager(repo_root=tmp_path)

        manager.record_gap_patch(
            gap_id="gap-003",
            patch_id="patch-123",
            goal_id="goal-008",
        )

        gap = manager.get_gap_outcome("gap-003")
        assert gap is not None
        assert "patch-123" in gap.patches_generated
        assert "goal-008" in gap.goal_ids

    def test_get_recently_completed(self, tmp_path):
        """Test getting recently completed goals."""
        manager = GoalManager(repo_root=tmp_path)

        # Create and complete 5 goals
        for i in range(5):
            goal = GoalSpec(
                goal_id=f"goal-{i}",
                title=f"Goal {i}",
                description="Test",
                domain="core",
                environment="sandbox",
            )
            manager.activate_goal(goal)
            manager.complete_goal(f"goal-{i}", success=(i % 2 == 0), notes=f"Note {i}")

        recent = manager.get_recently_completed(limit=3)
        assert len(recent) == 3

        # Should be sorted by end_time descending
        # Most recent first

    def test_get_recently_addressed_gaps(self, tmp_path):
        """Test getting recently addressed gaps."""
        manager = GoalManager(repo_root=tmp_path)

        # Record several gap patches
        for i in range(5):
            manager.record_gap_patch(
                gap_id=f"gap-{i}",
                patch_id=f"patch-{i}",
            )

        recent_gaps = manager.get_recently_addressed_gaps(limit=3)
        assert len(recent_gaps) == 3

    def test_get_summary_for_improver(self, tmp_path):
        """Test generating summary for BlueprintImprover."""
        manager = GoalManager(repo_root=tmp_path)

        # Create some goals
        for i in range(3):
            goal = GoalSpec(
                goal_id=f"goal-{i}",
                title=f"Goal {i}",
                description="Test",
                domain="core",
                environment="sandbox",
            )

            if i < 2:
                # Complete first 2
                manager.activate_goal(goal, blueprint_gaps=[f"gap-{i}"])
                manager.complete_goal(f"goal-{i}", success=(i == 0), notes=f"Result {i}")
            else:
                # Leave last one active
                manager.activate_goal(goal)

        summary = manager.get_summary_for_improver()

        assert summary["active_goal_count"] == 1
        assert summary["total_recent_attempts"] == 2
        assert 0 <= summary["recent_success_rate"] <= 1
        assert len(summary["recently_addressed_gaps"]) >= 0
        assert isinstance(summary["active_goals"], list)

    def test_get_statistics(self, tmp_path):
        """Test getting overall statistics."""
        manager = GoalManager(repo_root=tmp_path)

        # Create mixed goals
        for i in range(10):
            goal = GoalSpec(
                goal_id=f"goal-{i}",
                title=f"Goal {i}",
                description="Test",
                domain="core",
                environment="sandbox",
            )

            manager.activate_goal(goal)

            if i < 4:
                manager.complete_goal(f"goal-{i}", success=True)
            elif i < 7:
                manager.complete_goal(f"goal-{i}", success=False)
            # Rest stay active

        stats = manager.get_statistics()

        assert stats["total_goals"] == 10
        assert stats["active_goals"] == 3
        assert stats["completed_goals"] == 4
        assert stats["failed_goals"] == 3

    def test_persistence(self, tmp_path):
        """Test that data persists across instances."""
        # First instance
        manager1 = GoalManager(repo_root=tmp_path)

        goal = GoalSpec(
            goal_id="goal-persist",
            title="Persist Test",
            description="Test persistence",
            domain="core",
            environment="sandbox",
        )
        manager1.activate_goal(goal, blueprint_gaps=["gap-persist"])
        manager1.record_attempt("goal-persist", success=True, cost_tokens=100)

        # Second instance (load from file)
        manager2 = GoalManager(repo_root=tmp_path)

        active = manager2.get_active_goals()
        assert len(active) == 1
        assert active[0].goal_id == "goal-persist"
        assert active[0].success_count == 1
        assert active[0].total_cost_tokens == 100

        gap = manager2.get_gap_outcome("gap-persist")
        assert gap is not None
        assert "goal-persist" in gap.goal_ids

    def test_auto_create_outcome_on_attempt(self, tmp_path):
        """Test that recording attempt creates outcome if missing."""
        manager = GoalManager(repo_root=tmp_path)

        # Record attempt for non-existent goal
        manager.record_attempt(
            "goal-new",
            success=True,
            cost_tokens=50,
        )

        outcome = manager._goal_outcomes.get("goal-new")
        assert outcome is not None
        assert outcome.success_count == 1
        assert outcome.total_cost_tokens == 50


class TestGoalOutcome:
    """Test GoalOutcome data model."""

    def test_to_dict(self):
        """Test serialization to dict."""
        outcome = GoalOutcome(
            goal_id="test-001",
            status="active",
            success_count=5,
            failure_count=2,
        )

        data = outcome.to_dict()

        assert data["goal_id"] == "test-001"
        assert data["status"] == "active"
        assert data["success_count"] == 5
        assert data["failure_count"] == 2

    def test_from_dict(self):
        """Test deserialization from dict."""
        data = {
            "goal_id": "test-002",
            "status": "completed",
            "success_count": 10,
            "failure_count": 0,
            "total_cost_tokens": 5000,
        }

        outcome = GoalOutcome.from_dict(data)

        assert outcome.goal_id == "test-002"
        assert outcome.status == "completed"
        assert outcome.success_count == 10
        assert outcome.total_cost_tokens == 5000


class TestBlueprintGapOutcome:
    """Test BlueprintGapOutcome data model."""

    def test_to_dict(self):
        """Test serialization to dict."""
        gap_outcome = BlueprintGapOutcome(
            gap_id="gap-001",
            status="addressed",
            goal_ids=["goal-1", "goal-2"],
            patches_generated=["patch-1"],
            success=True,
        )

        data = gap_outcome.to_dict()

        assert data["gap_id"] == "gap-001"
        assert data["status"] == "addressed"
        assert data["goal_ids"] == ["goal-1", "goal-2"]
        assert data["success"] is True

    def test_from_dict(self):
        """Test deserialization from dict."""
        data = {
            "gap_id": "gap-002",
            "status": "in_progress",
            "goal_ids": ["goal-3"],
            "patches_generated": ["patch-2", "patch-3"],
            "success": False,
        }

        gap_outcome = BlueprintGapOutcome.from_dict(data)

        assert gap_outcome.gap_id == "gap-002"
        assert gap_outcome.status == "in_progress"
        assert gap_outcome.goal_ids == ["goal-3"]
        assert len(gap_outcome.patches_generated) == 2
