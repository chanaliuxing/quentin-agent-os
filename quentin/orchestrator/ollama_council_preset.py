from __future__ import annotations

from typing import Dict, Any, List
from pathlib import Path

from quentin.llm.ollama_client import OllamaLLMClient, OllamaModelConfig
from quentin.orchestrator.council import MultiModelCouncil


def create_default_ollama_council(
    base_url: str = "http://localhost:11434",
) -> MultiModelCouncil:
    """
    使用你现有的几个 Ollama 模型，创建一个默认的 MultiModelCouncil。
    """
    import os
    main_model = os.getenv("LLM_MODEL")
    if not main_model:
         raise ValueError("Environment variable LLM_MODEL is not set.")
    critic_model = os.getenv("LLM_MODEL_CRITIC") or main_model
    skeptic_model = os.getenv("LLM_MODEL_SKEPTIC") or main_model

    # 你以后可以按需要改变权重、温度等
    model_cfgs = [
        OllamaModelConfig(name=main_model, base_url=base_url, temperature=0.3),
        OllamaModelConfig(name=critic_model, base_url=base_url, temperature=0.3),
        OllamaModelConfig(name=skeptic_model, base_url=base_url, temperature=0.4),
    ]

    panel = {
        cfg.name: OllamaLLMClient(cfg)
        for cfg in model_cfgs
    }

    # Assuming MultiModelCouncil constructor takes 'members' list of tuples as defined in previous steps
    # The text says "assuming MultiModelCouncil receives models: Dict", but my implementation in step 104.md takes list of tuples.
    # I will adapt to list of tuples to be compatible with my previous implementation.
    
    members_list = [(name, client) for name, client in panel.items()]
    
    # Also need an aggregator. Let's pick the first one (qwen).
    aggregator = panel[model_cfgs[0].name]

    council = MultiModelCouncil(
        members=members_list,
        aggregator=aggregator
        # member_roles is optional
    )
    return council
