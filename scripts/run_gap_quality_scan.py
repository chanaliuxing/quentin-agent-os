# scripts/run_gap_quality_scan.py
import argparse

from meta_agent.blueprint.gap_tracker_v2 import BlueprintGapTrackerV2


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run blueprint gap quality scan (v2).",
    )
    parser.add_argument(
        "--blueprint",
        type=str,
        default="blueprint/blueprint_v2.yml",
        help="Path to blueprint YAML/JSON file.",
    )
    parser.add_argument(
        "--project-root",
        type=str,
        default=".",
        help="Root path of the project (for resolving impl_refs).",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=10,
        help="How many top gaps to print.",
    )
    args = parser.parse_args()

    print(f"Running quality scan on blueprint: {args.blueprint}")
    tracker = BlueprintGapTrackerV2(
        blueprint_path=args.blueprint,
        project_root=args.project_root,
    )

    top_gaps = tracker.find_top_gaps(limit=args.limit)

    print(f"\nTop {len(top_gaps)} gaps to improve:\n")
    for g in top_gaps:
        q = g.quality
        q_str = (
            f"score={q.overall_score:.1f}, risk={q.risk_level}, maturity={q.impl_maturity}"
            if q
            else "no_quality_data"
        )
        print(f"- [{g.id}] ({g.category}, prio={g.priority}) {g.title}")
        print(f"  quality: {q_str}")
        if q and q.suggested_actions:
            print(f"  suggested_actions:")
            for act in q.suggested_actions[:3]:
                print(f"    - {act}")
        print()


if __name__ == "__main__":
    main()
