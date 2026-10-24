# quentin/llm/types.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


LLMProvider = Literal[
    "ollama",
    "stub",
    "openai",
    "gemini",
    "deepseek",
    "openrouter",
    "anthropic",
    "unknown",
]


@dataclass
class LLMConfig:
    """
    描述一个 LLM 成员：
    - provider : provider id (ollama/openai/gemini/deepseek/...)
    - model    : provider model id，例如 "qwen3-vl:latest" / "gpt-4o-mini"
    - role     : 这个模型在“会议”里的角色，如 "planner" / "critic" / "safety"
    """
    provider: LLMProvider
    model: str
    role: str = "general"
