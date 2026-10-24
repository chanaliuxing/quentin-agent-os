import os
from dataclasses import dataclass, field
from typing import Literal, Dict, Any
from pydantic import BaseModel # Import BaseModel

# Canonical env names (blueprint v3): sandbox / staging / prod.
# Keep "production" as a backward-compatible alias (normalized in Settings.__post_init__).
EnvName = Literal["sandbox", "staging", "prod", "production"]


@dataclass
class LLMConfig:
    provider: str = field(default_factory=lambda: os.getenv("LLM_PROVIDER", "ollama"))
    model: str = field(default_factory=lambda: os.getenv("LLM_MODEL"))
    critic_model: str = field(default_factory=lambda: os.getenv("LLM_MODEL_CRITIC") or os.getenv("LLM_MODEL"))
    skeptic_model: str = field(default_factory=lambda: os.getenv("LLM_MODEL_SKEPTIC") or os.getenv("LLM_MODEL"))
    ollama_base_url: str = field(default_factory=lambda: os.getenv("LLM_BASE_URL", "http://localhost:11434"))
    extra: Dict[str, Any] = field(default_factory=dict)


@dataclass
class MemoryConfig:
    sts_decay_hours: int = 6         # STS 衰减周期
    mts_promotion_threshold: int = 3 # 被引用次数达到多少次升 MTS
    lts_promotion_threshold: int = 10
    max_sts_items: int = 1000        # 防止记忆膨胀


# BudgetConfig is now a Pydantic BaseModel
class BudgetConfig(BaseModel):
    """
    研究 & 自改预算配置：
    - 每天最多允许跑多少次「实验 / 自编程维护循环」
    - 将来可以扩展 token / 费用上限
    """
    max_experiments_per_day: int = 5
    max_tokens_per_day: int = 500_000  # 预留，当前还没强约束


@dataclass
class Settings:
    env: EnvName = "sandbox"
    llm: LLMConfig = field(default_factory=LLMConfig)
    memory: MemoryConfig = field(default_factory=MemoryConfig)
    # BudgetConfig is still passed as a dataclass field
    budget: BudgetConfig = field(default_factory=BudgetConfig)
    
    # [P5] Dynamic (AI-mutable) settings
    def get_dynamic(self, key: str, default: Any = None) -> Any:
        from quentin.config.dynamic_manager import get_dynamic_config
        return get_dynamic_config().get(key, default)

    def __post_init__(self) -> None:
        # Normalize aliases to canonical env names.
        if self.env == "production":
            self.env = "prod"  # type: ignore[assignment]
