# scripts/run_self_evolution_tick.py
import argparse

from meta_agent.evolution.orchestrator import (
    SelfEvolutionOrchestrator,
    SelfEvolutionConfig,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run a single self-evolution tick for the Meta-Agent.",
    )
    parser.add_argument(
        "--mode",
        type=str,
        default="daily",
        choices=["daily", "hourly", "manual"],
        help="Tick mode: affects snapshot window etc.",
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
        help="Project root for resolving impl_refs.",
    )
    parser.add_argument(
        "--auto-apply-code",
        action="store_true",
        help="Allow auto applying code patches that pass governance & safety.",
    )
    parser.add_argument(
        "--auto-apply-blueprint",
        action="store_true",
        help="Allow auto applying blueprint patches that pass governance & safety.",
    )
    parser.add_argument(
        "--max-code-gaps",
        type=int,
        default=3,
        help="Max code gaps to handle in one tick.",
    )
    # This argument is defined in the doc but not directly used in the SelfEvolutionConfig,
    # it's a detail for later refinement. I'll leave it in.
    parser.add_argument(
        "--max-bp-patches",
        type=int,
        default=1,
        help="Max blueprint patches per cycle (forwarded into BlueprintSelfUpdateConfig).",
    )
    args = parser.parse_args()

    print("Initializing a self-evolution tick...")
    cfg = SelfEvolutionConfig(
        blueprint_path=args.blueprint,
        project_root=args.project_root,
        max_code_gaps_per_tick=args.max_code_gaps,
        max_blueprint_patches_per_tick=args.max_bp_patches,
        allow_auto_apply_code=args.auto_apply_code,
        allow_auto_apply_blueprint=args.auto_apply_blueprint,
        mode=args.mode,
    )

    orchestrator = SelfEvolutionOrchestrator(config=cfg)
    orchestrator.run_tick()
    print("Self-evolution tick finished.")


if __name__ == "__main__":
    main()
