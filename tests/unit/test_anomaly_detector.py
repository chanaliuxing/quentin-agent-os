# tests/unit/test_anomaly_detector.py

import pytest
from quentin.observability.anomaly_detector import AnomalyDetector, Anomaly

def test_detect_no_anomalies():
    detector = AnomalyDetector()
    overview = {
        "domain": {
            "task": {"by_domain_env": [{"domain": "core", "environment": "sandbox", "tasks": 10, "success_rate": 0.95}]},
            "actions": {"by_domain_env_action": [{"action_type": "llm_call", "domain": "core", "requests": 20, "allow_rate": 0.98}]}
        },
        "memory": {
            "events": {"recall": {"avg_latency_ms": 100.0}},
            "embedding_failure_rate": 0.01
        },
        "patches": {"by_status": {"applied": 5, "needs_review": 1}}
    }
    anomalies = detector.detect(overview)
    assert len(anomalies) == 0

def test_detect_task_failure_spike():
    detector = AnomalyDetector(llm_error_rate_threshold=0.2)
    overview = {
        "domain": {
            "task": {"by_domain_env": [{"domain": "core", "environment": "sandbox", "tasks": 10, "success_rate": 0.4}]},
            "actions": {"by_domain_env_action": []}
        },
        "memory": {},
        "patches": {}
    }
    anomalies = detector.detect(overview)
    assert len(anomalies) == 1
    assert anomalies[0].kind == "task_failure_spike"
    assert anomalies[0].severity == "high"

def test_detect_memory_latency_spike():
    detector = AnomalyDetector(memory_latency_ms_threshold=2000.0)
    overview = {
        "domain": {},
        "memory": {
            "events": {"recall": {"avg_latency_ms": 5000.0}},
            "embedding_failure_rate": 0.0
        },
        "patches": {}
    }
    anomalies = detector.detect(overview)
    assert len(anomalies) == 1
    assert anomalies[0].kind == "memory_latency_spike"

def test_detect_patchflow_degraded():
    detector = AnomalyDetector(patchflow_blocked_ratio_threshold=0.5)
    overview = {
        "domain": {},
        "memory": {},
        "patches": {"by_status": {"blocked": 3, "applied": 1, "rejected": 2}}
    }
    anomalies = detector.detect(overview)
    assert len(anomalies) == 1
    assert anomalies[0].kind == "patchflow_health_degraded"

def test_detect_policy_denial_spike():
    detector = AnomalyDetector(denial_rate_threshold=0.3)
    overview = {
        "domain": {
            "actions": {"by_domain_env_action": [{"action_type": "llm_call", "domain": "core", "requests": 20, "allow_rate": 0.5}]}
        },
        "memory": {},
        "patches": {}
    }
    anomalies = detector.detect(overview)
    assert len(anomalies) == 1
    assert anomalies[0].kind == "policy_denial_spike"


def test_detect_lease_drift_contention_and_fencing():
    detector = AnomalyDetector(
        lease_expiring_count_threshold=2,
        lease_contention_events_threshold=2,
        lease_fencing_conflicts_threshold=1,
    )
    overview = {
        "domain": {},
        "memory": {},
        "patches": {},
        "communication": {
            "leases": {
                "expired_count": 1,
                "expiring_soon_count": 3,
                "contention_events_recent": 3,
                "fencing_conflicts_recent": 2,
            }
        },
    }
    anomalies = detector.detect(overview)
    kinds = {a.kind for a in anomalies}
    assert "lease_renew_drift" in kinds
    assert "lease_contention_spike" in kinds
    assert "lease_fencing_conflict_spike" in kinds


def test_detect_dead_letter_growth_trend():
    detector = AnomalyDetector(dead_letter_growth_ratio_threshold=1.5, dead_letter_recent_min=3)
    overview = {
        "domain": {},
        "memory": {},
        "patches": {},
        "communication": {
            "dead_letters": {
                "trend": {
                    "recent_count": 6,
                    "previous_count": 2,
                    "growth_ratio": 3.0,
                }
            }
        },
    }
    anomalies = detector.detect(overview)
    assert any(a.kind == "dead_letter_growth_trend" for a in anomalies)
