# scripts/generate_status_snapshot.py
import argparse

from meta_agent.monitoring.status_snapshot import write_status_snapshot


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate a status snapshot JSON for the Meta-Agent system."
    )
    parser.add_argument(
        "--window-hours",
        type=int,
        default=24,
        help="Time window (in hours) for metrics aggregation.",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="data/status_snapshot.json",
        help="Output JSON path.",
    )
    args = parser.parse_args()

    snapshot = write_status_snapshot(
        output_path=args.output,
        window_hours=args.window_hours,
    )

    print(f"[status] snapshot generated at {args.output}")
    print(f"  window_hours: {snapshot.window_hours}")
    print(f"  total_tasks: {snapshot.task_stats_overall.total}")
    print(f"  success_rate: {snapshot.task_stats_overall.success_rate:.3f}")
    print(f"  skills_total: {snapshot.skills.total}")
    print(f"  patches_evaluated: {snapshot.patches.total_evaluated}")
    print(f"  experiments_total: {snapshot.experiments.total}")


if __name__ == "__main__":
    main()
