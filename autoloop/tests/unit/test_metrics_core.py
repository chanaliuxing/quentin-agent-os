import pytest
import time
from prometheus_client import REGISTRY
from app.observability.metrics import (
    workflow_duration_seconds,
    workflow_total,
    workflow_active,
    agent_execution_duration_seconds,
    agent_execution_total,
    agent_errors_total,
    cli_call_duration_seconds,
    cli_errors_total,
    git_conflicts_total,
    planning_rounds,
    dev_qa_rounds,
    MetricsTimer,
    MetricsCollector,
    start_metrics_server,
    classify_error,
)


def test_workflow_metrics_exist():
    assert workflow_duration_seconds._name == "autoloop_workflow_duration_seconds"
    assert workflow_total._name == "autoloop_workflow"
    assert workflow_active._name == "autoloop_workflow_active"


def test_agent_metrics_exist():
    assert agent_execution_duration_seconds._name == "autoloop_agent_execution_duration_seconds"
    assert agent_execution_total._name == "autoloop_agent_execution"
    assert agent_errors_total._name == "autoloop_agent_errors"


def test_cli_metrics_exist():
    assert cli_call_duration_seconds._name == "autoloop_cli_call_duration_seconds"
    assert cli_errors_total._name == "autoloop_cli_errors"


def test_git_metrics_exist():
    assert git_conflicts_total._name == "autoloop_git_conflicts"


def test_loop_metrics_exist():
    assert planning_rounds._name == "autoloop_planning_rounds"
    assert dev_qa_rounds._name == "autoloop_dev_qa_rounds"


def test_workflow_duration_labels():
    metric_labels = workflow_duration_seconds._labelnames
    assert "phase" in metric_labels
    assert "status" in metric_labels


def test_agent_execution_labels():
    metric_labels = agent_execution_duration_seconds._labelnames
    assert "agent_role" in metric_labels
    assert "runner_type" in metric_labels
    assert "status" in metric_labels


def test_cli_call_labels():
    metric_labels = cli_call_duration_seconds._labelnames
    assert "cli_type" in metric_labels
    assert "agent_role" in metric_labels


def test_git_conflicts_labels():
    metric_labels = git_conflicts_total._labelnames
    assert "phase_id" in metric_labels
    assert "risk_level" in metric_labels


def test_planning_rounds_labels():
    metric_labels = planning_rounds._labelnames
    assert "phase" in metric_labels
    assert len(metric_labels) == 1


def test_workflow_histogram_buckets():
    expected_buckets = [60, 300, 600, 1800, 3600, 7200, 14400]
    actual_buckets = [
        b
        for b in workflow_duration_seconds._upper_bounds
        if b != float("inf")
    ]
    assert actual_buckets == expected_buckets


def test_agent_histogram_buckets():
    expected_buckets = [1, 5, 10, 30, 60, 120, 300, 600, 1800]
    actual_buckets = [
        b
        for b in agent_execution_duration_seconds._upper_bounds
        if b != float("inf")
    ]
    assert actual_buckets == expected_buckets


def test_cli_histogram_buckets():
    expected_buckets = [1, 5, 10, 30, 60, 120, 300, 600]
    actual_buckets = [
        b
        for b in cli_call_duration_seconds._upper_bounds
        if b != float("inf")
    ]
    assert actual_buckets == expected_buckets


def test_planning_rounds_histogram_buckets():
    expected_buckets = [1, 2, 3, 4, 5, 10]
    actual_buckets = [
        b
        for b in planning_rounds._upper_bounds
        if b != float("inf")
    ]
    assert actual_buckets == expected_buckets


def test_metrics_timer_context_manager():
    with MetricsTimer() as timer:
        assert timer.start_time > 0
        time.sleep(0.1)

    assert timer.end_time > timer.start_time
    assert timer.duration_seconds >= 0.1
    assert timer.duration_seconds < 0.2


def test_metrics_timer_duration_property():
    timer = MetricsTimer()
    timer.start_time = 100.0
    timer.end_time = 105.5
    assert timer.duration_seconds == 5.5


def test_metrics_timer_duration_before_exit():
    timer = MetricsTimer()
    timer.start_time = time.time()
    time.sleep(0.05)
    duration = timer.duration_seconds
    assert duration >= 0.05


def test_workflow_counter_increment():
    initial_value = workflow_total.labels(phase="phase_01", status="completed")._value.get()
    workflow_total.labels(phase="phase_01", status="completed").inc()
    final_value = workflow_total.labels(phase="phase_01", status="completed")._value.get()
    assert final_value == initial_value + 1


def test_workflow_gauge_set():
    workflow_active.labels(phase="phase_01").set(5)
    value = workflow_active.labels(phase="phase_01")._value.get()
    assert value == 5


def test_agent_errors_increment():
    initial_value = agent_errors_total.labels(
        agent_role="dev", error_type="timeout"
    )._value.get()
    agent_errors_total.labels(agent_role="dev", error_type="timeout").inc()
    final_value = agent_errors_total.labels(
        agent_role="dev", error_type="timeout"
    )._value.get()
    assert final_value == initial_value + 1


def test_workflow_duration_observe():
    workflow_duration_seconds.labels(phase="phase_test", status="completed").observe(120.5)
    metric = workflow_duration_seconds.labels(phase="phase_test", status="completed")
    assert metric._sum.get() >= 120.5


def test_agent_execution_duration_observe():
    agent_execution_duration_seconds.labels(
        agent_role="dev", runner_type="mock", status="success"
    ).observe(45.2)
    metric = agent_execution_duration_seconds.labels(
        agent_role="dev", runner_type="mock", status="success"
    )
    assert metric._sum.get() >= 45.2


def test_metrics_registered_in_registry():
    collector_names = [
        collector._name
        for collector in REGISTRY._collector_to_names.keys()
        if hasattr(collector, "_name")
    ]

    assert "autoloop_workflow_duration_seconds" in collector_names
    assert "autoloop_workflow" in collector_names
    assert "autoloop_workflow_active" in collector_names
    assert "autoloop_agent_execution_duration_seconds" in collector_names
    assert "autoloop_agent_execution" in collector_names
    assert "autoloop_agent_errors" in collector_names
    assert "autoloop_cli_call_duration_seconds" in collector_names
    assert "autoloop_cli_errors" in collector_names
    assert "autoloop_git_conflicts" in collector_names
    assert "autoloop_planning_rounds" in collector_names
    assert "autoloop_dev_qa_rounds" in collector_names


def test_all_metrics_have_autoloop_prefix():
    metric_names = [
        workflow_duration_seconds._name,
        workflow_total._name,
        workflow_active._name,
        agent_execution_duration_seconds._name,
        agent_execution_total._name,
        agent_errors_total._name,
        cli_call_duration_seconds._name,
        cli_errors_total._name,
        git_conflicts_total._name,
        planning_rounds._name,
        dev_qa_rounds._name,
    ]

    for name in metric_names:
        assert name.startswith("autoloop_"), f"Metric {name} missing autoloop_ prefix"


def test_metrics_collector_record_agent_execution():
    MetricsCollector.record_agent_execution(
        agent_role="dev",
        runner_type="mock",
        status="success",
        duration_seconds=10.5,
    )

    samples = agent_execution_duration_seconds.collect()[0].samples
    sample_names = [s.name for s in samples]
    assert any("autoloop_agent_execution_duration_seconds" in name for name in sample_names)


def test_metrics_collector_record_workflow():
    MetricsCollector.record_workflow(
        phase="phase_01",
        status="completed",
        duration_seconds=120.0,
    )

    samples = workflow_duration_seconds.collect()[0].samples
    sample_names = [s.name for s in samples]
    assert any("autoloop_workflow_duration_seconds" in name for name in sample_names)


def test_metrics_collector_workflow_active():
    initial_value = workflow_active.labels(phase="phase_test_active")._value.get()

    MetricsCollector.increment_workflow_active("phase_test_active")
    after_inc = workflow_active.labels(phase="phase_test_active")._value.get()
    assert after_inc == initial_value + 1

    MetricsCollector.decrement_workflow_active("phase_test_active")
    after_dec = workflow_active.labels(phase="phase_test_active")._value.get()
    assert after_dec == initial_value


def test_metrics_collector_increment_errors():
    initial_value = agent_errors_total.labels(
        agent_role="dev_test", error_type="timeout_test"
    )._value.get()

    MetricsCollector.increment_errors(
        agent_role="dev_test",
        error_type="timeout_test",
    )

    final_value = agent_errors_total.labels(
        agent_role="dev_test", error_type="timeout_test"
    )._value.get()
    assert final_value == initial_value + 1


def test_metrics_collector_cli_call():
    MetricsCollector.record_cli_call(
        cli_type="codex",
        agent_role="dev",
        duration_seconds=5.0,
    )

    samples = cli_call_duration_seconds.collect()[0].samples
    sample_names = [s.name for s in samples]
    assert any("autoloop_cli_call_duration_seconds" in name for name in sample_names)


def test_metrics_collector_cli_errors():
    initial_value = cli_errors_total.labels(
        cli_type="codex_test", error_type="rate_limit_test"
    )._value.get()

    MetricsCollector.increment_cli_errors(
        cli_type="codex_test",
        error_type="rate_limit_test",
    )

    final_value = cli_errors_total.labels(
        cli_type="codex_test", error_type="rate_limit_test"
    )._value.get()
    assert final_value == initial_value + 1


def test_metrics_collector_git_conflicts():
    initial_value = git_conflicts_total.labels(
        phase_id="phase_test_git", risk_level="high"
    )._value.get()

    MetricsCollector.increment_conflicts(
        phase_id="phase_test_git",
        risk_level="high",
        count=2,
    )

    final_value = git_conflicts_total.labels(
        phase_id="phase_test_git", risk_level="high"
    )._value.get()
    assert final_value == initial_value + 2


def test_metrics_collector_planning_rounds():
    MetricsCollector.record_planning_rounds(
        phase="phase_01",
        rounds=3,
    )

    samples = planning_rounds.collect()[0].samples
    sample_names = [s.name for s in samples]
    assert any("autoloop_planning_rounds" in name for name in sample_names)


def test_metrics_collector_dev_qa_rounds():
    MetricsCollector.record_dev_qa_rounds(
        phase="phase_01",
        module="auth",
        rounds=2,
    )

    samples = dev_qa_rounds.collect()[0].samples
    sample_names = [s.name for s in samples]
    assert any("autoloop_dev_qa_rounds" in name for name in sample_names)


def test_classify_error_timeout():
    exc = TimeoutError("Request timed out")
    assert classify_error(exc) == "timeout"


def test_classify_error_rate_limit():
    exc = Exception("Rate limit exceeded (429)")
    assert classify_error(exc) == "rate_limit"


def test_classify_error_api_error():
    exc = Exception("API error 401 Unauthorized")
    assert classify_error(exc) == "api_error"


def test_classify_error_api_error_403():
    exc = Exception("403 Forbidden")
    assert classify_error(exc) == "api_error"


def test_classify_error_network():
    exc = Exception("Network connection failed")
    assert classify_error(exc) == "network_error"


def test_classify_error_unknown():
    exc = ValueError("Invalid value")
    assert classify_error(exc) == "valueerror"
