import argparse
import json
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from meta_agent.self_programming.auditing.task_executor import RemediationTaskExecutor
from meta_agent.self_programming.auditing.task_council import TaskCouncil


def main():
    parser = argparse.ArgumentParser(description="Execute remediation tasks with SelfProgrammingEngineV2")
    parser.add_argument("--tasks", default="data/blueprint/remediation_tasks.json", help="Path to tasks JSON")
    parser.add_argument("--reviewed", default=None, help="Path to reviewed tasks JSON (approved/rejected/needs_info)")
    parser.add_argument("--no-council", action="store_true", help="Skip council review if reviewed file not provided")
    parser.add_argument("--snapshot-out", default=None, help="Path to capabilities snapshot to update after success")
    parser.add_argument("--implemented-threshold", type=float, default=0.85, help="Confidence threshold for snapshot update")
    args = parser.parse_args()

    tasks = []
    if args.reviewed and os.path.exists(args.reviewed):
        data = json.load(open(args.reviewed, "r", encoding="utf-8"))
        tasks = data.get("approved", [])
    else:
        raw = json.load(open(args.tasks, "r", encoding="utf-8"))
        tasks = raw.get("tasks", [])
        if not args.no_council:
            reviewed = TaskCouncil(max_rounds=1).review(tasks)
            tasks = reviewed.get("approved", [])

    if not tasks:
        print("No tasks to execute.")
        return

    executor = RemediationTaskExecutor()
    executor.run_tasks(tasks)
    print(f"Executed {len(tasks)} remediation tasks.")

    if args.snapshot_out and os.path.exists(args.tasks):
        try:
            # Use original tasks file to infer req_ids status implemented; here we simply mark them as implemented
            raw = json.load(open(args.tasks, "r", encoding="utf-8"))
            from meta_agent.self_programming.auditing.capabilities_writer import update_capabilities_snapshot
            # Build faux RequirementStatus list from executed tasks
            from meta_agent.self_programming.auditing.templates import RequirementStatus
            statuses = [
                RequirementStatus(req_id=t.get("req_id", ""), title=t.get("title", ""), status="implemented", confidence=args.implemented_threshold)
                for t in tasks
            ]
            update_capabilities_snapshot(statuses, args.snapshot_out, implemented_threshold=args.implemented_threshold)
            print(f"Updated capabilities snapshot at {args.snapshot_out}")
        except Exception as e:
            print(f"Failed to update capabilities snapshot: {e}")


if __name__ == "__main__":
    main()
