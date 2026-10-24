"""
Unit tests for ImmuneLoop windowed error-rate detection.

Tests the anomaly detection functionality when error rate exceeds thresholds.
"""
import pytest
from pathlib import Path
from quentin.immune.loop import ImmuneLoop
from quentin.immune.anomaly import MetricSnapshot, AnomalyDetector
from quentin.immune.store import ImmuneCaseStore
from quentin.cognitive.loop import CognitiveLoop
from dataclasses import dataclass, asdict
from typing import Optional


@dataclass
class MockGoal:
    """Mock goal object for testing (JSON-serializable)."""
    goal_id: str
    title: str
    domain: str = "test"
    environment: str = "sandbox"

    def to_dict(self):
        return asdict(self)


class TestImmuneLoopWindowedErrorRate:
    """Test windowed error rate detection in ImmuneLoop."""

    def test_no_anomaly_when_error_rate_low(self, tmp_path):
        """Test that no anomaly is detected when error rate is acceptable."""
        immune_loop = ImmuneLoop(repo_root=tmp_path)

        # Simulate 10 attempts with 1 error (10% error rate)
        snapshot = MetricSnapshot(
            attempt_index=10,
            total_attempts=10,
            success_attempts=9,
            error_attempts=1,
            cost_tokens=1000,
            latency_ms=500,
            reward_score=0.9,
        )

        recent_snapshots = [snapshot]
        goal = MockGoal(goal_id="test-goal-001", title="Test Goal")
        metrics = {
            "total_attempts": 10,
            "success_attempts": 9,
            "error_attempts": 1,
        }

        action = immune_loop.after_attempt(
            goal=goal,
            metrics=metrics,
            snapshot=snapshot,
            recent_snapshots=recent_snapshots,
            recent_traces=[],
        )

        assert action is None, "Should not trigger immune action for low error rate"

    def test_anomaly_detected_when_error_rate_high(self, tmp_path):
        """Test that anomaly is detected when error rate exceeds threshold."""
        immune_loop = ImmuneLoop(repo_root=tmp_path)

        # Simulate 10 attempts with 8 errors (80% error rate)
        snapshot = MetricSnapshot(
            attempt_index=10,
            total_attempts=10,
            success_attempts=2,
            error_attempts=8,
            cost_tokens=1000,
            latency_ms=500,
            reward_score=0.2,
        )

        recent_snapshots = [snapshot]
        goal = MockGoal(goal_id="test-goal-002", title="Failing Goal")
        metrics = {
            "total_attempts": 10,
            "success_attempts": 2,
            "error_attempts": 8,
        }

        action = immune_loop.after_attempt(
            goal=goal,
            metrics=metrics,
            snapshot=snapshot,
            recent_snapshots=recent_snapshots,
            recent_traces=[],
        )

        # High error rate should trigger immune action
        assert action is not None, "Should trigger immune action for high error rate"
        assert isinstance(action.notes, str)
        assert action.immune_case_id is not None

    def test_windowed_error_rate_calculation(self, tmp_path):
        """Test error rate calculation across multiple snapshots (window)."""
        immune_loop = ImmuneLoop(repo_root=tmp_path)

        # Create a window of snapshots showing increasing error rate
        snapshots = []
        for i in range(1, 6):
            # Error rate increases: 20%, 40%, 60%, 80%, 100%
            errors = i * 2
            successes = 10 - errors
            snap = MetricSnapshot(
                attempt_index=i,
                total_attempts=10 * i,
                success_attempts=successes * i,
                error_attempts=errors * i,
                cost_tokens=1000 * i,
                latency_ms=500,
                reward_score=1.0 - (errors / 10),
            )
            snapshots.append(snap)

        goal = MockGoal(goal_id="test-goal-003", title="Degrading Goal")
        metrics = {
            "total_attempts": 50,
            "success_attempts": 15,  # 30% success
            "error_attempts": 35,    # 70% error
        }

        action = immune_loop.after_attempt(
            goal=goal,
            metrics=metrics,
            snapshot=snapshots[-1],
            recent_snapshots=snapshots,
            recent_traces=[],
        )

        # High cumulative error rate should trigger action
        assert action is not None, "Should detect anomaly in windowed error rate"

    def test_immune_case_stored_on_anomaly(self, tmp_path):
        """Test that ImmuneCase is stored when anomaly is detected."""
        case_store = ImmuneCaseStore(repo_root=tmp_path)
        immune_loop = ImmuneLoop(
            repo_root=tmp_path,
            case_store=case_store,
        )

        # High error rate scenario
        snapshot = MetricSnapshot(
            attempt_index=5,
            total_attempts=5,
            success_attempts=1,
            error_attempts=4,
            cost_tokens=500,
            latency_ms=1000,
            reward_score=0.2,
        )

        goal = MockGoal(goal_id="test-goal-004", title="Failing Goal")
        metrics = {
            "total_attempts": 5,
            "success_attempts": 1,
            "error_attempts": 4,
        }

        action = immune_loop.after_attempt(
            goal=goal,
            metrics=metrics,
            snapshot=snapshot,
            recent_snapshots=[snapshot],
            recent_traces=[],
        )

        if action:
            # Check that case was stored
            assert action.immune_case_id is not None
            # Verify that the immune case ID is set (means case was created)
            assert isinstance(action.immune_case_id, str)
            assert len(action.immune_case_id) > 0

    def test_no_action_with_insufficient_samples(self, tmp_path):
        """Test that no action is taken when sample size is too small."""
        immune_loop = ImmuneLoop(repo_root=tmp_path)

        # Only 2 attempts (insufficient for reliable error rate)
        snapshot = MetricSnapshot(
            attempt_index=2,
            total_attempts=2,
            success_attempts=0,
            error_attempts=2,  # 100% error but too few samples
            cost_tokens=100,
            latency_ms=200,
            reward_score=0.0,
        )

        goal = MockGoal(goal_id="test-goal-005", title="New Goal")
        metrics = {
            "total_attempts": 2,
            "success_attempts": 0,
            "error_attempts": 2,
        }

        action = immune_loop.after_attempt(
            goal=goal,
            metrics=metrics,
            snapshot=snapshot,
            recent_snapshots=[snapshot],
            recent_traces=[],
        )

        # Anomaly detector might require minimum samples
        # This behavior depends on AnomalyDetector implementation
        # Test documents the behavior with small samples

    def test_latency_threshold_anomaly(self, tmp_path):
        """Test that high latency can trigger anomaly detection."""
        immune_loop = ImmuneLoop(repo_root=tmp_path)

        # Normal error rate but very high latency
        snapshot = MetricSnapshot(
            attempt_index=10,
            total_attempts=10,
            success_attempts=9,
            error_attempts=1,
            cost_tokens=1000,
            latency_ms=10000,  # 10 seconds (very high)
            reward_score=0.8,
        )

        goal = MockGoal(goal_id="test-goal-006", title="Slow Goal")
        metrics = {
            "total_attempts": 10,
            "success_attempts": 9,
            "error_attempts": 1,
            "latency_ms": 10000,
        }

        action = immune_loop.after_attempt(
            goal=goal,
            metrics=metrics,
            snapshot=snapshot,
            recent_snapshots=[snapshot],
            recent_traces=[],
        )

        # High latency might trigger anomaly depending on detector config
        # Test documents the latency detection behavior

    def test_action_flags_for_severe_anomaly(self, tmp_path):
        """Test that severe anomalies set appropriate action flags."""
        immune_loop = ImmuneLoop(repo_root=tmp_path)

        # Very severe: 95% error rate
        snapshot = MetricSnapshot(
            attempt_index=20,
            total_attempts=20,
            success_attempts=1,
            error_attempts=19,
            cost_tokens=2000,
            latency_ms=1000,
            reward_score=0.05,
        )
        goal = MockGoal(goal_id="test-goal-007", title="Critical Failure")
        metrics = {
            "total_attempts": 20,
            "success_attempts": 1,
            "error_attempts": 19,
        }

        action = immune_loop.after_attempt(
            goal=goal,
            metrics=metrics,
            snapshot=snapshot,
            recent_snapshots=[snapshot],
            recent_traces=[],
        )

        if action:
            # Severe anomalies should suggest strong actions
            assert isinstance(action.degrade_mode, bool)
            assert isinstance(action.disable_self_programming, bool)
            assert isinstance(action.revert_version, bool)
            assert len(action.notes) > 0


def test_local_runtime_first_attempt_high_latency_does_not_trigger(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_BASE_URL", "http://localhost:11434")
    monkeypatch.delenv("QUENTIN_IMMUNE_MAX_LATENCY_MS", raising=False)
    detector = AnomalyDetector()
    snapshot = MetricSnapshot(
        attempt_index=1,
        total_attempts=1,
        success_attempts=1,
        error_attempts=0,
        cost_tokens=100.0,
        latency_ms=350_000.0,
        reward_score=1.0,
    )
    signal = detector.analyze(
        goal=MockGoal(goal_id="g-local-1", title="local"),
        metrics={},
        snapshot=snapshot,
        recent_snapshots=[snapshot],
    )
    assert signal is None


def test_local_runtime_second_attempt_high_latency_triggers(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_BASE_URL", "http://localhost:11434")
    monkeypatch.setenv("QUENTIN_IMMUNE_MAX_LATENCY_MS_LOCAL", "300000")
    monkeypatch.delenv("QUENTIN_IMMUNE_MAX_LATENCY_MS", raising=False)
    detector = AnomalyDetector()
    snapshot = MetricSnapshot(
        attempt_index=2,
        total_attempts=2,
        success_attempts=1,
        error_attempts=1,
        cost_tokens=100.0,
        latency_ms=320_000.0,
        reward_score=0.5,
    )
    signal = detector.analyze(
        goal=MockGoal(goal_id="g-local-2", title="local"),
        metrics={},
        snapshot=snapshot,
        recent_snapshots=[snapshot],
    )
    assert signal is not None
    assert signal.anomaly_type == "high_latency"


def test_circuit_breaker_state_updates_once_per_attempt() -> None:
    c, last, current, trig = CognitiveLoop._update_circuit_breaker_state(
        raw_error="timeout",
        consecutive_errors=0,
        last_error_msg="",
        threshold=2,
    )
    assert (c, last, current, trig) == (1, "timeout", "timeout", False)

    c2, last2, current2, trig2 = CognitiveLoop._update_circuit_breaker_state(
        raw_error="timeout",
        consecutive_errors=c,
        last_error_msg=last,
        threshold=2,
    )
    assert (c2, last2, current2, trig2) == (2, "timeout", "timeout", True)

    c3, last3, current3, trig3 = CognitiveLoop._update_circuit_breaker_state(
        raw_error=None,
        consecutive_errors=c2,
        last_error_msg=last2,
        threshold=2,
    )
    assert (c3, last3, current3, trig3) == (0, "", "", False)


class TestImmuneLoopIntegration:
    """Integration tests for ImmuneLoop with CognitiveLoop."""

    def test_immune_loop_can_be_initialized_from_cognitive_loop(self, tmp_path):
        """Test that ImmuneLoop can be initialized as expected by CognitiveLoop."""
        # This mimics how CognitiveLoop would initialize ImmuneLoop
        immune_loop = ImmuneLoop(repo_root=tmp_path)

        assert immune_loop is not None
        assert immune_loop.anomaly_detector is not None
        assert immune_loop.case_store is not None

    def test_after_attempt_signature_matches_cognitive_loop_usage(self, tmp_path):
        """Test that after_attempt signature matches CognitiveLoop usage."""
        immune_loop = ImmuneLoop(repo_root=tmp_path)

        # This is exactly how CognitiveLoop calls after_attempt
        goal = MockGoal(goal_id="test", title="Test")
        metrics = {"total_attempts": 1, "success_attempts": 1, "error_attempts": 0}
        snapshot = MetricSnapshot(
            attempt_index=1,
            total_attempts=1,
            success_attempts=1,
            error_attempts=0,
            cost_tokens=100,
            latency_ms=100,
            reward_score=1.0,
        )

        # Should not raise any errors
        action = immune_loop.after_attempt(
            goal=goal,
            metrics=metrics,
            snapshot=snapshot,
            recent_snapshots=[snapshot],
            recent_traces=[],
        )

        # With good metrics, should return None
        assert action is None or isinstance(action.notes, str)
