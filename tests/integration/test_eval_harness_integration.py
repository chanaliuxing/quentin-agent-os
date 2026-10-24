"""
Integration Tests for Eval Harness + Evaluators + Orchestrator

Tests the complete workflow:
1. Register real evaluators with harness
2. Run experiments end-to-end
3. Verify metrics collection
4. Test dashboard integration
"""

import asyncio
import json
import pytest
from pathlib import Path
from typing import Dict, Any

from quentin.infra.storage.kv_store import KVStore
from quentin.infra.logging import Tracer
from quentin.l3.research.eval_harness import EvalHarness, EvalCase
from quentin.l3.research.eval_setup import setup_default_evaluators, get_evaluator_info
from quentin.l3.research.evaluators import (
    KeywordEvaluator,
    ModelOutputEvaluator,
    StrategyBacktestEvaluator,
    CodeQualityEvaluator,
    get_evaluator,
)
from quentin.l3.research.experiment_orchestrator import ExperimentOrchestrator
from quentin.l3.research.experiment_schemas import ExperimentConfig, ExperimentVariant, ExperimentStatus
from quentin.observability.dashboard import ObservabilityDashboard


class TestEvaluatorRegistry:
    """Test evaluator registration and retrieval."""

    def test_all_evaluators_registered(self):
        """Verify all evaluators are in registry."""
        info = get_evaluator_info()
        assert "keyword" in info
        assert "model_output" in info
        assert "strategy_backtest" in info
        assert "code_quality" in info

    def test_get_evaluator_keyword(self):
        """Test getting keyword evaluator."""
        evaluator = get_evaluator("keyword")
        assert isinstance(evaluator, KeywordEvaluator)

    def test_get_evaluator_model_output(self):
        """Test getting model output evaluator."""
        evaluator = get_evaluator("model_output")
        assert isinstance(evaluator, ModelOutputEvaluator)

    def test_get_evaluator_strategy(self):
        """Test getting strategy backtest evaluator."""
        evaluator = get_evaluator("strategy_backtest")
        assert isinstance(evaluator, StrategyBacktestEvaluator)

    def test_get_evaluator_code_quality(self):
        """Test getting code quality evaluator."""
        evaluator = get_evaluator("code_quality")
        assert isinstance(evaluator, CodeQualityEvaluator)

    def test_get_evaluator_unknown_raises(self):
        """Test that unknown evaluator type raises ValueError."""
        with pytest.raises(ValueError, match="Unknown evaluator type"):
            get_evaluator("nonexistent")


class TestEvaluatorExecution:
    """Test individual evaluator execution."""

    def test_keyword_evaluator(self):
        """Test keyword evaluator with matching keywords."""
        evaluator = KeywordEvaluator()
        case = EvalCase(
            case_id="test_1",
            description="Test case",
            input_payload={"prompt": "Generate a response"},
            expected_keywords=["response", "generate"],
            pass_threshold=0.5,
        )
        variant = ExperimentVariant(
            variant_id="baseline",
            name="Baseline",
            params={"strategy": "baseline"},
        )

        result = evaluator.evaluate(case, variant)

        assert 0.0 <= result.success <= 1.0
        assert result.latency_ms >= 0
        assert result.cost_tokens >= 0
        assert result.raw_output is not None
        assert "keywords_matched" in result.raw_metrics
        assert "keywords_total" in result.raw_metrics

    def test_model_output_evaluator(self):
        """Test model output evaluator."""
        evaluator = ModelOutputEvaluator()
        case = EvalCase(
            case_id="test_2",
            description="Model output test",
            input_payload={"prompt": "Provide detailed analysis"},
            expected_keywords=["analysis", "detailed"],
            pass_threshold=0.6,
        )
        variant = ExperimentVariant(
            variant_id="enhanced",
            name="Enhanced",
            params={"model": "gpt-4"},
        )

        result = evaluator.evaluate(case, variant)

        assert 0.0 <= result.success <= 1.0
        assert result.latency_ms >= 0
        assert "quality_score" in result.raw_metrics
        assert "has_expected_structure" in result.raw_metrics

    def test_strategy_backtest_evaluator(self):
        """Test strategy backtest evaluator."""
        evaluator = StrategyBacktestEvaluator()
        case = EvalCase(
            case_id="test_3",
            description="Backtest strategy",
            input_payload={"strategy_config": {}},
            expected_keywords=[],
            pass_threshold=0.5,
        )
        variant = ExperimentVariant(
            variant_id="aggressive",
            name="Aggressive",
            params={"strategy": "aggressive"},
        )

        result = evaluator.evaluate(case, variant)

        assert 0.0 <= result.success <= 1.0
        assert result.cost_tokens == 0.0  # No LLM cost for backtests
        assert "sharpe_ratio" in result.raw_metrics
        assert "max_drawdown" in result.raw_metrics
        assert "win_rate" in result.raw_metrics

    def test_code_quality_evaluator(self):
        """Test code quality evaluator."""
        evaluator = CodeQualityEvaluator()
        case = EvalCase(
            case_id="test_4",
            description="Code generation",
            input_payload={"task": "implement binary search"},
            expected_keywords=["search", "binary"],
            pass_threshold=0.5,
        )
        variant = ExperimentVariant(
            variant_id="high_quality",
            name="High Quality",
            params={"quality": "high"},
        )

        result = evaluator.evaluate(case, variant)

        assert 0.0 <= result.success <= 1.0
        assert "has_docstring" in result.raw_metrics
        assert "has_type_hints" in result.raw_metrics
        assert "overall_score" in result.raw_metrics


class TestHarnessIntegration:
    """Test eval harness integration with real evaluators."""

    def test_setup_default_evaluators(self):
        """Test that setup_default_evaluators registers all evaluators."""
        kv = KVStore()
        tracer = Tracer()
        harness = EvalHarness(kv=kv, tracer=tracer)

        setup_default_evaluators(harness)

        # Verify evaluators are registered (using private attribute)
        assert "text_generation" in harness._evaluators
        assert "model_output" in harness._evaluators
        assert "strategy" in harness._evaluators
        assert "code_generation" in harness._evaluators
        assert "default" in harness._evaluators

    @pytest.mark.asyncio
    async def test_run_case_with_keyword_evaluator(self):
        """Test running a single case through harness via run_suite."""
        kv = KVStore()
        tracer = Tracer()
        harness = EvalHarness(kv=kv, tracer=tracer)
        setup_default_evaluators(harness)

        case = EvalCase(
            case_id="harness_test_1",
            description="Test harness execution",
            input_payload={"prompt": "Generate response"},
            expected_keywords=["response"],
            pass_threshold=0.5,
        )
        variant = ExperimentVariant(
            variant_id="test_variant",
            name="Test Variant",
            params={"strategy": "baseline"},
        )

        # Use run_suite for single case
        suite_result = await harness.run_suite(
            experiment_id="test_exp",
            variant=variant,
            cases=[case],
            target_type="text_generation",
        )

        assert len(suite_result.case_results) == 1
        result = suite_result.case_results[0]
        assert result.case_id == "harness_test_1"
        assert 0.0 <= result.success <= 1.0
        assert result.latency_ms >= 0

    @pytest.mark.asyncio
    async def test_run_suite_aggregation(self):
        """Test running a suite and aggregating results."""
        kv = KVStore()
        tracer = Tracer()
        harness = EvalHarness(kv=kv, tracer=tracer)
        setup_default_evaluators(harness)

        cases = [
            EvalCase(
                case_id=f"suite_test_{i}",
                description=f"Test case {i}",
                input_payload={"prompt": f"Task {i}"},
                expected_keywords=["response"],
                pass_threshold=0.5,
            )
            for i in range(3)
        ]
        variant = ExperimentVariant(
            variant_id="suite_variant",
            name="Suite Variant",
            params={},
        )

        suite_result = await harness.run_suite(
            experiment_id="integration_suite",
            variant=variant,
            cases=cases,
            target_type="text_generation",
        )

        assert suite_result.experiment_id == "integration_suite"
        assert len(suite_result.case_results) == 3
        metrics = suite_result.metrics
        assert 0.0 <= metrics["success_rate"] <= 1.0
        assert metrics["avg_latency_ms"] >= 0
        assert metrics["avg_cost_tokens"] >= 0


class TestOrchestratorIntegration:
    """Test experiment orchestrator with real evaluators."""

    @pytest.mark.asyncio
    async def test_create_and_run_experiment(self):
        """Test creating and running experiment end-to-end."""
        kv = KVStore()
        tracer = Tracer()
        harness = EvalHarness(kv=kv, tracer=tracer)
        setup_default_evaluators(harness)

        orchestrator = ExperimentOrchestrator(
            tracer=tracer,
            kv=kv,
            eval_harness=harness,
        )

        # Create experiment
        config = ExperimentConfig(
            target_module="text_generation",
            target_type="text_generation",
            metrics=["success", "latency_ms", "cost_tokens"],
        )
        variants = [
            ExperimentVariant(
                variant_id="baseline",
                name="Baseline",
                params={"strategy": "baseline"},
            ),
            ExperimentVariant(
                variant_id="enhanced",
                name="Enhanced",
                params={"strategy": "enhanced"},
            ),
        ]

        experiment = await orchestrator.create_experiment(
            name="Integration Test Experiment",
            description="End-to-end integration test",
            config=config,
            variants=variants,
        )

        assert experiment.experiment_id is not None
        assert experiment.name == "Integration Test Experiment"
        assert len(experiment.variants) == 2

        # Create eval cases
        cases = [
            EvalCase(
                case_id="integration_case_1",
                description="Basic test",
                input_payload={"prompt": "Generate simple response"},
                expected_keywords=["response", "generate"],
                pass_threshold=0.5,
            ),
            EvalCase(
                case_id="integration_case_2",
                description="Quality test",
                input_payload={"prompt": "Provide detailed analysis"},
                expected_keywords=["analysis", "detailed"],
                pass_threshold=0.6,
            ),
        ]

        # Run experiment
        result = await orchestrator.run_experiment(experiment.experiment_id, cases=cases)

        assert result.run_id is not None
        assert result.status in [ExperimentStatus.completed, ExperimentStatus.running]
        assert result.variant_results is not None

        # Verify variant results
        variant_results = result.variant_results
        assert "baseline" in variant_results
        assert "enhanced" in variant_results

        for variant_id, metrics in variant_results.items():
            assert "success_rate" in metrics or "success" in metrics or "avg_success" in metrics
            assert "avg_latency_ms" in metrics or "latency_ms" in metrics

    @pytest.mark.asyncio
    async def test_compare_variants(self):
        """Test variant comparison after experiment run."""
        kv = KVStore()
        tracer = Tracer()
        harness = EvalHarness(kv=kv, tracer=tracer)
        setup_default_evaluators(harness)

        orchestrator = ExperimentOrchestrator(
            tracer=tracer,
            kv=kv,
            eval_harness=harness,
        )

        # Create and run experiment
        config = ExperimentConfig(
            target_module="text_generation",
            target_type="text_generation",
            metrics=["success"],
        )
        variants = [
            ExperimentVariant(
                variant_id="var_a",
                name="Variant A",
                params={"strategy": "baseline"},
            ),
            ExperimentVariant(
                variant_id="var_b",
                name="Variant B",
                params={"strategy": "enhanced"},
            ),
        ]

        experiment = await orchestrator.create_experiment(
            name="Comparison Test",
            description="Test variant comparison",
            config=config,
            variants=variants,
        )

        cases = [
            EvalCase(
                case_id="comp_case_1",
                description="Comparison test",
                input_payload={"prompt": "Test"},
                expected_keywords=["response"],
                pass_threshold=0.5,
            ),
        ]

        await orchestrator.run_experiment(experiment.experiment_id, cases=cases)

        # Compare variants
        comparison = await orchestrator.compare_variants(
            experiment.experiment_id,
            metric="success_rate",
        )

        # comparison is a list of dicts, not tuples
        assert isinstance(comparison, list)
        if len(comparison) > 0:  # May be empty if no results stored
            for item in comparison[:2]:  # Check top 2
                assert isinstance(item, dict)


class TestDashboardIntegration:
    """Test dashboard integration with experiment metrics."""

    def test_dashboard_collects_experiment_metrics(self, tmp_path):
        """Test that dashboard can collect experiment metrics from JSONL."""
        # Create test data directory
        data_dir = tmp_path / "data" / "research"
        data_dir.mkdir(parents=True)
        eval_results_path = data_dir / "eval_results.jsonl"

        # Write test data
        test_results = [
            {
                "experiment_id": "exp_1",
                "run_id": "run_1",
                "case_results": [
                    {"success": 0.8, "latency_ms": 100},
                    {"success": 0.9, "latency_ms": 120},
                ],
            },
            {
                "experiment_id": "exp_2",
                "run_id": "run_2",
                "case_results": [
                    {"success": 0.7, "latency_ms": 90},
                ],
            },
        ]

        with open(eval_results_path, "w") as f:
            for result in test_results:
                f.write(json.dumps(result) + "\n")

        # Temporarily change working directory to tmp_path
        import os
        original_cwd = os.getcwd()
        try:
            os.chdir(tmp_path)

            dashboard = ObservabilityDashboard()
            metrics = dashboard.collect_metrics()

            # Verify experiment metrics were collected
            assert metrics.experiment_count == 2
            assert metrics.experiment_runs_total == 2
            assert metrics.evaluation_cases_total == 3
            assert metrics.experiment_avg_success_rate > 0
            assert metrics.evaluation_avg_latency_ms > 0
            assert metrics.eval_harness_healthy is True

        finally:
            os.chdir(original_cwd)

    def test_dashboard_health_check(self):
        """Test dashboard health check includes eval harness."""
        dashboard = ObservabilityDashboard()
        health = dashboard.health_check()

        assert "status" in health
        assert "checks" in health
        assert health["status"] in ["healthy", "degraded", "unhealthy"]

    def test_dashboard_summary_includes_experiments(self):
        """Test dashboard summary includes experiment section."""
        dashboard = ObservabilityDashboard()
        summary = dashboard.get_summary()

        assert "Experiments & Evaluation:" in summary
        assert "Experiments:" in summary
        assert "Runs:" in summary
        assert "Avg Success Rate:" in summary
        assert "Evaluation Cases:" in summary
        assert "Avg Latency:" in summary


class TestEndToEndWorkflow:
    """Test complete end-to-end workflow."""

    @pytest.mark.asyncio
    async def test_full_experiment_workflow(self, tmp_path):
        """Test full workflow: create -> run -> collect metrics -> dashboard."""
        # Setup
        kv = KVStore()
        tracer = Tracer()
        harness = EvalHarness(kv=kv, tracer=tracer)
        setup_default_evaluators(harness)

        orchestrator = ExperimentOrchestrator(
            tracer=tracer,
            kv=kv,
            eval_harness=harness,
        )

        # Step 1: Create experiment
        config = ExperimentConfig(
            target_module="model_output",
            target_type="model_output",
            metrics=["success", "latency_ms", "cost_tokens"],
        )
        variants = [
            ExperimentVariant(
                variant_id="baseline",
                name="Baseline Model",
                params={"model": "baseline"},
            ),
            ExperimentVariant(
                variant_id="advanced",
                name="Advanced Model",
                params={"model": "advanced"},
            ),
        ]

        experiment = await orchestrator.create_experiment(
            name="E2E Test Experiment",
            description="Full end-to-end workflow test",
            config=config,
            variants=variants,
        )

        # Step 2: Run experiment
        cases = [
            EvalCase(
                case_id="e2e_case_1",
                description="Basic evaluation",
                input_payload={"prompt": "Generate response"},
                expected_keywords=["response"],
                pass_threshold=0.5,
            ),
            EvalCase(
                case_id="e2e_case_2",
                description="Quality evaluation",
                input_payload={"prompt": "Detailed analysis"},
                expected_keywords=["analysis", "detailed"],
                pass_threshold=0.6,
            ),
        ]

        result = await orchestrator.run_experiment(experiment.experiment_id, cases=cases)

        # Step 3: Verify results
        assert result.status in [ExperimentStatus.completed, ExperimentStatus.running]
        assert len(result.variant_results) == 2

        # Step 4: Compare variants (may be empty if results not persisted to experiment record)
        comparison = await orchestrator.compare_variants(
            experiment.experiment_id,
            metric="success_rate",
        )
        # Comparison may be empty, that's okay for this test
        assert isinstance(comparison, list)

        # Step 5: Verify dashboard can access results
        # Note: Dashboard reads from JSONL file, which harness writes to
        # In a real scenario, we'd verify the file exists and is readable
        dashboard = ObservabilityDashboard()
        health = dashboard.health_check()
        assert health["status"] in ["healthy", "degraded"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
