"""
Unit tests for meta-experiment system.
"""
from __future__ import annotations

import pytest
from datetime import datetime, timedelta
from pathlib import Path

from meta_agent.self_programming.meta_experiment import (
    MetaExperimentOrchestrator,
    StrategyVariant,
    ExperimentRun,
    ExperimentResult,
    create_default_variants,
)
from meta_agent.self_programming.metrics_store import JsonlMetricsStore


@pytest.fixture
def temp_metrics_store(tmp_path):
    """Create a temporary metrics store for testing."""
    store = JsonlMetricsStore(repo_root=str(tmp_path), filename="test_metrics.jsonl")

    # Add some test data
    now = datetime.utcnow()
    test_runs = [
        {
            "task_id": "task_001",
            "status": "approved",
            "timestamp": now - timedelta(hours=1),
            "metrics": {"complexity_change": -2.0, "coverage_change": 0.1},
        },
        {
            "task_id": "task_002",
            "status": "approved",
            "timestamp": now - timedelta(hours=2),
            "metrics": {"complexity_change": -1.5, "coverage_change": 0.05},
        },
        {
            "task_id": "task_003",
            "status": "test_fail",
            "timestamp": now - timedelta(hours=3),
            "metrics": {"complexity_change": 0.5, "coverage_change": -0.1},
        },
    ]

    for run in test_runs:
        store.log_run(run)

    return store


@pytest.fixture
def sample_variants():
    """Create sample strategy variants for testing."""
    return [
        StrategyVariant(
            variant_id="v1",
            name="Variant 1",
            weights={"retry_failed": 0.6, "find_untested_code": 0.25, "find_complex_code": 0.15},
            description="Baseline",
        ),
        StrategyVariant(
            variant_id="v2",
            name="Variant 2",
            weights={"retry_failed": 0.3, "find_untested_code": 0.6, "find_complex_code": 0.1},
            description="Test-focused",
        ),
    ]


class TestMetaExperimentOrchestrator:
    """Tests for MetaExperimentOrchestrator."""

    def test_create_experiment(self, temp_metrics_store, sample_variants):
        """Test creating a new experiment."""
        orchestrator = MetaExperimentOrchestrator(
            metrics_store=temp_metrics_store,
            repo_root=".",
        )

        experiment = orchestrator.create_experiment(
            experiment_id="exp_001",
            variants=sample_variants,
        )

        assert experiment.experiment_id == "exp_001"
        assert len(experiment.variants) == 2
        assert experiment.started_at is not None
        assert experiment.finished_at is None
        assert len(experiment.runs) == 0

    def test_run_variant(self, temp_metrics_store, sample_variants, tmp_path):
        """Test running a single variant."""
        orchestrator = MetaExperimentOrchestrator(
            metrics_store=temp_metrics_store,
            repo_root=str(tmp_path),
        )

        # Create some source files for strategy to analyze
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        (src_dir / "example.py").write_text("def test(): pass")

        variant = sample_variants[0]
        run = orchestrator.run_variant(variant, task_limit=5, time_window_hours=24)

        assert run.variant_id == "v1"
        assert run.timestamp is not None
        assert run.tasks_generated >= 0
        assert run.tasks_successful >= 0
        assert run.tasks_failed >= 0

    def test_analyze_results_success_rate(self, temp_metrics_store, sample_variants):
        """Test analyzing experiment results by success rate."""
        orchestrator = MetaExperimentOrchestrator(
            metrics_store=temp_metrics_store,
            repo_root=".",
        )

        # Create experiment with mock runs
        experiment = ExperimentResult(
            experiment_id="exp_001",
            started_at=datetime.utcnow(),
            finished_at=None,
            variants=sample_variants,
            runs=[
                ExperimentRun(
                    variant_id="v1",
                    timestamp=datetime.utcnow(),
                    tasks_generated=10,
                    tasks_successful=8,
                    tasks_failed=2,
                    avg_complexity_reduction=1.5,
                    avg_test_coverage_improvement=0.1,
                ),
                ExperimentRun(
                    variant_id="v2",
                    timestamp=datetime.utcnow(),
                    tasks_generated=10,
                    tasks_successful=6,
                    tasks_failed=4,
                    avg_complexity_reduction=2.0,
                    avg_test_coverage_improvement=0.15,
                ),
            ],
        )

        winner, confidence = orchestrator.analyze_results(experiment, primary_metric="success_rate")

        assert winner is not None
        assert winner.variant_id == "v1"  # v1 has higher success rate (80% vs 60%)
        assert confidence > 0.0
        assert experiment.winner == "v1"

    def test_analyze_results_complexity_reduction(self, temp_metrics_store, sample_variants):
        """Test analyzing by complexity reduction."""
        orchestrator = MetaExperimentOrchestrator(
            metrics_store=temp_metrics_store,
            repo_root=".",
        )

        experiment = ExperimentResult(
            experiment_id="exp_002",
            started_at=datetime.utcnow(),
            finished_at=None,
            variants=sample_variants,
            runs=[
                ExperimentRun(
                    variant_id="v1",
                    timestamp=datetime.utcnow(),
                    tasks_generated=10,
                    tasks_successful=8,
                    tasks_failed=2,
                    avg_complexity_reduction=1.5,  # Less reduction
                    avg_test_coverage_improvement=0.1,
                ),
                ExperimentRun(
                    variant_id="v2",
                    timestamp=datetime.utcnow(),
                    tasks_generated=10,
                    tasks_successful=6,
                    tasks_failed=4,
                    avg_complexity_reduction=3.0,  # More reduction
                    avg_test_coverage_improvement=0.15,
                ),
            ],
        )

        winner, confidence = orchestrator.analyze_results(experiment, primary_metric="complexity_reduction")

        assert winner is not None
        assert winner.variant_id == "v2"  # v2 has better complexity reduction

    def test_auto_adjust_weights(self, temp_metrics_store, sample_variants):
        """Test automatic weight adjustment based on winner."""
        orchestrator = MetaExperimentOrchestrator(
            metrics_store=temp_metrics_store,
            repo_root=".",
        )

        current_weights = {"retry_failed": 0.6, "find_untested_code": 0.25, "find_complex_code": 0.15}

        experiment = ExperimentResult(
            experiment_id="exp_003",
            started_at=datetime.utcnow(),
            finished_at=datetime.utcnow(),
            variants=sample_variants,
            winner="v2",
            confidence=0.8,
        )

        new_weights = orchestrator.auto_adjust_weights(
            current_weights,
            experiment,
            learning_rate=0.2,
        )

        # Should move towards v2's weights (test-focused)
        assert new_weights["find_untested_code"] > current_weights["find_untested_code"]
        assert new_weights["retry_failed"] < current_weights["retry_failed"]

        # Should still sum to ~1.0
        assert abs(sum(new_weights.values()) - 1.0) < 0.01

    def test_auto_adjust_weights_no_winner(self, temp_metrics_store):
        """Test that weights don't change without a winner."""
        orchestrator = MetaExperimentOrchestrator(
            metrics_store=temp_metrics_store,
            repo_root=".",
        )

        current_weights = {"retry_failed": 0.6, "find_untested_code": 0.25, "find_complex_code": 0.15}

        experiment = ExperimentResult(
            experiment_id="exp_004",
            started_at=datetime.utcnow(),
            finished_at=datetime.utcnow(),
            variants=[],
            winner=None,
            confidence=0.0,
        )

        new_weights = orchestrator.auto_adjust_weights(current_weights, experiment)

        assert new_weights == current_weights

    def test_save_experiment(self, temp_metrics_store, sample_variants, tmp_path):
        """Test saving experiment results."""
        orchestrator = MetaExperimentOrchestrator(
            metrics_store=temp_metrics_store,
            repo_root=str(tmp_path),
        )

        experiment = ExperimentResult(
            experiment_id="exp_save_test",
            started_at=datetime.utcnow(),
            finished_at=datetime.utcnow(),
            variants=sample_variants,
            runs=[
                ExperimentRun(
                    variant_id="v1",
                    timestamp=datetime.utcnow(),
                    tasks_generated=10,
                    tasks_successful=8,
                    tasks_failed=2,
                    avg_complexity_reduction=1.5,
                    avg_test_coverage_improvement=0.1,
                ),
            ],
            winner="v1",
            confidence=0.75,
        )

        output_path = tmp_path / "test_experiment.json"
        orchestrator.save_experiment(experiment, output_path=output_path)

        assert output_path.exists()

        # Verify content
        import json
        with output_path.open("r") as f:
            data = json.load(f)

        assert data["experiment_id"] == "exp_save_test"
        assert data["winner"] == "v1"
        assert data["confidence"] == 0.75
        assert len(data["variants"]) == 2
        assert len(data["runs"]) == 1


class TestStrategyVariants:
    """Tests for strategy variant creation."""

    def test_create_default_variants(self):
        """Test creating default variant set."""
        variants = create_default_variants()

        assert len(variants) >= 3
        assert all(isinstance(v, StrategyVariant) for v in variants)

        # Check that all weights sum to 1.0
        for variant in variants:
            total = sum(variant.weights.values())
            assert abs(total - 1.0) < 0.01

    def test_variant_has_required_fields(self):
        """Test that variants have all required fields."""
        variants = create_default_variants()

        for variant in variants:
            assert variant.variant_id
            assert variant.name
            assert variant.weights
            assert len(variant.weights) > 0


class TestExperimentWorkflow:
    """Integration tests for complete experiment workflow."""

    def test_full_experiment_workflow(self, temp_metrics_store, tmp_path):
        """Test running a complete experiment from start to finish."""
        orchestrator = MetaExperimentOrchestrator(
            metrics_store=temp_metrics_store,
            repo_root=str(tmp_path),
        )

        # Create some source files
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        (src_dir / "example.py").write_text("def test(): pass")

        # Create experiment
        variants = create_default_variants()[:2]  # Use first 2 variants
        experiment = orchestrator.create_experiment("exp_workflow", variants)

        assert experiment.experiment_id == "exp_workflow"
        assert len(experiment.variants) == 2

        # Note: Full run would require actual self-programming, so we'll just
        # verify the workflow structure works
        assert experiment.started_at is not None
        assert experiment.finished_at is None

    def test_experiment_lifecycle(self, temp_metrics_store):
        """Test experiment state transitions."""
        orchestrator = MetaExperimentOrchestrator(
            metrics_store=temp_metrics_store,
            repo_root=".",
        )

        variants = create_default_variants()[:2]

        # 1. Create
        experiment = orchestrator.create_experiment("exp_lifecycle", variants)
        assert experiment.finished_at is None
        assert len(experiment.runs) == 0

        # 2. Add mock runs with different success rates
        experiment.runs = [
            ExperimentRun(
                variant_id=variants[0].variant_id,
                timestamp=datetime.utcnow(),
                tasks_generated=5,
                tasks_successful=3,  # Lower success rate
                tasks_failed=2,
                avg_complexity_reduction=1.0,
                avg_test_coverage_improvement=0.05,
            ),
            ExperimentRun(
                variant_id=variants[1].variant_id,
                timestamp=datetime.utcnow(),
                tasks_generated=5,
                tasks_successful=5,  # Higher success rate - should win
                tasks_failed=0,
                avg_complexity_reduction=1.0,
                avg_test_coverage_improvement=0.05,
            ),
        ]

        # 3. Analyze
        winner, confidence = orchestrator.analyze_results(experiment)
        assert winner is not None
        assert experiment.winner is not None

        # 4. Adjust weights
        current_weights = {"retry_failed": 0.6, "find_untested_code": 0.25, "find_complex_code": 0.15}
        new_weights = orchestrator.auto_adjust_weights(current_weights, experiment)
        assert new_weights != current_weights


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
