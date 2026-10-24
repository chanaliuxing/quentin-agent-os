#!/usr/bin/env python
# scripts/run_blueprint_self_update_cycle.py
import argparse
from pathlib import Path

from meta_agent.blueprint.self_update_v2 import (
    BlueprintSelfUpdateEngineV2,
    BlueprintSelfUpdateConfig,
)
from meta_agent.blueprint.patch_types import BlueprintPatch, make_blueprint_patch_id

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run blueprint self-update cycle (v2) manually.",
    )
    parser.add_argument("--blueprint", type=str, default="blueprint/blueprint.md", help="Path to the blueprint markdown file.")
    parser.add_argument("--auto-apply", action="store_true", help="Allow auto-applying low-risk patches.")
    parser.add_argument("--section", type=str, help="Target section to modify.")
    parser.add_argument("--new-content", type=str, help="New content to apply.")
    args = parser.parse_args()

    cfg = BlueprintSelfUpdateConfig(
        blueprint_path=Path(args.blueprint),
        allow_auto_apply_low_risk=args.auto_apply,
    )
    engine = BlueprintSelfUpdateEngineV2(config=cfg)

    # This script can be used for manual testing by providing content.
    if args.section and args.new_content:
        print(f"Manually applying patch to section: {args.section}")
        patch = BlueprintPatch(
            id=make_blueprint_patch_id(),
            created_at=dt.datetime.utcnow().isoformat(),
            source="manual_cli",
            author="human",
            target_section=args.section,
            change_type="rewrite_section",
            new_content=args.new_content,
            rationale="Manual update from CLI.",
            risk_level="low",
            status="proposed",
        )
        result = engine.apply_patch(patch, auto=args.auto_apply)
        print(f"Patch applied with status: {result.status}")
    else:
        # Minimal manual mode: list pending patches if available.
        print("No patch specified. Provide --section and --new-content to apply a manual patch.")
        print("Patch history (last 5):")
        try:
            log_path = cfg.patch_log_path
            if log_path.exists():
                text = log_path.read_text(encoding="utf-8", errors="ignore")
                lines = [ln for ln in text.splitlines() if ln.strip()]
                for ln in lines[-5:]:
                    print(ln[:240])
            else:
                print("(no patch log found)")
        except Exception:
            print("(failed to read patch log)")
        return

if __name__ == "__main__":
    # Add datetime import for manual patch creation
    import datetime as dt
    main()
