# scripts/run_self_evo_daemon.py
import argparse
import datetime as dt
import json
import time
import sys
import os
from pathlib import Path
from dotenv import load_dotenv

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from meta_agent.evolution.orchestrator import SelfEvolutionOrchestrator
from meta_agent.blueprint.store import BlueprintCoverageStore
from meta_agent.blueprint.objectives import ObjectiveLoader
from meta_agent.evolution.token_budget import TokenBudgetConfig


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run Quentin Meta-Agent self-evolution daemon."
    )
    parser.add_argument(
        "--cycle-interval-seconds",
        type=int,
        default=60,
        help="Interval in seconds between self-evolution cycles (default 60).",
    )
    parser.add_argument(
        "--max-cycles",
        type=int,
        default=0,
        help="Max number of cycles to run. 0 means infinite until deadline or manual stop.",
    )
    parser.add_argument(
        "--deadline",
        type=str,
        default="",
        help="Deadline in ISO format (e.g., 2025-03-31T23:59:00). Stops when deadline is reached.",
    )
    parser.add_argument(
        "--log-dir",
        type=str,
        default="logs/self_evo_daemon",
        help="Directory for daemon logs.",
    )
    parser.add_argument(
        "--max-tokens-per-cycle",
        type=int,
        default=None,
        help="Overrides max_tokens_per_cycle in TokenBudgetConfig.",
    )
    parser.add_argument(
        "--max-actions-per-cycle",
        type=int,
        default=None,
        help="Overrides max_actions_per_cycle in TokenBudgetConfig.",
    )
    return parser.parse_args()


def parse_deadline(deadline_str: str) -> dt.datetime | None:
    if not deadline_str:
        return None
    try:
        if "T" in deadline_str:
            return dt.datetime.fromisoformat(deadline_str)
        d = dt.date.fromisoformat(deadline_str)
        return dt.datetime.combine(d, dt.time(23, 59, 59))
    except Exception:
        print(f"[WARN] Invalid deadline format: {deadline_str}. Ignoring deadline.", file=sys.stderr)
        return None


def should_stop_by_deadline(deadline: dt.datetime | None) -> bool:
    if not deadline:
        return False
    return dt.datetime.now() >= deadline

def main() -> None:
    load_dotenv()
    args = parse_args()
    deadline_dt = parse_deadline(args.deadline)

    log_dir = Path(args.log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)

    # Prepare TokenBudgetConfig
    token_budget_cfg = TokenBudgetConfig()
    if args.max_tokens_per_cycle is not None:
        token_budget_cfg.max_tokens_per_cycle = args.max_tokens_per_cycle
    if args.max_actions_per_cycle is not None:
        token_budget_cfg.max_actions_per_cycle = args.max_actions_per_cycle


    orchestrator = SelfEvolutionOrchestrator(token_budget_config=token_budget_cfg) # Pass config
    coverage_store = BlueprintCoverageStore() # These might be initialized within orchestrator if it provides them
    objective_loader = ObjectiveLoader() # Same here

    cycle_idx = 0

    print("[INFO] Self-evolution daemon started.")
    if deadline_dt:
        print(f"[INFO] Deadline: {deadline_dt.isoformat()}")

    while True:
        cycle_idx += 1
        now = dt.datetime.now().isoformat()

        if args.max_cycles > 0 and cycle_idx > args.max_cycles:
            print(f"[INFO] Reached max_cycles={args.max_cycles}, exiting.")
            break

        if should_stop_by_deadline(deadline_dt):
            print("[INFO] Reached deadline, exiting.")
            break

        print(f"\n[INFO] ===== Self-evo cycle {cycle_idx} at {now} =====")

        try:
            result = orchestrator.run_daily_self_evo_cycle()
        except Exception as e:
            print(f"[ERROR] self-evo cycle {cycle_idx} failed: {e}", file=sys.stderr)
            import traceback
            traceback.print_exc()
            # Decide whether to continue or break on error
            time.sleep(args.cycle_interval_seconds) # Wait before next cycle
            continue

        out = {
            "cycle_idx": cycle_idx,
            "timestamp": now,
            "result": result,
        }
        log_path = log_dir / f"cycle_{cycle_idx:06d}.json"
        log_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

        cov = result.get("blueprint_coverage") or {}
        token_usage = result.get("token_usage") or {}
        print(
            f"[INFO] Coverage: total={cov.get('total_sections')} "
            f"missing={cov.get('count_missing')} "
            f"planned={cov.get('count_planned')} "
            f"impl={cov.get('count_implemented')} "
            f"eval={cov.get('count_evaluated')} "
            f"self_evo={cov.get('count_self_evolving')}"
        )
        print(
            f"[INFO] Token usage this cycle: used_tokens={token_usage.get('used_tokens')} "
            f"/ max={token_usage.get('max_tokens_per_cycle')}"
        )

        time.sleep(args.cycle_interval_seconds)


if __name__ == "__main__":
    main()
