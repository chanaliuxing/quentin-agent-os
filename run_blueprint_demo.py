# run_blueprint_demo.py
import os
import subprocess
from meta_agent.evolution.blueprint_loop import (
    BlueprintImprovementLoop,
    BlueprintStore,
    BlueprintGapTracker,
    PatchEvaluator,
    PatchGovernanceCouncil,
    PatchApplier,
    MetricsSnapshotProvider,
    ImmuneLoop,
)
from meta_agent.self_programming.engine import SelfProgrammingEngine
from meta_agent.memory.fabric import MemoryFabric
from meta_agent.blueprint.objectives import ObjectiveLoader

def main():
    print("--- Running Blueprint Improvement Loop Demo ---")

    # 1. Reset workspace to a clean state
    print("Resetting workspace to a clean state...")
    subprocess.run(['git', 'reset', '--hard', 'HEAD'], check=True)
    subprocess.run(['git', 'clean', '-fd'], check=True)

    # 2. Create the demo file for the engine to modify
    demo_content = "def foo(x: int) -> int:\n    return x + 1\n"
    with open("demo.py", "w") as f:
        f.write(demo_content)
    
    # 3. Instantiate the BlueprintImprovementLoop with the real engine
    #    and placeholders for other dependencies.
    print("Instantiating BlueprintImprovementLoop with real SelfProgrammingEngine...")
    
    # The real engine
    self_prog_engine = SelfProgrammingEngine(repo_root=".")
    
    # Placeholders
    memory_fabric = MemoryFabric()
    objective_loader = ObjectiveLoader()

    blueprint_loop = BlueprintImprovementLoop(
        blueprint_store=BlueprintStore(),
        gap_tracker=BlueprintGapTracker(),
        self_prog=self_prog_engine,
        patch_evaluator=PatchEvaluator(),
        patch_governance=PatchGovernanceCouncil(),
        patch_applier=PatchApplier(),
        metrics_provider=MetricsSnapshotProvider(),
        immune_loop=ImmuneLoop(),
        memory=memory_fabric,
        objective_loader=objective_loader,
    )

    # 4. Run the loop
    print("Running the improvement loop...")
    result = blueprint_loop.run(max_sections=1)

    # 5. Print the results
    print("\n--- Blueprint Improvement Loop Result ---")
    import json
    print(json.dumps(result, indent=2))
    print("------------------------------------")

    # 6. Check git status to see if a new branch was created and committed to
    print("\n--- Final Git Status ---")
    subprocess.run(['git', 'branch'], check=True)
    print("------------------------")


if __name__ == "__main__":
    main()
