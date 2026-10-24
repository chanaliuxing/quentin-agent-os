from __future__ import annotations

from quentin.immune.anomaly import AnomalyDetector, MetricSnapshot


def _base_snapshot() -> MetricSnapshot:
    return MetricSnapshot(
        attempt_index=1,
        total_attempts=2,
        success_attempts=1,
        error_attempts=1,
        cost_tokens=10.0,
        latency_ms=100.0,
        reward_score=0.8,
    )


def test_prediction_error_spike_triggers_anomaly() -> None:
    detector = AnomalyDetector(config={"prediction_error_rate_threshold": 0.6})
    snap = _base_snapshot()
    snap.prediction_error_rate = 0.75
    out = detector.analyze(goal=None, metrics={}, snapshot=snap, recent_snapshots=[])
    assert out is not None
    assert out.anomaly_type == "prediction_error_spike"
    assert "disable_reflex_mode" in (out.suggested_actions or [])


def test_context_misclass_spike_triggers_anomaly() -> None:
    detector = AnomalyDetector(config={"context_misclass_rate_threshold": 0.7})
    snap = _base_snapshot()
    snap.prediction_error_rate = 0.1
    snap.context_misclass_rate = 0.9
    out = detector.analyze(goal=None, metrics={}, snapshot=snap, recent_snapshots=[])
    assert out is not None
    assert out.anomaly_type == "context_misclass_spike"
    assert "degrade_mode" in (out.suggested_actions or [])


def test_no_prediction_error_anomaly_when_below_threshold() -> None:
    detector = AnomalyDetector(config={"prediction_error_rate_threshold": 0.8})
    snap = _base_snapshot()
    snap.prediction_error_rate = 0.2
    snap.context_misclass_rate = 0.2
    out = detector.analyze(goal=None, metrics={}, snapshot=snap, recent_snapshots=[])
    assert out is None
