#!/usr/bin/env python
# scripts/blueprint_rollback.py
from __future__ import annotations
import argparse
from pathlib import Path

from meta_agent.blueprint.version_store import BlueprintVersionStore


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Rollback blueprint to a specific version")
    p.add_argument(
        "--to",
        dest="version_id",
        required=True,
        help="Target version_id, e.g., v20251206-103012-ABCD",
    )
    p.add_argument(
        "--blueprint",
        type=str,
        default="blueprint/blueprint.md",
        help="Path to the blueprint markdown file.",
    )
    p.add_argument(
        "--reason",
        type=str,
        default="manual rollback from CLI",
        help="Reason for the rollback, recorded in metadata.",
    )
    return p.parse_args()


def main() -> None:
    args = parse_args()
    store = BlueprintVersionStore("data/blueprint/versions")
    bp_path = Path(args.blueprint)

    print(f"Attempting to roll back '{bp_path}' to version '{args.version_id}'...")
    
    ok = store.rollback_to(
        version_id=args.version_id,
        blueprint_path=bp_path,
        reason=args.reason,
        author="human_cli",
    )

    if not ok:
        print(f"[ERROR] Failed to rollback. Check if version_id '{args.version_id}' exists.")
        return

    print(f"[OK] Successfully rolled back '{bp_path}' to version '{args.version_id}'.")
    print("A new version record has been created for this rollback action.")
    print("Run 'python scripts/blueprint_history.py --limit 5' to see the latest versions.")


if __name__ == "__main__":
    main()
