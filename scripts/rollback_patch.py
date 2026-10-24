"""
按 proposal_id 回滚 Patch（恢复到最近一次备份）。

用法：
  python -m scripts.rollback_patch --proposal-id <ID>
"""

from __future__ import annotations

import argparse
from pathlib import Path

from quentin.traces.core import JsonlTraceRecorder
from quentin.self_programming.apply import PatchApplier


def main() -> None:
    parser = argparse.ArgumentParser(description="Rollback the latest applied patch for a proposal.")
    parser.add_argument("--proposal-id", required=True, help="Patch proposal_id.")
    parser.add_argument(
        "--repo-root",
        type=str,
        default=".",
        help="Repository root (default: current directory).",
    )
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    recorder = JsonlTraceRecorder(repo_root=repo_root)
    applier = PatchApplier(repo_root=repo_root, trace_recorder=recorder)

    log = applier.rollback_by_proposal(args.proposal_id)

    print("status     :", log.status)
    print("message    :", log.message)
    print("proposal   :", log.proposal_id)
    print("target     :", log.target_path)
    print("backup     :", log.backup_path)
    print("applied_at :", log.applied_at)


if __name__ == "__main__":
    main()
