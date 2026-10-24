#!/usr/bin/env python
"""
CLI tool to run experiments with eval harness.

Usage:
    python scripts/run_experiment.py create --name "Model Comparison" --target model_output
    python scripts/run_experiment.py list
    python scripts/run_experiment.py run <experiment_id>
    python scripts/run_experiment.py compare <experiment_id> --metric success
"""

import argparse
import json
import sys
from pathlib import Path
from typing import List, Dict, Any

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from quentin.infra.storage.kv_store import KVStore
from quentin.infra.logging import Tracer
from quentin.l3.research.experiment_orchestrator import ExperimentOrchestrator
from quentin.l3.research.experiment_schemas import ExperimentConfig, ExperimentVariant
from quentin.l3.research.eval_harness import EvalHarness, EvalCase
from quentin.l3.research.eval_setup import setup_default_evaluators, print_evaluator_info


def create_experiment(args):
    """Create a new experiment."""
    print(f"\nCreating experiment: {args.name}")
    print(f"Target type: {args.target}")

    # Initialize components
    kv = KVStore()
    tracer = Tracer()
    orchestrator = ExperimentOrchestrator(tracer=tracer, kv=kv)

    # Create variants
    variants = []
    if args.variants:
        for variant_spec in args.variants:
            # Parse variant_id:param1=val1,param2=val2
            if ':' in variant_spec:
                variant_id, params_str = variant_spec.split(':', 1)
                params = {}
                for param in params_str.split(','):
                    if '=' in param:
                        key, val = param.split('=', 1)
                        params[key] = val
            else:
                variant_id = variant_spec
                params = {}

            variants.append(ExperimentVariant(
                variant_id=variant_id,
                name=variant_id,
                params=params
            ))
    else:
        # Default variants
        variants = [
            ExperimentVariant(variant_id="baseline", name="Baseline", params={"strategy": "baseline"}),
            ExperimentVariant(variant_id="enhanced", name="Enhanced", params={"strategy": "enhanced"}),
        ]

    # Create config
    config = ExperimentConfig(
        target_module=args.target,
        target_type=args.target,
        metrics=args.metrics or ["success", "latency_ms", "cost_tokens"],
    )

    # Create experiment
    experiment = orchestrator.create_experiment(
        name=args.name,
        config=config,
        variants=variants,
    )

    print(f"\n✓ Created experiment: {experiment.experiment_id}")
    print(f"  Name: {experiment.name}")
    print(f"  Variants: {len(variants)}")
    for v in variants:
        print(f"    - {v.variant_id}: {v.params}")

    return experiment.experiment_id


def list_experiments(args):
    """List all experiments."""
    kv = KVStore()
    tracer = Tracer()
    orchestrator = ExperimentOrchestrator(tracer=tracer, kv=kv)

    experiments = orchestrator.list_experiments()

    if not experiments:
        print("\nNo experiments found.")
        return

    print(f"\n{'='*80}")
    print(f"{'EXPERIMENTS':^80}")
    print(f"{'='*80}\n")

    for exp in experiments:
        print(f"ID: {exp.experiment_id}")
        print(f"  Name: {exp.name}")
        print(f"  Target: {exp.config.target_type}")
        print(f"  Status: {exp.status.value}")
        print(f"  Variants: {len(exp.variants)}")
        print()


def run_experiment(args):
    """Run an experiment."""
    exp_id = args.experiment_id

    print(f"\n{'='*80}")
    print(f"{'RUNNING EXPERIMENT':^80}")
    print(f"{'='*80}\n")

    # Initialize components
    kv = KVStore()
    tracer = Tracer()
    harness = EvalHarness(kv=kv, tracer=tracer)

    # Setup evaluators
    setup_default_evaluators(harness)
    print("✓ Loaded default evaluators")

    orchestrator = ExperimentOrchestrator(tracer=tracer, kv=kv, eval_harness=harness)

    # Get experiment
    experiment = orchestrator.get_experiment(exp_id)
    if not experiment:
        print(f"❌ Experiment not found: {exp_id}")
        return

    print(f"Experiment: {experiment.name}")
    print(f"Target: {experiment.config.target_type}")
    print(f"Variants: {len(experiment.variants)}\n")

    # Create eval cases if not exists
    cases = []
    if args.cases:
        # Load cases from file
        try:
            with open(args.cases, 'r') as f:
                cases_data = json.load(f)
                for case_data in cases_data:
                    cases.append(EvalCase(
                        case_id=case_data.get("case_id", f"case_{len(cases)}"),
                        description=case_data.get("description", ""),
                        input_payload=case_data.get("input_payload", {}),
                        expected_keywords=case_data.get("expected_keywords", []),
                        pass_threshold=case_data.get("pass_threshold", 0.6),
                    ))
        except Exception as e:
            print(f"Error loading cases: {e}")
            return
    else:
        # Default cases
        cases = [
            EvalCase(
                case_id="case_1",
                description="Basic functionality test",
                input_payload={"prompt": "Generate a simple response"},
                expected_keywords=["response", "generate"],
                pass_threshold=0.5,
            ),
            EvalCase(
                case_id="case_2",
                description="Quality test",
                input_payload={"prompt": "Provide detailed analysis"},
                expected_keywords=["analysis", "detailed", "comprehensive"],
                pass_threshold=0.6,
            ),
        ]

    print(f"Running {len(cases)} evaluation cases...")

    # Run experiment
    import asyncio
    result = asyncio.run(orchestrator.run_experiment(exp_id, cases=cases))

    print("\n" + "="*80)
    print(f"{'RESULTS':^80}")
    print("="*80 + "\n")

    print(f"Run ID: {result['run_id']}")
    print(f"Status: {result['status']}\n")

    # Display variant results
    variant_results = result.get("variant_results", {})
    for variant_id, metrics in variant_results.items():
        print(f"Variant: {variant_id}")
        for metric_name, metric_value in metrics.items():
            if isinstance(metric_value, float):
                print(f"  {metric_name}: {metric_value:.3f}")
            else:
                print(f"  {metric_name}: {metric_value}")
        print()

    print("✓ Experiment complete")


def compare_experiments(args):
    """Compare experiment variants."""
    exp_id = args.experiment_id
    metric = args.metric

    kv = KVStore()
    tracer = Tracer()
    orchestrator = ExperimentOrchestrator(tracer=tracer, kv=kv)

    print(f"\n{'='*80}")
    print(f"{'VARIANT COMPARISON':^80}")
    print(f"{'='*80}\n")

    results = orchestrator.compare_variants(exp_id, metric=metric, top_k=args.top_k)

    if not results:
        print(f"No results found for experiment: {exp_id}")
        return

    print(f"Comparing by: {metric}")
    print(f"Top {len(results)} variants:\n")

    for i, (variant_id, score) in enumerate(results, 1):
        print(f"{i}. {variant_id:20s} {score:.4f}")


def show_evaluators(args):
    """Show available evaluators."""
    print_evaluator_info()


def main():
    parser = argparse.ArgumentParser(description="Experiment CLI")
    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # Create experiment
    create_parser = subparsers.add_parser("create", help="Create new experiment")
    create_parser.add_argument("--name", required=True, help="Experiment name")
    create_parser.add_argument("--target", required=True, help="Target type (model_output, strategy, etc)")
    create_parser.add_argument("--variants", nargs="+", help="Variant specs (id:param1=val1,param2=val2)")
    create_parser.add_argument("--metrics", nargs="+", help="Metrics to track")

    # List experiments
    list_parser = subparsers.add_parser("list", help="List all experiments")

    # Run experiment
    run_parser = subparsers.add_parser("run", help="Run experiment")
    run_parser.add_argument("experiment_id", help="Experiment ID")
    run_parser.add_argument("--cases", help="Path to eval cases JSON file")

    # Compare variants
    compare_parser = subparsers.add_parser("compare", help="Compare variants")
    compare_parser.add_argument("experiment_id", help="Experiment ID")
    compare_parser.add_argument("--metric", default="success", help="Metric to compare")
    compare_parser.add_argument("--top-k", type=int, default=5, help="Number of top variants to show")

    # Show evaluators
    eval_parser = subparsers.add_parser("evaluators", help="Show available evaluators")

    args = parser.parse_args()

    if args.command == "create":
        create_experiment(args)
    elif args.command == "list":
        list_experiments(args)
    elif args.command == "run":
        run_experiment(args)
    elif args.command == "compare":
        compare_experiments(args)
    elif args.command == "evaluators":
        show_evaluators(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
