# scripts/run_immune_cycle.py
import argparse

from meta_agent.immune.runner import run_immune_cycle


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the ImmuneLoop v2 (self-diagnosis & self-healing)."
    )
    parser.add_argument(
        "--window-hours",
        type=int,
        default=24,
        help="Time window (in hours) for metrics aggregation.",
    )
    args = parser.parse_args()

    run_immune_cycle(window_hours=args.window_hours)


if __name__ == "__main__":
    main()
