import sys
import os
import argparse
from datetime import datetime

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from meta_agent.self_programming.auditing.auditor import BlueprintAuditor
from meta_agent.self_programming.auditing.delta import load_report, compute_delta
from meta_agent.self_programming.auditing.backlog import generate_backlog, save_backlog
from meta_agent.self_programming.auditing.task_builder import RemediationTaskBuilder
from meta_agent.self_programming.auditing.task_council import TaskCouncil


def main():
    parser = argparse.ArgumentParser(description="Run Evidence-based Gap Analysis")
    parser.add_argument("--spec", default="blueprint/meta_agent_v3_spec.json", help="Path to spec file")
    parser.add_argument("--caps", default="data/blueprint/capabilities.json", help="Path to legacy capabilities file")
    parser.add_argument("--out", default="data/blueprint/audit_report.json", help="Output path")
    parser.add_argument("--delta-from", dest="delta_from", default=None, help="Previous audit report to diff against")
    parser.add_argument("--delta-out", dest="delta_out", default="data/blueprint/audit_delta.json", help="Where to write delta")
    parser.add_argument("--snapshot", action="store_true", help="Save timestamped snapshot alongside --out")
    parser.add_argument("--backlog-out", dest="backlog_out", default="data/blueprint/backlog.json", help="Where to write backlog recommendations")
    parser.add_argument("--backlog-top", dest="backlog_top", type=int, default=20, help="Top N items for backlog")
    parser.add_argument("--run-tests", action="store_true", help="Run tests_expected for each requirement (slow, optional)")
    parser.add_argument("--runtime-events", dest="runtime_events", default=None, help="Directory containing runtime events (jsonl) to scan for runtime_signals")
    parser.add_argument("--tasks-out", dest="tasks_out", default="data/blueprint/remediation_tasks.json", help="Where to write remediation tasks")
    parser.add_argument("--tasks-top", dest="tasks_top", type=int, default=20, help="Top N tasks to emit")
    parser.add_argument("--tasks-reviewed-out", dest="tasks_reviewed_out", default="data/blueprint/remediation_tasks_reviewed.json", help="Where to write council-reviewed tasks")
    parser.add_argument("--no-council", action="store_true", help="Skip council review of tasks")

    args = parser.parse_args()

    project_root = os.getcwd()
    auditor = BlueprintAuditor(project_root)

    print(f"🔍 Starting Audit on {args.spec}...")

    try:
        results, warnings, errors = auditor.audit_spec(
            args.spec,
            args.caps,
            run_tests=args.run_tests,
            runtime_events_dir=args.runtime_events,
        )
        auditor.save_report(results, args.out, warnings, errors)

        if args.snapshot:
            ts_path = args.out.replace(".json", f"_{datetime.utcnow().strftime('%Y%m%d')}.json")
            auditor.save_report(results, ts_path, warnings, errors)

        stats = {"implemented": 0, "partial": 0, "unknown": 0, "gap": 0}
        for r in results:
            stats[r.status] += 1

        print("\n📊 Audit Summary:")
        print(f"  ✅ Implemented: {stats['implemented']}")
        print(f"  ⚠️  Partial:     {stats['partial']}")
        print(f"  ❓ Unknown:     {stats['unknown']}")
        print(f"  ❌ Gap:         {stats['gap']}")
        if warnings:
            print(f"  ⚠️  Warnings:   {warnings}")
        if errors:
            print(f"  ❌ Errors:     {errors}")

        if args.delta_from:
            prev_report = load_report(args.delta_from)
            delta = compute_delta(prev_report, results)
            os.makedirs(os.path.dirname(args.delta_out), exist_ok=True)
            with open(args.delta_out, "w", encoding="utf-8") as f:
                import json
                json.dump(delta, f, ensure_ascii=False, indent=2)
            print(f"\nΔ Delta written to {args.delta_out}:")
            print(f"  status_changed: {len(delta.get('status_changed', []))}")
            print(f"  new_gaps: {len(delta.get('new_gaps', []))}")
            print(f"  closed_gaps: {len(delta.get('closed_gaps', []))}")

        if args.backlog_out:
            backlog = generate_backlog(results, top_n=args.backlog_top)
            save_backlog(backlog, args.backlog_out)
            print(f"\n📋 Backlog written to {args.backlog_out} (items={len(backlog.get('items', []))})")

        if args.tasks_out:
            builder = RemediationTaskBuilder(max_tasks=args.tasks_top)
            tasks = builder.build(results, delta if args.delta_from else None)
            os.makedirs(os.path.dirname(args.tasks_out), exist_ok=True)
            with open(args.tasks_out, "w", encoding="utf-8") as f:
                import json
                json.dump(tasks, f, ensure_ascii=False, indent=2)
            print(f"🛠️  Tasks written to {args.tasks_out} (count={len(tasks.get('tasks', []))})")
            if not args.no_council and args.tasks_reviewed_out:
                council = TaskCouncil(max_rounds=1)
                reviewed = council.review(tasks.get("tasks", []))
                os.makedirs(os.path.dirname(args.tasks_reviewed_out), exist_ok=True)
                with open(args.tasks_reviewed_out, "w", encoding="utf-8") as f:
                    import json
                    json.dump(reviewed, f, ensure_ascii=False, indent=2)
                print(f"🏛️  Council review written to {args.tasks_reviewed_out} (approved={len(reviewed.get('approved', []))})")

    except Exception as e:
        print(f"❌ Fatal Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
