#!/usr/bin/env python
# scripts/blueprint_impact_report.py
from __future__ import annotations
import argparse

from meta_agent.blueprint.impact_analyzer import BlueprintImpactAnalyzer

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Blueprint impact report")
    p.add_argument("--versions", type=int, default=10, help="Analyze the last N versions.")
    p.add_argument("--window-hours", type=int, default=24, help="Before/after comparison window in hours.")
    return p.parse_args()

def main() -> None:
    args = parse_args()
    analyzer = BlueprintImpactAnalyzer(
        blueprint_versions_root="data/blueprint/versions",
        metrics_log_path="logs/runtime_metrics.jsonl", # Assumes this log exists
        window_hours=args.window_hours,
    )
    report = analyzer.build_report(limit_versions=args.versions)

    print(f"Blueprint Impact Report (window={report.window_hours}h, generated_at={report.generated_at})")
    print("-" * 120)
    print(f"{'VersionId':<28} {'CreatedAt':<20} {'Risk':<7} {'Effect':<11} {'ΔSuccess':<11} {'ΔError':<11} {'TargetSection'}")
    print("-" * 120)

    for item in report.items:
        ds = f"{item.delta_success_rate:+.3f}" if item.delta_success_rate is not None else "NA"
        de = f"{item.delta_error_rate:+.3f}" if item.delta_error_rate is not None else "NA"
        print(
            f"{item.version_id:28} {item.created_at[:19]:<20} {item.risk_level:<7} {item.effect_label:<11} "
            f"{ds:<11} {de:<11} {item.target_section[:30]}"
        )

if __name__ == "__main__":
    main()
