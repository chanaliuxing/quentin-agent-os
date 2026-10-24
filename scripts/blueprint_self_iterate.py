"""
命令行入口示例：蓝皮书自迭代 run

用法（在仓库根目录）：
    python -m scripts.blueprint_self_iterate

你需要先实现 create_runtime_for_blueprint_self_iteration()
里如何构造 RuntimeFacade（接入你的 LLM、本地模型、多模型会议等）。
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Dict, List, Optional

from quentin.cli.blueprint_runner import (
    BlueprintSelfIterateConfig,
    run_blueprint_self_iteration,
)
from quentin.runtime.system import RuntimeFacade

# 新增 import：
from quentin.llm.ollama_client import OllamaLLMClient, OllamaModelConfig
from quentin.llm.datastore import ModelPerformanceDataStore
from quentin.llm.data_driven_router import DataDrivenModelRouter
from quentin.runtime.council import CouncilRuntime, CouncilConfig
from quentin.l3.research.experiments import ExperimentOrchestrator
from quentin.l3.research.layer import ResearchLayer
from quentin.memory.fabric import MemoryFabric
from quentin.tools.manager import ToolManager
from quentin.critic.core import SimpleCritic
from quentin.traces.core import JsonlTraceRecorder
from quentin.runtime.immune_loop import ImmuneLoop, AnomalyDetectorConfig
from quentin.sleep.loop import SleepLoop, SleepLoopConfig
from quentin.skills.evolution import SkillEvolutionLoop
from quentin.self_programming.engine import SelfProgrammingEngine
from quentin.planning import HierarchicalPlanner
from quentin.execution import Executor
from quentin.skills.registry import SkillRegistry

# 可选：初始化简单日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
)


from dataclasses import dataclass, field

@dataclass
class VariantRuntimeConfig:
    variant_id: str
    llm_model_name: str
    llm_base_url: str = "http://localhost:11434"
    llm_temperature: float = 0.3
    llm_top_p: float = 0.9
    llm_num_ctx: int = 8192
    llm_num_predict: int = 1024
    council_enabled: bool = False
    is_main_runtime: bool = False # Only one variant can be the main runtime

def create_runtime_for_blueprint_self_iteration(
    repo_root: str | Path = ".",
    variant_configs: Optional[List[VariantRuntimeConfig]] = None
) -> RuntimeFacade:
    """
    最小可运行版本的 RuntimeFacade，用本地 Ollama 模型 + 极简 Memory/Tool/Critic + 四大 Loop。
    可以通过 variant_configs 配置多个 RuntimeFacade 变体，用于实验。
    """
    repo_root = Path(repo_root).resolve()

    if variant_configs is None:
        # Default variants if not provided
        variant_configs = [
            VariantRuntimeConfig(variant_id="baseline", llm_model_name="qwen3-vl:latest"),
            VariantRuntimeConfig(variant_id="council", llm_model_name="qwen3-vl:latest", council_enabled=True, is_main_runtime=True),
        ]
    
    # Create a single data-driven model router for all variants
    datastore = ModelPerformanceDataStore(db_path=repo_root / "data" / "model_performance.db")
    
    all_models = {cfg.llm_model_name for cfg in variant_configs}
    llm_clients = {
        model_name: OllamaLLMClient(OllamaModelConfig(name=model_name))
        for model_name in all_models
    }
    
    model_router = DataDrivenModelRouter(datastore=datastore, llm_clients=llm_clients)
    
    variants_runtimes: Dict[str, RuntimeFacade] = {}
    main_runtime: Optional[RuntimeFacade] = None

    # Common components (shared across all runtimes if not variant-specific)
    memory_fabric = MemoryFabric(db_path=repo_root / "data" / "memory.db")
    tool_manager = ToolManager()
    trace_recorder = JsonlTraceRecorder(repo_root=repo_root)
    skill_registry = SkillRegistry(path=repo_root / "data" / "skills.json")

    # Read environment variables for global flags
    critic_enabled_global = os.getenv("CRITIC_ENABLED", "0") == "1"
    enable_evolver_sandbox_global = os.getenv("ENABLE_EVOLVER_SANDBOX", "0") == "1"

    for config in variant_configs:
        # The model router is now shared. Variants may differ in other aspects, like council enablement.
        llm_for_components = llm_clients[config.llm_model_name] # For components that need a direct LLM
        
        current_council = create_default_ollama_council(base_url=config.llm_base_url) if config.council_enabled else None
        
        critic = SimpleCritic(llm=llm_for_components, enabled=critic_enabled_global)
        planner = HierarchicalPlanner(llm=llm_for_components, skill_registry=skill_registry)
        executor = Executor(tool_manager=tool_manager, llm=llm_for_components, trace_recorder=trace_recorder)

        runtime_instance = RuntimeFacade(
            model_router=model_router, # Use the shared data-driven router
            memory_fabric=memory_fabric,
            tool_manager=tool_manager,
            critic=critic,
            planner=planner,
            executor=executor,
            council=current_council,
            repo_root=repo_root,
            research_layer=None, # Will attach later
            trace_recorder=trace_recorder,
        )
        variants_runtimes[config.variant_id] = runtime_instance
        if config.is_main_runtime:
            main_runtime = runtime_instance
    
    if main_runtime is None and variants_runtimes:
        # If no main_runtime explicitly set, pick the first one
        main_runtime = list(variants_runtimes.values())[0]
    elif main_runtime is None:
        raise ValueError("No runtime variants configured.")

    # 6) ExperimentOrchestrator + ResearchLayer
    exp_orch = ExperimentOrchestrator(
        repo_root=repo_root,
        variants_runtimes=variants_runtimes,
    )
    research_layer = ResearchLayer(
        repo_root=repo_root,
        experiment_orchestrator=exp_orch,
    )

    # 7) 构造自编程引擎，并挂到 ResearchLayer 上
    self_prog_engine = SelfProgrammingEngine(
        repo_root=repo_root,
        llm=main_runtime.model_router,  # Use main_runtime's LLM for self-programming
        experiment_orchestrator=exp_orch,
        trace_recorder=trace_recorder,
        enable_sandbox=enable_evolver_sandbox_global, # Pass global enable_evolver_sandbox
    )
    research_layer.attach_self_programming_engine(self_prog_engine)

    # Attach the same research_layer to all created runtimes
    for rt in variants_runtimes.values():
        rt.attach_research_layer(research_layer)

    # 8) 构造四大 Loop，并挂到“主 runtime”以及其他 variants (if needed)
    immune_loop = ImmuneLoop(
        config=AnomalyDetectorConfig(
            window_size=100,
            error_rate_threshold=0.3,
            max_latency_ms=None,
        ),
        trace_recorder=trace_recorder,
    )

    sleep_loop = SleepLoop(
        config=SleepLoopConfig(
            max_sts_candidates=500,
            max_records_per_run=500,
        ),
        trace_recorder=trace_recorder,
        memory_fabric=memory_fabric,
        council=main_runtime.council,
        repo_root=repo_root,
    )

    skill_evolution_loop = SkillEvolutionLoop(
        trace_recorder=trace_recorder,
        experiment_orchestrator=exp_orch,
        llm=main_runtime.model_router,  # Use main_runtime's LLM for skill evolution
    )

    # 把这些 loop 挂在主 runtime 上（认知执行主路径由 RuntimeFacade -> Container.cognitive_loop 提供）
    main_runtime.immune_loop = immune_loop
    main_runtime.sleep_loop = sleep_loop
    main_runtime.skill_evolution_loop = skill_evolution_loop
    
    # Other runtimes might need their own cognitive loops if they are meant to run independently.
    # For now, let's assume other variants are mostly for evaluation in ExperimentOrchestrator.
    # If a variant needs to run a full task with its own cognitive loop, it would need its own.

    # 9) 返回作为“主中控”的 runtime
    return main_runtime


def main() -> None:
    repo_root = Path(".").resolve()

    # 1) 构造 RuntimeFacade (现在可以传入 variant_configs)
    # 使用环境变量来配置 LLM
    llm_base_url = os.getenv("LLM_BASE_URL", "http://localhost:11434")
    llm_model = os.getenv("LLM_MODEL", "qwen3-vl:latest")
    llm_local_models_str = os.getenv("LLM_LOCAL_MODELS")
    critic_enabled = os.getenv("CRITIC_ENABLED", "0") == "1"
    
    all_variant_configs: List[VariantRuntimeConfig] = []

    # Add the base LLM variant
    all_variant_configs.append(
        VariantRuntimeConfig(
            variant_id="base_llm", 
            llm_model_name=llm_model, 
            llm_base_url=llm_base_url
        )
    )

    # Add other local models from env var
    if llm_local_models_str:
        local_models = [m.strip() for m in llm_local_models_str.split(",") if m.strip()]
        for model_name in local_models:
            all_variant_configs.append(
                VariantRuntimeConfig(
                    variant_id=f"local_{model_name.replace(':', '_').replace('-', '_')}",
                    llm_model_name=model_name,
                    llm_base_url=llm_base_url
                )
            )

    # Add council-enabled variant
    all_variant_configs.append(
        VariantRuntimeConfig(
            variant_id="council_enabled", 
            llm_model_name=llm_model, 
            llm_base_url=llm_base_url,
            council_enabled=True,
            is_main_runtime=True # Designate this as the main runtime if needed
        )
    )

    runtime = create_runtime_for_blueprint_self_iteration(repo_root=repo_root, variant_configs=all_variant_configs)

    # 2) 配置本次自迭代 run
    cfg = BlueprintSelfIterateConfig(
        max_gaps_per_cycle=5,
        research_strategy="simple",
        max_experiments=None,  # 交给预算控制器
        repo_root=str(repo_root),
        run_tag=None,  # 例如 "local_ollama_v1"
    )

    # 3) 跑一整圈：扫描能力 → gap → 实验 → 研究周期
    result = run_blueprint_self_iteration(runtime, cfg)

    # 4) 打印结果（命令行快速查看）
    print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))

import os

if __name__ == "__main__":
    main()
