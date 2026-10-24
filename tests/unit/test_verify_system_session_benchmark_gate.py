from __future__ import annotations

import verify_system


def test_session_benchmark_gate_disabled(monkeypatch) -> None:
    monkeypatch.setenv("QUENTIN_VERIFY_SESSION_BENCHMARK", "0")
    out = verify_system._audit_session_model_benchmark(repo_root=".")
    assert out == []


def test_session_benchmark_gate_threshold(monkeypatch) -> None:
    monkeypatch.setenv("QUENTIN_VERIFY_SESSION_BENCHMARK", "1")
    monkeypatch.setenv("QUENTIN_VERIFY_SESSION_BENCHMARK_MIN_SCORE", "0.95")
    monkeypatch.setenv("QUENTIN_VERIFY_SESSION_BENCHMARK_REQUIRE_PASS", "1")

    import quentin.benchmarks.session_model as sm

    monkeypatch.setattr(
        sm,
        "run_benchmark",
        lambda **kwargs: {
            "quality_score": 0.80,
            "pass": False,
            "summary": {"failed_keys": ["session_recovery"]},
        },
    )

    out = verify_system._audit_session_model_benchmark(repo_root=".")
    assert any("score_below_threshold" in s for s in out)
    assert any("report_failed" in s for s in out)


def test_session_benchmark_gate_pass(monkeypatch) -> None:
    monkeypatch.setenv("QUENTIN_VERIFY_SESSION_BENCHMARK", "1")
    monkeypatch.setenv("QUENTIN_VERIFY_SESSION_BENCHMARK_MIN_SCORE", "0.95")
    monkeypatch.setenv("QUENTIN_VERIFY_SESSION_BENCHMARK_REQUIRE_PASS", "1")

    import quentin.benchmarks.session_model as sm

    monkeypatch.setattr(
        sm,
        "run_benchmark",
        lambda **kwargs: {
            "quality_score": 1.0,
            "pass": True,
            "summary": {"failed_keys": []},
        },
    )

    out = verify_system._audit_session_model_benchmark(repo_root=".")
    assert out == []
