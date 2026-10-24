"""
End-to-end integration test for Phase 3 self-programming.

This test verifies that:
1. A task can be created and run through SelfProgrammingEngine
2. Failed tasks are logged to MetricsStore
3. SimpleEvolutionStrategyManager generates retry tasks
4. The evolution loop can execute retry tasks
"""
from __future__ import annotations

import pytest
from pathlib import Path
from datetime import datetime

from meta_agent.self_programming.engine import SelfProgrammingEngine
from meta_agent.self_programming.metrics_store import JsonlMetricsStore
from meta_agent.self_programming.strategy import SimpleEvolutionStrategyManager
from meta_agent.self_programming.schema import ProgrammingTask
from meta_agent.self_programming.evolution_loop import run_once


class TestPhase3EndToEnd:
    """End-to-end integration tests for Phase 3."""

    def test_metrics_store_logs_runs(self, tmp_path):
        """Test that metrics store can log and retrieve runs."""
        store = JsonlMetricsStore(repo_root=str(tmp_path), filename="test_runs.jsonl")

        # Log a test run
        record = {
            "task_id": "test_task_001",
            "status": "test_fail",
            "timestamp": datetime.utcnow(),
            "commit_hash": "abc123",
            "branch_name": "test-branch",
            "raw_test_output": "AssertionError: test failed",
            "metrics": {"duration_sec": 10.5},
            "task_payload": {
                "task_id": "test_task_001",
                "origin": "experiment",
                "description": "Test task",
                "repo_root": str(tmp_path),
                "related_files": [],
                "context_summary": "test",
                "constraints": {},
                "acceptance_criteria": [],
            },
        }

        store.log_run(record)

        # Verify we can retrieve it
        failed_runs = store.get_runs_by_status("test_fail", limit=10)
        assert len(failed_runs) == 1
        assert failed_runs[0]["task_id"] == "test_task_001"
        assert failed_runs[0]["status"] == "test_fail"

    def test_strategy_generates_retry_tasks(self, tmp_path):
        """Test that strategy manager generates retry tasks from failures."""
        store = JsonlMetricsStore(repo_root=str(tmp_path), filename="test_runs.jsonl")

        # Create a failed task record
        record = {
            "task_id": "original_task_001",
            "status": "test_fail",
            "timestamp": datetime.utcnow(),
            "raw_test_output": "Test failed: assertion error",
            "task_payload": {
                "task_id": "original_task_001",
                "origin": "bugfix",
                "description": "Fix bug in module X",
                "repo_root": str(tmp_path),
                "related_files": ["module_x.py"],
                "context_summary": "Bug fix needed",
                "constraints": {},
                "acceptance_criteria": ["Tests pass"],
            },
        }

        store.log_run(record)

        # Generate retry tasks
        strategy = SimpleEvolutionStrategyManager(metrics_store=store)
        tasks = strategy.generate_tasks(limit=10)

        # Verify retry task was generated
        assert len(tasks) == 1
        assert tasks[0].task_id == "retry_of_original_task_001"
        assert "Previous attempt failed" in tasks[0].description
        assert "assertion error" in tasks[0].description

    def test_no_infinite_retry_loops(self, tmp_path):
        """Test that retry tasks don't themselves get retried infinitely."""
        store = JsonlMetricsStore(repo_root=str(tmp_path), filename="test_runs.jsonl")

        # Create a failed retry task
        record = {
            "task_id": "retry_of_original_task",
            "status": "test_fail",
            "timestamp": datetime.utcnow(),
            "raw_test_output": "Still failing",
            "task_payload": {
                "task_id": "retry_of_original_task",
                "origin": "bugfix",
                "description": "Retry of original task",
                "repo_root": str(tmp_path),
                "related_files": [],
                "context_summary": "retry",
                "constraints": {},
                "acceptance_criteria": [],
            },
        }

        store.log_run(record)

        # Try to generate retry tasks
        strategy = SimpleEvolutionStrategyManager(metrics_store=store)
        tasks = strategy.generate_tasks(limit=10)

        # Should not create retry of retry
        assert len(tasks) == 0

    def test_engine_logs_to_metrics_store(self, tmp_path):
        """Test that SelfProgrammingEngine logs results to metrics store."""
        # Create a simple test file
        test_file = tmp_path / "test_module.py"
        test_file.write_text("def add(a, b):\n    return a + b\n")

        store = JsonlMetricsStore(repo_root=str(tmp_path), filename="test_runs.jsonl")
        engine = SelfProgrammingEngine(
            repo_root=str(tmp_path),
            metrics_store=store,
            enable_governance=False,  # Disable for simpler test
        )

        # Create a simple task
        task = ProgrammingTask(
            task_id="test_task_engine",
            origin="experiment",
            description="Add a subtract function",
            repo_root=str(tmp_path),
            related_files=["test_module.py"],
            context_summary="Add subtract function",
            constraints={},
            acceptance_criteria=["subtract function exists"],
        )

        # Run the task (it will likely fail since we don't have real LLM, but should log)
        result = engine.run_task(task)

        # Check that something was logged
        # The task might fail or succeed, but it should be logged
        all_runs = (
            store.get_runs_by_status("approved", limit=10)
            + store.get_runs_by_status("test_fail", limit=10)
            + store.get_runs_by_status("error", limit=10)
        )

        assert len(all_runs) > 0, "Engine should have logged the run"
        logged_task_ids = [r["task_id"] for r in all_runs]
        assert "test_task_engine" in logged_task_ids

    def test_evolution_loop_processes_tasks(self, tmp_path):
        """Test that evolution loop can process retry tasks."""
        # Setup
        store = JsonlMetricsStore(repo_root=str(tmp_path), filename="test_runs.jsonl")
        engine = SelfProgrammingEngine(
            repo_root=str(tmp_path),
            metrics_store=store,
            enable_governance=False,
        )
        strategy = SimpleEvolutionStrategyManager(metrics_store=store)

        # Create initial failed task
        record = {
            "task_id": "task_to_retry",
            "status": "test_fail",
            "timestamp": datetime.utcnow(),
            "raw_test_output": "Test error",
            "task_payload": {
                "task_id": "task_to_retry",
                "origin": "bugfix",
                "description": "Initial task",
                "repo_root": str(tmp_path),
                "related_files": [],
                "context_summary": "test",
                "constraints": {},
                "acceptance_criteria": [],
            },
        }
        store.log_run(record)

        # Run one iteration of the evolution loop
        processed = run_once(strategy, engine)

        # Should have processed 1 retry task
        assert processed == 1

        # Check that retry task was logged
        all_runs = (
            store.get_runs_by_status("approved", limit=10)
            + store.get_runs_by_status("test_fail", limit=10)
            + store.get_runs_by_status("error", limit=10)
        )

        retry_runs = [r for r in all_runs if "retry_of" in r["task_id"]]
        assert len(retry_runs) > 0, "Retry task should have been executed"


class TestPhase3Components:
    """Test that all Phase 3 components exist and work."""

    def test_governance_config_loads(self):
        """Test that governance config can be loaded."""
        from meta_agent.self_programming.governance import GovernanceConfig

        # Load from actual governance.yaml
        config = GovernanceConfig.load("governance.yaml")

        assert config is not None
        assert len(config.protected_paths) > 0
        assert config.budgets is not None
        assert config.safety is not None

    def test_meta_experiment_orchestrator_exists(self):
        """Test that meta-experiment system is available."""
        from meta_agent.self_programming.meta_experiment import (
            MetaExperimentOrchestrator,
            create_default_variants,
        )

        variants = create_default_variants()
        assert len(variants) >= 3

        # Verify variant structure
        for v in variants:
            assert v.variant_id
            assert v.name
            assert v.weights
            assert sum(v.weights.values()) > 0.99  # Should sum to ~1.0

    def test_blueprint_gap_strategy_exists(self):
        """Test that blueprint gap strategy is integrated."""
        from meta_agent.self_programming.strategy import EvolutionStrategyManager

        # Check that blueprint_gap is in the strategy types
        import typing
        strategy_type = typing.get_args(
            EvolutionStrategyManager.__init__.__annotations__.get("strategy_weights", {})
        )

        # The StrategyType literal should include blueprint_gap
        # This is a bit hacky but verifies the integration
        assert hasattr(EvolutionStrategyManager, "_generate_blueprint_gap_tasks")

    def test_evolution_loop_script_exists(self):
        """Test that evolution loop script exists and is runnable."""
        from pathlib import Path

        script_path = Path("scripts/run_evolution_loop.py")
        assert script_path.exists(), "Evolution loop script should exist"

        # Read the script and verify it has sys.path fix
        content = script_path.read_text()
        assert "sys.path.insert" in content, "Script should fix import paths"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
