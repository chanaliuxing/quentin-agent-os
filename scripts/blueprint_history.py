#!/usr/bin/env python
# scripts/blueprint_history.py
from __future__ import annotations
import argparse

from meta_agent.blueprint.version_store import BlueprintVersionStore


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Blueprint version history viewer")
    p.add_argument("--limit", type=int, default=20, help="Number of recent versions to show.")
    p.add_argument("--show", type=str, default=None, help="Show details and diff for a specific version_id.")
    p.add_argument("--patch", type=str, default=None, help="Filter versions by patch_id.")
    return p.parse_args()


def print_timeline(store: BlueprintVersionStore, limit: int, patch_filter: str | None) -> None:
    records = store.list_versions()
    if patch_filter:
        records = [r for r in records if r.patch_id == patch_filter]
    
    records = records[:limit]

    if not records:
        print("No blueprint versions recorded yet.")
        return

    print(f"{ 'VersionId':<28} {'CreatedAt':<26} {'PatchId':<20} {'Risk':<7} {'Source'}")
    print("-" * 120)
    for r in records:
        print(f"{r.version_id:<28} {r.created_at:<26} {r.patch_id[:20]:<20} {r.risk_level:<7} {r.source}")


def print_version_detail(store: BlueprintVersionStore, version_id: str) -> None:
    rec = store.get_version(version_id)
    if rec is None:
        print(f"Version '{version_id}' not found.")
        return

    print("\n=== Version Info ===")
    for key, value in rec.__dict__.items():
        print(f"{key:<15}: {value}")

    diff_text = store.load_diff_text(version_id)
    if diff_text:
        print("\n=== Unified Diff ===")
        print(diff_text)


def main() -> None:
    args = parse_args()
    store = BlueprintVersionStore("data/blueprint/versions")

    if args.show:
        print_version_detail(store, args.show)
    else:
        print_timeline(store, limit=args.limit, patch_filter=args.patch)


if __name__ == "__main__":
    main()
