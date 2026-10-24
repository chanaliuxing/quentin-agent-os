import sys
import os
from pathlib import Path

# Add repo root to sys.path
repo_root = Path(__file__).parent.parent
sys.path.insert(0, str(repo_root))

print(f"Repo root: {repo_root}")
print(f"Sys path: {sys.path}")

try:
    import meta_agent.self_programming.engine_v2 as mod
    print(f"Module file: {mod.__file__}")
    print("Attributes:", dir(mod))
    
    with open(mod.__file__, 'r') as f:
        content = f.read()
        print("Content preview:")
        print(content[:500])
        print("..." * 5)
        if "class PatchGovernanceCouncil" in content:
            print("FOUND: class PatchGovernanceCouncil")
        else:
            print("NOT FOUND: class PatchGovernanceCouncil")

except Exception as e:
    print(f"Error: {e}")