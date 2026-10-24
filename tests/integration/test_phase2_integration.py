"""
Integration test for Phase 2 multi-strategy system.

Tests the actual strategy manager with real subprocess calls and file operations.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path
from datetime import datetime, UTC

import pytest

from meta_agent.self_programming.strategy import EvolutionStrategyManager
from meta_agent.self_programming.metrics_store import JsonlMetricsStore
from meta_agent.self_programming.quality_evaluator import CodeQualityEvaluator


class TestPhase2Integration:
    """Integration tests for Phase 2 multi-strategy system."""

    def test_evolution_manager_initializes(self, tmp_path):
        """Test that EvolutionStrategyManager can be instantiated."""
        metrics_store = JsonlMetricsStore(repo_root=tmp_path)
        manager = EvolutionStrategyManager(
            metrics_store=metrics_store,
            repo_root=str(tmp_path),
        )

        assert manager.coverage_threshold == 0.80
        assert manager.complexity_threshold == 10
        # P5: Align with latest policy weights
        assert manager.weights["retry_failed"] >= 0.5

    def test_generate_tasks_with_no_data(self, tmp_path):
        """Test task generation when no failures/coverage/complexity data exists."""
        metrics_store = JsonlMetricsStore(repo_root=tmp_path)
        manager = EvolutionStrategyManager(
            metrics_store=metrics_store,
            repo_root=str(tmp_path),
        )

        tasks = manager.generate_tasks(limit=10)

        # Should return empty list, not crash
        assert isinstance(tasks, list)

    def test_generate_retry_tasks_with_real_failures(self, tmp_path):
        """Test that retry tasks are generated from real failure data."""
        metrics_store = JsonlMetricsStore(repo_root=tmp_path)

        # Add a real failure
        metrics_store.log_run({
            "task_id": "test_integration_task",
            "status": "test_fail",
            "timestamp": datetime.now(UTC),
            "raw_test_output": "Integration test failure: connection refused",
            "task_payload": {
                "description": "Fix database connection",
                "origin": "bugfix",
                "repo_root": str(tmp_path),
                "related_files": ["db/connection.py"],
                "context_summary": "DB connection fails on startup",
                "constraints": {},
                "acceptance_criteria": ["Connection succeeds"],
            },
        })

        manager = EvolutionStrategyManager(
            metrics_store=metrics_store,
            repo_root=str(tmp_path),
        )

        tasks = manager.generate_tasks(limit=10)

        # Should generate at least 1 retry task
        assert len(tasks) >= 1
        assert any("retry_of" in task.task_id for task in tasks)

        # Check retry task content
        retry_tasks = [t for t in tasks if "retry_of" in t.task_id]
        assert "connection refused" in retry_tasks[0].description

    def test_radon_executable_exists(self):
        """Test that radon is actually installed and executable."""
        try:
            result = subprocess.run(
                ["radon", "--version"],
                capture_output=True,
                text=True,
            )
            assert result.returncode == 0
            # P5: Radon 6+ only outputs version number
            assert len(result.stdout.strip()) > 0
        except FileNotFoundError:
            pytest.skip("radon not installed in current environment")

    def test_pytest_cov_available(self):
        """Test that pytest-cov is installed."""
        try:
            import pytest_cov
            # If import succeeds, pytest-cov is available
            assert True
        except ImportError:
            pytest.skip("pytest-cov not installed in current environment")

    def test_quality_evaluator_with_real_code(self, tmp_path):
        """Test CodeQualityEvaluator with real Python file."""
        # Create a test file
        test_file = tmp_path / "sample.py"
        test_file.write_text('''
def hello(name: str) -> str:
    """Greet someone by name."""
    return f"Hello, {name}!"
''')

        evaluator = CodeQualityEvaluator()
        metrics = evaluator.evaluate_file(test_file)

        assert metrics.syntax_valid is True
        assert metrics.overall_score > 0.5  # Should have decent score
        assert metrics.complexity_score > 0.0
        assert metrics.style_score > 0.0

    def test_quality_evaluator_detects_syntax_error(self):
        """Test that evaluator detects syntax errors."""
        bad_code = """
def broken(:
    return "missing parameter name"
"""

        evaluator = CodeQualityEvaluator()
        metrics = evaluator.evaluate_code(bad_code)

        assert metrics.syntax_valid is False
        assert metrics.overall_score == 0.0
        assert "syntax_error" in metrics.details

    def test_quality_evaluator_assesses_complexity(self):
        """Test that evaluator uses radon to assess complexity."""
        try:
            # Check if radon is available
            subprocess.run(["radon", "--version"], capture_output=True, check=True)
        except (FileNotFoundError, subprocess.CalledProcessError):
            pytest.skip("radon not available in current environment")

        complex_code = '''
def complex_function(x):
    if x > 10:
        if x > 20:
            if x > 30:
                if x > 40:
                    return "very complex"
                else:
                    return "complex"
            else:
                return "moderate"
        else:
            return "simple"
    else:
        return "very simple"
'''

        evaluator = CodeQualityEvaluator(max_acceptable_complexity=5)
        metrics = evaluator.evaluate_code(complex_code)

        assert metrics.syntax_valid is True
        # If radon is available, should have complexity metrics
        if "radon_exception" not in metrics.details:
            assert "avg_complexity" in metrics.details
            # P5: Compatibility with Radon 6+
            assert metrics.details["avg_complexity"] >= 5

    def test_quality_evaluator_assesses_style(self):
        """Test that evaluator assesses code style."""
        good_style = '''
def calculate_total(items: list[dict]) -> float:
    """
    Calculate total price from list of items.

    Args:
        items: List of item dictionaries with 'price' key

    Returns:
        Total price as float
    """
    total = 0.0
    for item in items:
        total += item.get("price", 0.0)

    return total
'''

        bad_style = '''
def f(x):
    return sum([i["p"] for i in x])
'''

        evaluator = CodeQualityEvaluator()

        good_metrics = evaluator.evaluate_code(good_style)
        bad_metrics = evaluator.evaluate_code(bad_style)

        # Good style should score higher
        assert good_metrics.style_score > bad_metrics.style_score
        assert good_metrics.details["has_docstring"] is True
        assert bad_metrics.details["has_docstring"] is False

    def test_allocate_limits_distributes_correctly(self, tmp_path):
        """Test that task limits are allocated according to weights."""
        metrics_store = JsonlMetricsStore(repo_root=tmp_path)
        manager = EvolutionStrategyManager(
            metrics_store=metrics_store,
            repo_root=str(tmp_path),
            strategy_weights={
                "retry_failed": 0.5,
                "find_untested_code": 0.3,
                "find_complex_code": 0.2,
            },
        )

        limits = manager._allocate_limits(total_limit=10)

        # Should allocate approximately according to weights
        assert limits["retry_failed"] >= 4  # At least 40% of 10
        assert limits["find_untested_code"] >= 2  # At least 20% of 10
        assert limits["find_complex_code"] >= 1  # At least 10% of 10
        assert sum(limits.values()) == 10

    def test_demo_script_runs(self):
        """Test that demo script executes without errors."""
        import sys
        import os

        # Check if meta_agent package is available
        try:
            import meta_agent
        except ImportError:
            pytest.skip("meta_agent package not installed (run 'pip install -e .')")

        repo_root = Path(__file__).parent.parent.parent
        script_path = repo_root / "scripts" / "demo_multi_strategy.py"

        if not script_path.exists():
            pytest.skip("Demo script not found")

        # Set PYTHONPATH to repo root so script can import meta_agent
        env = os.environ.copy()
        env["PYTHONPATH"] = str(repo_root)

        # Use the same Python interpreter that's running tests
        result = subprocess.run(
            [
                sys.executable,
                str(script_path),
                "--limit", "3",
                "--dry-run",
            ],
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=30,
            env=env,
        )

        # Should complete successfully (exit code 0)
        assert result.returncode == 0, f"Script failed:\nstdout: {result.stdout}\nstderr: {result.stderr}"
        # Check either stdout or stderr (logging goes to stderr)
        output = result.stdout + result.stderr
        assert "Multi-Strategy Evolution Manager Demo" in output

    def test_backward_compatibility_simple_manager(self, tmp_path):
        """Test that SimpleEvolutionStrategyManager still works."""
        from meta_agent.self_programming.strategy import SimpleEvolutionStrategyManager

        metrics_store = JsonlMetricsStore(repo_root=tmp_path)

        # Add a failure
        metrics_store.log_run({
            "task_id": "old_task",
            "status": "test_fail",
            "timestamp": datetime.now(UTC),
            "raw_test_output": "Old failure",
            "task_payload": {
                "description": "Old test",
                "origin": "bugfix",
                "repo_root": str(tmp_path),
                "related_files": [],
                "context_summary": "",
                "constraints": {},
                "acceptance_criteria": [],
            },
        })

        # Old API should still work
        manager = SimpleEvolutionStrategyManager(metrics_store=metrics_store)
        tasks = manager.generate_tasks(limit=10)

        assert len(tasks) == 1
        assert "retry_of_old_task" == tasks[0].task_id
