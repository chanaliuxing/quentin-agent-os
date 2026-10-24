from quentin.self_programming.skill_impl_runner import run_skill_impl_cycle
from quentin.skills.registry import SkillRegistry
from quentin.memory.fabric import MemoryFabric
from quentin.self_programming.engine import SelfProgrammingEngine
from quentin.self_programming.eval import PatchEvaluator
from quentin.self_programming.apply import PatchApplier
from quentin.governance.patch_council import PatchGovernanceCouncil
from quentin.traces.core import JsonlTraceRecorder
from quentin.orchestrator.ollama_council_preset import create_default_ollama_council
from quentin.llm.ollama_client import OllamaLLMClient, OllamaModelConfig
from quentin.l3.research.experiments import ExperimentOrchestrator
from pathlib import Path
import os


def main():
    repo_root = Path(".").resolve()

    # Initialize components
    trace_recorder = JsonlTraceRecorder(repo_root=repo_root)
    skill_registry = SkillRegistry(path=repo_root / "data" / "skills.json")
    memory_fabric = MemoryFabric(db_path=repo_root / "data" / "memory.db")
    
    llm_model = os.getenv("LLM_MODEL", "qwen3-vl:latest")
    llm_clients = {llm_model: OllamaLLMClient(OllamaModelConfig(name=llm_model))}
    
    # In a real scenario, ExperimentOrchestrator would be initialized with variant runtimes
    exp_orch = ExperimentOrchestrator(repo_root=repo_root, variants_runtimes={})
    
    engine = SelfProgrammingEngine(
        repo_root=repo_root,
        llm=llm_clients[llm_model],
        experiment_orchestrator=exp_orch,
        trace_recorder=trace_recorder,
    )
    evaluator = PatchEvaluator(
        repo_root=repo_root,
        experiment_orchestrator=exp_orch,
        trace_recorder=trace_recorder,
    )
    applier = PatchApplier(repo_root=repo_root, trace_recorder=trace_recorder)
    council = create_default_ollama_council()
    govern_council = PatchGovernanceCouncil(
        repo_root=repo_root,
        council_callable=council,
        trace_recorder=trace_recorder,
    )

    domain = "generic"
    print(f"Running skill implementation cycle for domain: {domain}...")
    run_skill_impl_cycle(
        repo_root=repo_root,
        skill_registry=skill_registry,
        memory_fabric=memory_fabric,
        engine=engine,
        evaluator=evaluator,
        applier=applier,
        govern_council=govern_council,
        trace_recorder=trace_recorder,
        domain=domain,
        max_skills=1,
    )
    print("Skill implementation cycle finished.")

if __name__ == "__main__":
    main()
