"""
按 proposal_id 应用 Patch。

用法（仓库根目录）：
  # 只预览（dry-run），不写文件：
  python -m scripts.apply_patch --proposal-id <ID>

  # 真正应用：
  python -m scripts.apply_patch --proposal-id <ID> --apply
"""

from __future__ import annotations

import argparse
from pathlib import Path

from quentin.traces.core import JsonlTraceRecorder
from quentin.self_programming.apply import PatchApplier


def main() -> None:
    parser = argparse.ArgumentParser(description="Apply a patch proposal safely.")
    parser.add_argument("--proposal-id", required=True, help="Patch proposal_id to apply.")
    parser.add_argument(
        "--repo-root",
        type=str,
        default=".",
        help="Repository root (default: current directory).",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually modify files. If omitted, only do a dry-run.",
    )
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    recorder = JsonlTraceRecorder(repo_root=repo_root)
    applier = PatchApplier(repo_root=repo_root, trace_recorder=recorder)

    log = applier.apply_by_id(args.proposal_id, dry_run=not args.apply)

    print("status     :", log.status)
    print("message    :", log.message)
    print("proposal   :", log.proposal_id)
    print("target     :", log.target_path)
    print("backup     :", log.backup_path)
    print("dry_run    :", log.dry_run)
    print("applied_at :", log.applied_at)


if __name__ == "__main__":
    main()
