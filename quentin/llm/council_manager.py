from __future__ import annotations

import yaml
from pathlib import Path
from typing import Dict, Any, List, Optional
import logging

from quentin.llm.types import LLMConfig
from quentin.llm.multi_council import MultiAICouncil
from quentin.llm.router import ModelRouter

logger = logging.getLogger(__name__)

DEFAULT_COUNCILS_PATH = "quentin/config/councils.yaml"


class CouncilManager:
    """
    Manages loading and instantiation of MultiAICouncils from configuration.
    """

    def __init__(
        self,
        *,
        repo_root: str | Path = ".",
        config_path: str | Path = DEFAULT_COUNCILS_PATH,
        router: Optional[ModelRouter] = None,
    ) -> None:
        self.repo_root = Path(repo_root).resolve()
        self.config_path = self.repo_root / config_path
        self.router = router or ModelRouter()
        self._configs: Dict[str, Any] = {}
        self._load_config()

    def _load_config(self) -> None:
        if not self.config_path.exists():
            logger.warning(f"Council config not found at {self.config_path}, using empty defaults.")
            return

        try:
            with self.config_path.open("r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
                self._configs = data.get("councils", {})
        except Exception:
            logger.exception(f"Failed to load council config from {self.config_path}")

    def get_council(
        self,
        council_name: str,
        *,
        domain: str = "core",
        overrides: Optional[Dict[str, Any]] = None,
    ) -> MultiAICouncil:
        """
        Instantiates a MultiAICouncil by name (e.g., 'done_council', 'patch_council').
        Falls back to 'default' if not found, or a minimal hardcoded one if 'default' is missing.
        """
        cfg = self._configs.get(council_name)
        if not cfg:
            # Fallback to default if explicitly requested council is missing
            cfg = self._configs.get("default")
        
        if not cfg:
            # Fallback hardcoded if no config at all
            logger.warning(f"Council '{council_name}' not found and no 'default' config. Using minimal fallback.")
            return self._create_fallback_council(domain)

        members_cfg = cfg.get("members", [])
        members: List[LLMConfig] = []

        for m_cfg in members_cfg:
            name = m_cfg.get("name", "unknown")
            role_desc = m_cfg.get("role", "Assistant")
            strategy = m_cfg.get("provider_strategy", "router:general")
            
            # Resolve strategy to actual LLMConfig
            llm_conf = self._resolve_strategy(strategy, domain)
            
            # Create final member config with specific role
            members.append(LLMConfig(
                provider=llm_conf.provider,
                model=llm_conf.model,
                role=f"{name} ({role_desc})", # Embed description in role for context
                api_key=llm_conf.api_key,
                api_base=llm_conf.api_base,
            ))

        return MultiAICouncil(members=members)

    def _resolve_strategy(self, strategy: str, domain: str) -> LLMConfig:
        """
        Resolves a provider strategy string to an LLMConfig.
        Strategies:
            - 'router:<mode>' -> use ModelRouter
            - 'fixed:<model>' -> use specific model with ollama
            - 'openai:<model>' -> use openai provider
        """
        if strategy.startswith("router:"):
            mode = strategy.split(":", 1)[1]
            return self.router.route(mode=mode, task_type=domain)
        
        if strategy.startswith("fixed:"):
            model = strategy.split(":", 1)[1]
            return LLMConfig(provider="ollama", model=model)
            
        if strategy.startswith("openai:"):
            model = strategy.split(":", 1)[1]
            return LLMConfig(provider="openai", model=model)

        # Default fallback
        return self.router.route(mode="general", task_type=domain)

    def _create_fallback_council(self, domain: str) -> MultiAICouncil:
        """Minimal fallback if configuration is missing."""
        cfg = self.router.route(mode="general", task_type=domain)
        m1 = LLMConfig(provider=cfg.provider, model=cfg.model, role="General Assistant")
        return MultiAICouncil(members=[m1])
