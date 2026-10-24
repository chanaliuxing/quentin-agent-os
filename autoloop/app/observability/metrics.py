from __future__ import annotations

import time
import os
import logging
from typing import TYPE_CHECKING
from prometheus_client import Counter, Histogram, Gauge, start_http_server, REGISTRY, push_to_gateway

if TYPE_CHECKING:
    pass

LOG = logging.getLogger("metrics")

GRAFANA_CLOUD_ENABLED = os.getenv("GRAFANA_CLOUD_ENABLED", "false").lower() == "true"
GRAFANA_CLOUD_PROMETHEUS_URL = os.getenv("GRAFANA_CLOUD_PROMETHEUS_URL", "")
GRAFANA_CLOUD_PROMETHEUS_USER = os.getenv("GRAFANA_CLOUD_PROMETHEUS_USER", "")
GRAFANA_CLOUD_API_KEY = os.getenv("GRAFANA_CLOUD_API_KEY", "")

workflow_duration_seconds = Histogram(
    "autoloop_workflow_duration_seconds",
    "Workflow total duration in seconds",
    ["phase", "status"],
    buckets=[60, 300, 600, 1800, 3600, 7200, 14400],
)

workflow_total = Counter(
    "autoloop_workflow_total",
    "Total number of workflows executed",
    ["phase", "status"],
)

workflow_active = Gauge(
    "autoloop_workflow_active",
    "Number of currently active workflows",
    ["phase"],
)

agent_execution_duration_seconds = Histogram(
    "autoloop_agent_execution_duration_seconds",
    "Agent execution duration in seconds",
    ["agent_role", "runner_type", "status"],
    buckets=[1, 5, 10, 30, 60, 120, 300, 600, 1800],
)

agent_execution_total = Counter(
    "autoloop_agent_execution_total",
    "Total number of agent executions",
    ["agent_role", "runner_type", "status"],
)

agent_errors_total = Counter(
    "autoloop_agent_errors_total",
    "Total number of agent errors",
    ["agent_role", "error_type"],
)

cli_call_duration_seconds = Histogram(
    "autoloop_cli_call_duration_seconds",
    "CLI API call duration in seconds",
    ["cli_type", "agent_role"],
    buckets=[1, 5, 10, 30, 60, 120, 300, 600],
)

cli_errors_total = Counter(
    "autoloop_cli_errors_total",
    "Total number of CLI errors",
    ["cli_type", "error_type"],
)

git_conflicts_total = Counter(
    "autoloop_git_conflicts_total",
    "Total number of git conflicts detected",
    ["phase_id", "risk_level"],
)

planning_rounds = Histogram(
    "autoloop_planning_rounds",
    "Number of planning rounds in Planner-Reviewer loop",
    ["phase"],
    buckets=[1, 2, 3, 4, 5, 10],
)

dev_qa_rounds = Histogram(
    "autoloop_dev_qa_rounds",
    "Number of Dev-QA iteration rounds",
    ["phase", "module"],
    buckets=[1, 2, 3, 4, 5, 10],
)

task_generation_duration_seconds = Histogram(
    "autoloop_task_generation_duration_seconds",
    "Task generation duration in seconds",
    ["phase", "agent_role"],
    buckets=[1, 5, 10, 30, 60, 120, 300],
)

result_collection_duration_seconds = Histogram(
    "autoloop_result_collection_duration_seconds",
    "Result collection duration in seconds",
    ["phase", "agent_role"],
    buckets=[1, 5, 10, 30, 60, 120],
)

integration_test_duration_seconds = Histogram(
    "autoloop_integration_test_duration_seconds",
    "Integration test execution duration",
    ["phase", "status"],
    buckets=[5, 10, 30, 60, 120, 300, 600],
)


class MetricsCollector:
    @staticmethod
    def record_agent_execution(
        agent_role: str,
        runner_type: str,
        status: str,
        duration_seconds: float,
    ) -> None:
        agent_execution_duration_seconds.labels(
            agent_role=agent_role,
            runner_type=runner_type,
            status=status,
        ).observe(duration_seconds)
        agent_execution_total.labels(
            agent_role=agent_role,
            runner_type=runner_type,
            status=status,
        ).inc()
        MetricsCollector._push_to_grafana()

    @staticmethod
    def record_cli_call(
        cli_type: str,
        agent_role: str,
        duration_seconds: float,
    ) -> None:
        cli_call_duration_seconds.labels(
            cli_type=cli_type,
            agent_role=agent_role,
        ).observe(duration_seconds)
        MetricsCollector._push_to_grafana()

    @staticmethod
    def record_workflow(phase: str, status: str, duration_seconds: float) -> None:
        workflow_duration_seconds.labels(phase=phase, status=status).observe(duration_seconds)
        workflow_total.labels(phase=phase, status=status).inc()
        MetricsCollector._push_to_grafana()

    @staticmethod
    def increment_workflow_active(phase: str) -> None:
        workflow_active.labels(phase=phase).inc()
        MetricsCollector._push_to_grafana()

    @staticmethod
    def decrement_workflow_active(phase: str) -> None:
        workflow_active.labels(phase=phase).dec()
        MetricsCollector._push_to_grafana()

    @staticmethod
    def increment_errors(agent_role: str, error_type: str) -> None:
        agent_errors_total.labels(
            agent_role=agent_role,
            error_type=error_type,
        ).inc()
        MetricsCollector._push_to_grafana()

    @staticmethod
    def increment_cli_errors(cli_type: str, error_type: str) -> None:
        cli_errors_total.labels(
            cli_type=cli_type,
            error_type=error_type,
        ).inc()
        MetricsCollector._push_to_grafana()

    @staticmethod
    def increment_conflicts(phase_id: str, risk_level: str, count: int = 1) -> None:
        git_conflicts_total.labels(
            phase_id=phase_id,
            risk_level=risk_level,
        ).inc(count)
        MetricsCollector._push_to_grafana()

    @staticmethod
    def record_planning_rounds(phase: str, rounds: int) -> None:
        planning_rounds.labels(phase=phase).observe(rounds)
        MetricsCollector._push_to_grafana()

    @staticmethod
    def record_dev_qa_rounds(phase: str, module: str, rounds: int) -> None:
        dev_qa_rounds.labels(phase=phase, module=module).observe(rounds)
        MetricsCollector._push_to_grafana()

    @staticmethod
    def _push_to_grafana() -> None:
        if not GRAFANA_CLOUD_ENABLED:
            return

        if not GRAFANA_CLOUD_PROMETHEUS_URL or not GRAFANA_CLOUD_PROMETHEUS_USER or not GRAFANA_CLOUD_API_KEY:
            return

        try:
            push_to_gateway(
                GRAFANA_CLOUD_PROMETHEUS_URL,
                job='autoloop',
                registry=REGISTRY,
                timeout=5
            )
        except Exception as e:
            LOG.debug("Failed to push to Grafana Cloud: %s", e)


def start_metrics_server(port: int = 9090, addr: str = "0.0.0.0") -> None:
    start_http_server(port, addr=addr, registry=REGISTRY)
    LOG.info("Metrics server started on %s:%d", addr, port)


class MetricsTimer:
    def __init__(self) -> None:
        self.start_time: float = 0.0
        self.end_time: float = 0.0

    def __enter__(self) -> MetricsTimer:
        self.start_time = time.time()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.end_time = time.time()

    @property
    def duration_seconds(self) -> float:
        return (
            self.end_time - self.start_time
            if self.end_time > 0
            else time.time() - self.start_time
        )


def classify_error(exc: Exception) -> str:
    error_type = type(exc).__name__
    error_msg = str(exc).lower()

    if "timeout" in error_msg or "timed out" in error_msg:
        return "timeout"
    elif "rate limit" in error_msg or "429" in error_msg:
        return "rate_limit"
    elif "api" in error_msg or "401" in error_msg or "403" in error_msg:
        return "api_error"
    elif "network" in error_msg or "connection" in error_msg:
        return "network_error"
    else:
        return error_type.lower()
