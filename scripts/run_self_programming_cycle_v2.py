import argparse
from typing import List

from meta_agent.self_programming.engine_v2 import (
    SelfProgrammingEngineV2,
    SelfProgrammingConfig,
    GapLike,
)

def collect_top_gaps(limit: int) -> List[GapLike]:
    """
    Collect top blueprint gaps from the YAML blueprint tracker (offline, deterministic).
    Falls back to an empty list if the blueprint file is missing.
    """
    try:
        from meta_agent.blueprint.gap_tracker_v2 import BlueprintGapTrackerV2
    except Exception:
        return []

    tracker = BlueprintGapTrackerV2(blueprint_path="blueprint/blueprint_v2.yml", project_root=".")
    gaps = tracker.find_top_gaps(limit=limit, min_priority=1)
    return [g.to_gap_like() for g in gaps]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run self-programming v2 cycle for blueprint gaps."
    )
    parser.add_argument(
        "--backend",
        type=str,
        default="codex_cli",
        help="Coder backend to use: codex_cli | gemini_cli | ...",
    )
    parser.add_argument(
        "--max-gaps",
        type=int,
        default=1,
        help="Max gaps to process in one cycle.",
    )
    parser.add_argument(
        "--disable-research",
        action="store_true",
        help="Disable web research before code generation.",
    )
    args = parser.parse_args()

    cfg = SelfProgrammingConfig(
        default_coder_backend=args.backend,
        enable_research=not args.disable_research,
        max_gaps_per_cycle=args.max_gaps,
    )

    engine = SelfProgrammingEngineV2(config=cfg)
    
    print("Finding top gaps to address (blueprint tracker v2)...")
    gaps = collect_top_gaps(limit=args.max_gaps)

    if not gaps:
        print("No gaps found to process (blueprint file missing or no planned gaps).")
        return
        
    print(f"Found {len(gaps)} gaps. Running engine...")
    engine.run_for_gaps(gaps, backend=args.backend)
    print("Self-programming cycle finished.")


if __name__ == "__main__":
    main()
