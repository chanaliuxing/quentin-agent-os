#!/usr/bin/env python
"""
CLI to run the Strategy Council.

Usage:
    python scripts/run_strategy_council.py --disable-llm
    python scripts/run_strategy_council.py --paper-runner module.sub:func
    python scripts/run_strategy_council.py --paper-metrics-path results.json
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, Optional, Callable

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from quentin.l3.research.strategy_council import (
    run_council,
    log_plan_vs_outcome,
    FinalPlan,
    PaperResult,
)


def load_paper_runner(module_path: str) -> Optional[Callable]:
    """
    Load a paper_runner function from module:function format.

    Example: 'mymodule.backtest:run_backtest'
    """
    try:
        module_name, func_name = module_path.split(":")
        import importlib
        mod = importlib.import_module(module_name)
        func = getattr(mod, func_name)
        return func
    except Exception as e:
        print(f"Error loading paper_runner from {module_path}: {e}")
        return None


def load_paper_metrics(path: str) -> Optional[Dict[str, Any]]:
    """Load paper trading metrics from JSON file."""
    try:
        with open(path, 'r') as f:
            return json.load(f)
    except Exception as e:
        print(f"Error loading paper metrics from {path}: {e}")
        return None


def main():
    parser = argparse.ArgumentParser(description="Run Strategy Council")
    parser.add_argument(
        "--disable-llm",
        action="store_true",
        help="Disable LLM calls and use fallback proposals"
    )
    parser.add_argument(
        "--universe",
        nargs="+",
        help="Trading universe symbols (e.g., AAPL TSLA SPY)"
    )
    parser.add_argument(
        "--paper-runner",
        help="Module path to paper runner function (module:func)"
    )
    parser.add_argument(
        "--paper-metrics-path",
        help="Path to paper trading metrics JSON file"
    )
    parser.add_argument(
        "--output-dir",
        default="runs/strategy_council",
        help="Output directory for results"
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Verbose output"
    )

    args = parser.parse_args()

    # Build context
    ctx: Dict[str, Any] = {
        "disable_llm": args.disable_llm,
    }

    if args.universe:
        ctx["universe"] = args.universe

    if args.paper_runner:
        paper_runner = load_paper_runner(args.paper_runner)
        if paper_runner:
            ctx["paper_runner"] = paper_runner
            print(f"✓ Loaded paper_runner from {args.paper_runner}")

    if args.paper_metrics_path:
        metrics = load_paper_metrics(args.paper_metrics_path)
        if metrics:
            ctx["paper_metrics"] = metrics
            print(f"✓ Loaded paper metrics from {args.paper_metrics_path}")

    # Create output directory
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    ctx["output_dir"] = str(output_dir)

    print("\n" + "="*80)
    print("  STRATEGY COUNCIL")
    print("="*80 + "\n")

    if args.disable_llm:
        print("⚠️  Running in fallback mode (LLM disabled)\n")

    if args.universe:
        print(f"Universe: {', '.join(args.universe)}\n")

    # Run council
    print("Running strategy council...\n")

    try:
        result = run_council(ctx)

        print("\n" + "="*80)
        print("  RESULTS")
        print("="*80 + "\n")

        # Display proposals
        proposals = result.get("proposals", [])
        print(f"Generated {len(proposals)} proposals:")
        for i, p in enumerate(proposals, 1):
            print(f"\n  {i}. Proposal {p.get('proposal_id', 'unknown')[:8]}...")
            print(f"     Symbols: {p.get('symbols', [])}")
            print(f"     Side: {p.get('side', 'unknown')}")
            print(f"     Expected EV: {p.get('expected_ev', 0):.2f}")
            print(f"     Confidence: {p.get('confidence', 0):.2f}")
            print(f"     Max Drawdown: {p.get('max_drawdown', 0):.1f}%")
            hedge = p.get('hedge_plan')
            if hedge:
                print(f"     Hedge: {hedge.get('hedge_type')} via {hedge.get('instrument')}")

        # Display reviews
        reviews = result.get("reviews", [])
        print(f"\n\nReceived {len(reviews)} reviews")

        # Display final plan
        final_plan = result.get("final_plan")
        if final_plan:
            print(f"\n\nFinal Plan (base: {final_plan.get('base_proposal_id', 'unknown')[:8]}...):")
            print(f"  Approvals: {', '.join(final_plan.get('approvals', []))}")
            print(f"  Open Risks: {len(final_plan.get('open_risks', []))}")
            hedge = final_plan.get('hedge_plan')
            if hedge:
                print(f"  Hedge Plan: {hedge.get('hedge_type')} via {hedge.get('instrument')}")

        # Display paper result
        paper_result = result.get("paper_result")
        if paper_result and paper_result.get("ok"):
            print(f"\n\nPaper Trading Result:")
            print(f"  PnL: {paper_result.get('pnl', 0):.2f}")
            print(f"  EV Realized: {paper_result.get('ev_realized', 0):.2f}")
            print(f"  Max Drawdown: {paper_result.get('mdd', 0):.2f}%")
            print(f"  Sharpe: {paper_result.get('sharpe', 0):.2f}")
            if paper_result.get('hedge_pnl') is not None:
                print(f"  Hedge PnL: {paper_result.get('hedge_pnl', 0):.2f}")
                print(f"  Hedge Var Reduction: {paper_result.get('hedge_var_reduction', 0):.2%}")

        # Save results
        result_file = output_dir / "council_result.json"
        with open(result_file, 'w') as f:
            # Convert to JSON-serializable format
            json_result = {}
            for key, value in result.items():
                if hasattr(value, 'to_dict'):
                    json_result[key] = value.to_dict()
                elif isinstance(value, list):
                    json_result[key] = [
                        v.to_dict() if hasattr(v, 'to_dict') else v
                        for v in value
                    ]
                else:
                    json_result[key] = value
            json.dump(json_result, f, indent=2, ensure_ascii=False)

        print(f"\n\n✓ Results saved to {result_file}")

        # Log plan outcome if we have paper results
        if paper_result and paper_result.get("ok") and final_plan:
            plan_id = final_plan.get("base_proposal_id", "unknown")
            ev_plan = 0.0
            for p in proposals:
                if p.get("proposal_id") == plan_id:
                    ev_plan = p.get("expected_ev", 0.0)
                    break

            outcome = log_plan_vs_outcome(
                plan_id=plan_id,
                summary=f"Council session {result.get('session_id', 'unknown')[:8]}",
                ev_plan=ev_plan,
                ev_realized=paper_result.get("ev_realized", 0.0),
                mdd=paper_result.get("mdd", 0.0),
                hedge_effect={
                    "hedge_pnl": paper_result.get("hedge_pnl"),
                    "var_reduction": paper_result.get("hedge_var_reduction"),
                },
                issues=[],
                lessons=[],
            )
            print(f"✓ Plan outcome logged: {outcome.get('plan_id')}")

        print("\n" + "="*80)
        print("  COUNCIL COMPLETE")
        print("="*80 + "\n")

    except Exception as e:
        print(f"\n❌ Error running council: {e}")
        import traceback
        if args.verbose:
            traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
