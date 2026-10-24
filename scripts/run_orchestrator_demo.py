# scripts/run_orchestrator_demo.py
import os
import sys
import subprocess
import json

# Add project root to sys.path
sys.path.insert(0, os.getcwd())

# --- Real Imports ---
from meta_agent.evolution.orchestrator import SelfEvolutionOrchestrator
from meta_agent.memory.fabric import MemoryFabric

def main():
    print("--- Running Self-Evolution Orchestrator Demo ---")

    # 1. Prepare demo files (no git reset here to preserve existing state)
    print("Preparing demo files...")
    with open("demo.py", "w") as f:
        f.write("def foo(x: int) -> int:\n    return x + 1\n")
    with open("tests/test_demo.py", "w") as f:
        f.write("from demo import foo\ndef test_foo():\n    assert foo(1) == 2\n")

    # 2. Instantiate the orchestrator
    print("Instantiating SelfEvolutionOrchestrator...")
    orchestrator = SelfEvolutionOrchestrator()

    # 3. Run the daily cycle
    print("Running the daily self-evolution cycle...")
    result = orchestrator.run_daily_self_evo_cycle()

    # 4. Print results
    print("\n--- Self-Evolution Cycle Result ---")
    # Use a custom encoder to handle non-serializable objects if any
    class CustomEncoder(json.JSONEncoder):
        def default(self, o):
            if hasattr(o, '__dict__'):
                return o.__dict__
            return str(o) # Fallback
    print(json.dumps(result, indent=2, cls=CustomEncoder))
    print("------------------------------------")


if __name__ == "__main__":
    main()
