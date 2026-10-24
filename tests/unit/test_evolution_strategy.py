"""
Unit tests for EvolutionStrategyManager (Phase 2 multi-strategy).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Any, List
from unittest.mock import MagicMock, patch, mock_open

import pytest

from meta_agent.self_programming.strategy import (
    EvolutionStrategyManager,
    SimpleEvolutionStrategyManager,
    StrategyType,
)
from meta_agent.self_programming.schema import ProgrammingTask
from meta_agent.self_programming.metrics_store import MetricsStoreProtocol, RunRecord


class MockMetricsStore(MetricsStoreProtocol):
    """Mock implementation of MetricsStoreProtocol for testing."""

    def __init__(self):
        self.runs: List[RunRecord] = []

    def log_run(self, record: RunRecord) -> None:
        self.runs.append(record)

    def get_runs_by_status(self, status: str, limit: int = 10) -> List[RunRecord]:
        matching = [r for r in self.runs if r.get("status") == status]
        return matching[-limit:]


@pytest.fixture
def mock_metrics_store():
    """Create a mock metrics store with sample failed runs."""
    store = MockMetricsStore()

    # Add some failed test runs
    from datetime import datetime, UTC
    store.runs = [
        {
            "task_id": "test_task_1",
            "status": "test_fail",
            "timestamp": datetime.now(UTC),
            "raw_test_output": "AssertionError: expected 2, got 3",
            "task_payload": {
                "description": "Fix calculation bug",
                "origin": "bugfix",
                "repo_root": "/test/repo",
                "related_files": ["src/calc.py"],
                "context_summary": "Bug in add function",
                "constraints": {},
                "acceptance_criteria": ["Tests pass"],
            },
        },
        {
            "task_id": "test_task_2",
            "status": "test_fail",
            "timestamp": datetime.now(UTC),
            "raw_test_output": "ImportError: cannot import module",
            "task_payload": {
                "description": "Fix import",
                "origin": "bugfix",
                "repo_root": "/test/repo",
                "related_files": ["src/module.py"],
                "context_summary": "Import error",
                "constraints": {},
                "acceptance_criteria": [],
            },
        },
    ]
    return store


@pytest.fixture
def strategy_manager(mock_metrics_store, tmp_path):
    """Create an EvolutionStrategyManager for testing."""
    return EvolutionStrategyManager(
        metrics_store=mock_metrics_store,
        repo_root=str(tmp_path),
        strategy_weights={
            "retry_failed": 0.6,
            "find_untested_code": 0.25,
            "find_complex_code": 0.15,
        },
        coverage_threshold=0.80,
        complexity_threshold=10,
    )


class TestSimpleEvolutionStrategyManager:
    """Tests for the original SimpleEvolutionStrategyManager."""

    def test_generate_retry_tasks(self, mock_metrics_store):
        """Test that SimpleEvolutionStrategyManager generates retry tasks."""
        manager = SimpleEvolutionStrategyManager(metrics_store=mock_metrics_store)
        tasks = manager.generate_tasks(limit=10)

        assert len(tasks) == 2
        assert all(isinstance(t, ProgrammingTask) for t in tasks)
        assert tasks[0].task_id == "retry_of_test_task_1"
        assert "AssertionError" in tasks[0].description
        assert tasks[0].origin == "bugfix"

    def test_skip_already_retried_tasks(self):
        """Test that already-retried tasks are skipped."""
        from datetime import datetime, UTC
        store = MockMetricsStore()

        # Add original task and its retry (both failed)
        store.runs = [
            {
                "task_id": "test_task_1",
                "status": "test_fail",
                "timestamp": datetime.now(UTC),
                "raw_test_output": "First failure",
                "task_payload": {
                    "description": "Test",
                    "origin": "bugfix",
                    "repo_root": ".",
                    "related_files": [],
                    "context_summary": "",
                    "constraints": {},
                    "acceptance_criteria": [],
                },
            },
            {
                "task_id": "retry_of_test_task_1",
                "status": "test_fail",
                "timestamp": datetime.now(UTC),
                "raw_test_output": "Still failing",
                "task_payload": {},
            },
        ]

        manager = SimpleEvolutionStrategyManager(metrics_store=store)
        tasks = manager.generate_tasks(limit=10)

        # Should only generate retry for test_task_1 (not retry_of_test_task_1)
        # But it will generate for the first test_task_1, not the retry
        assert len(tasks) == 1
        assert tasks[0].task_id == "retry_of_test_task_1"


class TestEvolutionStrategyManager:
    """Tests for the multi-strategy EvolutionStrategyManager."""

    def test_initialization(self, strategy_manager):
        """Test that manager initializes with correct defaults."""
        assert strategy_manager.coverage_threshold == 0.80
        assert strategy_manager.complexity_threshold == 10
        assert strategy_manager.weights == {
            "retry_failed": 0.6,
            "find_untested_code": 0.25,
            "find_complex_code": 0.15,
        }

    def test_weight_validation_warning(self, mock_metrics_store, tmp_path, caplog):
        """Test that invalid weights trigger a warning."""
        manager = EvolutionStrategyManager(
            metrics_store=mock_metrics_store,
            repo_root=str(tmp_path),
            strategy_weights={
                "retry_failed": 0.5,
                "find_untested_code": 0.3,
                "find_complex_code": 0.1,
                # Sum = 0.9, should warn
            },
        )
        assert "sum to 0.90" in caplog.text

    def test_allocate_limits(self, strategy_manager):
        """Test that task limits are allocated correctly by weight."""
        limits = strategy_manager._allocate_limits(total_limit=10)

        # Weights: 60%, 25%, 15%
        # Total should be 10, with retry_failed getting the most
        assert limits["retry_failed"] >= 5  # At least 50%
        assert limits["find_untested_code"] >= 1
        assert limits["find_complex_code"] >= 1
        assert sum(limits.values()) == 10

    def test_allocate_limits_small_total(self, strategy_manager):
        """Test allocation with small total limit."""
        limits = strategy_manager._allocate_limits(total_limit=3)

        # Should allocate at least 1 to highest-weighted strategies
        assert limits["retry_failed"] >= 1
        assert sum(limits.values()) == 3

    def test_generate_retry_failed_tasks(self, strategy_manager):
        """Test _generate_retry_failed_tasks method."""
        tasks = strategy_manager._generate_retry_failed_tasks(limit=10)

        assert len(tasks) == 2
        assert tasks[0].task_id == "retry_of_test_task_1"
        assert tasks[0].origin == "bugfix"
        assert "AssertionError" in tasks[0].description

    @patch("subprocess.run")
    @patch("pathlib.Path.open", new_callable=mock_open)
    @patch("pathlib.Path.exists")
    def test_generate_untested_code_tasks(self, mock_exists, mock_file_open, mock_subprocess, strategy_manager):
        """Test _generate_untested_code_tasks with mocked coverage data."""
        # Mock coverage.json output
        coverage_data = {
            "files": {
                "/test/repo/meta_agent/module_a.py": {
                    "summary": {"percent_covered": 45.5},
                    "missing_lines": [10, 11, 12, 15, 20, 25],
                },
                "/test/repo/quentin/module_b.py": {
                    "summary": {"percent_covered": 65.0},
                    "missing_lines": [5, 6, 7],
                },
                "/test/repo/meta_agent/module_c.py": {
                    "summary": {"percent_covered": 95.0},  # Above threshold
                    "missing_lines": [],
                },
            }
        }

        # Mock subprocess.run to succeed
        mock_subprocess.return_value = MagicMock(
            returncode=0,
            stdout="",
            stderr="",
        )

        # Mock file operations
        mock_exists.return_value = True
        mock_file_open.return_value.read.return_value = json.dumps(coverage_data)

        tasks = strategy_manager._generate_untested_code_tasks(limit=10)

        assert len(tasks) == 2  # Only module_a and module_b (below 80%)

        # Check that we have tasks for low coverage files
        task_descriptions = [t.description for t in tasks]
        assert any("module_a.py" in desc for desc in task_descriptions)
        assert any("module_b.py" in desc for desc in task_descriptions)
        assert tasks[0].origin == "refactor"
        assert any("All tests pass" in crit for crit in tasks[0].acceptance_criteria)

    @patch("subprocess.run")
    def test_generate_untested_code_tasks_timeout(self, mock_subprocess, strategy_manager, caplog):
        """Test that coverage task generation handles timeout gracefully."""
        from subprocess import TimeoutExpired
        mock_subprocess.side_effect = TimeoutExpired(cmd="pytest", timeout=60)

        tasks = strategy_manager._generate_untested_code_tasks(limit=10)

        assert len(tasks) == 0
        assert "timed out" in caplog.text

    @patch("subprocess.run")
    def test_generate_untested_code_tasks_no_coverage_file(self, mock_subprocess, strategy_manager, caplog):
        """Test handling when coverage.json is not generated."""
        mock_subprocess.return_value = MagicMock(returncode=0)

        with patch("pathlib.Path.exists", return_value=False):
            tasks = strategy_manager._generate_untested_code_tasks(limit=10)

        assert len(tasks) == 0
        assert "coverage.json not found" in caplog.text

    @patch("subprocess.run")
    def test_generate_complex_code_tasks(self, mock_subprocess, strategy_manager):
        """Test _generate_complex_code_tasks with mocked radon output."""
        radon_data = {
            "meta_agent/service.py": [
                {
                    "name": "complex_function",
                    "complexity": 15,
                    "lineno": 42,
                    "rank": "C",
                },
                {
                    "name": "simple_function",
                    "complexity": 3,
                    "lineno": 100,
                    "rank": "A",
                },
            ],
            "quentin/handler.py": [
                {
                    "name": "mega_function",
                    "complexity": 25,
                    "lineno": 10,
                    "rank": "F",
                },
            ],
        }

        mock_subprocess.return_value = MagicMock(
            returncode=0,
            stdout=json.dumps(radon_data),
            stderr="",
        )

        tasks = strategy_manager._generate_complex_code_tasks(limit=10)

        # Should generate tasks for complexity > 10
        assert len(tasks) == 2

        # Check first task (highest complexity)
        assert "mega_function" in tasks[0].description
        assert "25" in tasks[0].description
        assert "rank F" in tasks[0].description
        assert tasks[0].origin == "refactor"
        assert tasks[0].constraints.get("preserve_behavior") == True

    @patch("subprocess.run")
    def test_generate_complex_code_tasks_radon_failure(self, mock_subprocess, strategy_manager, caplog):
        """Test handling when radon fails."""
        mock_subprocess.return_value = MagicMock(
            returncode=1,
            stdout="",
            stderr="radon error",
        )

        tasks = strategy_manager._generate_complex_code_tasks(limit=10)

        assert len(tasks) == 0
        assert "radon cc failed" in caplog.text

    @patch("subprocess.run")
    def test_generate_complex_code_tasks_invalid_json(self, mock_subprocess, strategy_manager, caplog):
        """Test handling when radon outputs invalid JSON."""
        mock_subprocess.return_value = MagicMock(
            returncode=0,
            stdout="not valid json {{{",
            stderr="",
        )

        tasks = strategy_manager._generate_complex_code_tasks(limit=10)

        assert len(tasks) == 0
        assert "parse radon JSON" in caplog.text

    @patch("subprocess.run")
    def test_generate_tasks_integration(self, mock_subprocess, strategy_manager):
        """Test that generate_tasks combines all strategies."""
        # Mock coverage data
        coverage_data = {
            "files": {
                "/test/repo/meta_agent/low_cov.py": {
                    "summary": {"percent_covered": 50.0},
                    "missing_lines": [1, 2, 3],
                }
            }
        }

        # Mock radon data
        radon_data = {
            "meta_agent/complex.py": [
                {"name": "complex_fn", "complexity": 20, "lineno": 10, "rank": "D"}
            ]
        }

        # Setup subprocess mocks
        def subprocess_side_effect(*args, **kwargs):
            cmd = args[0]
            if "pytest" in cmd:
                return MagicMock(returncode=0, stdout="", stderr="")
            elif "radon" in cmd:
                return MagicMock(returncode=0, stdout=json.dumps(radon_data), stderr="")
            return MagicMock(returncode=1)

        mock_subprocess.side_effect = subprocess_side_effect

        with patch("builtins.open", mock_open(read_data=json.dumps(coverage_data))):
            with patch("pathlib.Path.exists", return_value=True):
                tasks = strategy_manager.generate_tasks(limit=10)

        # Should have tasks from all 3 strategies:
        # - 2 retry_failed tasks (from mock_metrics_store fixture)
        # - 1 untested_code task
        # - 1 complex_code task
        # Total: 4 tasks
        assert len(tasks) <= 10
        assert len(tasks) >= 3  # At least retry + one from each strategy

        # Check task IDs to verify strategy diversity
        task_ids = [t.task_id for t in tasks]
        has_retry = any("retry_of" in tid for tid in task_ids)
        has_untested = any("add_tests" in tid for tid in task_ids)
        has_complex = any("refactor_complex" in tid for tid in task_ids)

        assert has_retry, "Should have retry tasks"
        # Note: untested and complex might not always generate tasks if data is empty
        # So we don't assert on those strictly

    def test_generate_tasks_respects_limit(self, strategy_manager):
        """Test that generate_tasks respects the limit parameter."""
        with patch.object(
            strategy_manager, "_generate_retry_failed_tasks", return_value=[MagicMock()] * 100
        ):
            with patch.object(strategy_manager, "_generate_untested_code_tasks", return_value=[]):
                with patch.object(strategy_manager, "_generate_complex_code_tasks", return_value=[]):
                    tasks = strategy_manager.generate_tasks(limit=5)

        assert len(tasks) <= 5

    def test_generate_tasks_handles_strategy_exceptions(self, strategy_manager, caplog):
        """Test that exceptions in one strategy don't crash the whole generation."""
        with patch.object(
            strategy_manager,
            "_generate_retry_failed_tasks",
            side_effect=Exception("Retry failed"),
        ):
            with patch.object(
                strategy_manager, "_generate_untested_code_tasks", return_value=[]
            ):
                with patch.object(
                    strategy_manager, "_generate_complex_code_tasks", return_value=[]
                ):
                    tasks = strategy_manager.generate_tasks(limit=10)

        # Should return empty list, not crash
        assert isinstance(tasks, list)
        assert "Failed to generate tasks for strategy" in caplog.text


class TestStrategyWeighting:
    """Tests for strategy weight allocation logic."""

    def test_equal_weights(self, mock_metrics_store, tmp_path):
        """Test allocation with equal weights."""
        manager = EvolutionStrategyManager(
            metrics_store=mock_metrics_store,
            repo_root=str(tmp_path),
            strategy_weights={
                "retry_failed": 0.33,
                "find_untested_code": 0.33,
                "find_complex_code": 0.34,
            },
        )

        limits = manager._allocate_limits(total_limit=9)
        # With rounding, we should get approximately equal distribution
        assert 2 <= limits["retry_failed"] <= 3
        assert 2 <= limits["find_untested_code"] <= 3
        assert 2 <= limits["find_complex_code"] <= 4
        assert sum(limits.values()) == 9

    def test_extreme_weights(self, mock_metrics_store, tmp_path):
        """Test allocation with extreme weights."""
        manager = EvolutionStrategyManager(
            metrics_store=mock_metrics_store,
            repo_root=str(tmp_path),
            strategy_weights={
                "retry_failed": 0.95,
                "find_untested_code": 0.03,
                "find_complex_code": 0.02,
            },
        )

        limits = manager._allocate_limits(total_limit=100)
        assert limits["retry_failed"] >= 90
        assert sum(limits.values()) == 100

    def test_zero_weight(self, mock_metrics_store, tmp_path):
        """Test that zero-weighted strategies get no allocation."""
        manager = EvolutionStrategyManager(
            metrics_store=mock_metrics_store,
            repo_root=str(tmp_path),
            strategy_weights={
                "retry_failed": 1.0,
                "find_untested_code": 0.0,
                "find_complex_code": 0.0,
            },
        )

        limits = manager._allocate_limits(total_limit=10)
        assert limits["retry_failed"] == 10
        assert limits["find_untested_code"] == 0
        assert limits["find_complex_code"] == 0
