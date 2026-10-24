# meta_agent/runtime/council_config.py

from __future__ import annotations
from dataclasses import dataclass
from typing import Dict


@dataclass
class ModelConfig:
    name: str           # Ollama 模型名，如 "qwen3-vl:latest"
    provider: str       # "ollama" / "openai" / "gemini" 等，现阶段我们用 "ollama" 即可
    max_tokens: int = 4096
    temperature: float = 0.2


@dataclass
class CouncilRoleConfig:
    planner: ModelConfig
    critic: ModelConfig
    judge: ModelConfig


import os





main_model = os.getenv("LLM_MODEL", "qwen3-vl:latest") # Keep a safe but generic default here if env is totally missing, but ideally it's set


critic_model = os.getenv("LLM_MODEL_CRITIC") or main_model





DEFAULT_COUNCIL_CONFIG = CouncilRoleConfig(


    planner=ModelConfig(


        name=main_model,


        provider="ollama",


        max_tokens=4096,


        temperature=0.2,


    ),


    critic=ModelConfig(


        name=critic_model,


        provider="ollama",


        max_tokens=2048,


        temperature=0.2,


    ),


    judge=ModelConfig(


        name=main_model,


        provider="ollama",


        max_tokens=4096,


        temperature=0.1,


    )


)

