from quentin.skills.evolution import SkillEvolutionLoop
from quentin.skills.registry import SkillRegistry
from quentin.memory.fabric import MemoryFabric
from quentin.traces.core import JsonlTraceRecorder
from quentin.orchestrator.ollama_council_preset import create_default_ollama_council
from pathlib import Path

def main():
    """
    Manually trigger a skill evolution cycle for a given domain.
    """
    repo_root = Path(".").resolve()
    
    trace_recorder = JsonlTraceRecorder(repo_root=repo_root)
    skill_registry = SkillRegistry(path=repo_root / "data" / "skills.json")
    memory_fabric = MemoryFabric(db_path=repo_root / "data" / "memory.db")
    council = create_default_ollama_council()

    skill_evolution_loop = SkillEvolutionLoop(
        trace_recorder=trace_recorder,
        skill_registry=skill_registry,
        memory_fabric=memory_fabric,
        council=council,
        repo_root=repo_root,
    )
    
    # For now, let's test with the 'generic' domain
    domain = "generic"
    print(f"Running skill evolution cycle for domain: {domain}...")
    
    new_skill = skill_evolution_loop.run_once(domain=domain)
    
    if new_skill:
        print(f"  New skill created: '{new_skill.name}' (ID: {new_skill.id})")
        print(f"  Implementation stub: {new_skill.impl_stub_path}")
    else:
        print("  No new skill was created.")

if __name__ == "__main__":
    main()
