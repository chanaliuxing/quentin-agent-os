from __future__ import annotations

import logging
from typing import Dict, Type, Optional
from .base import ModelClient

logger = logging.getLogger(__name__)

class ModelAdapterRegistry:
    """
    Registry for model provider adapters.
    Allows dynamic registration of new providers without modifying core logic.
    """
    _adapters: Dict[str, Type[ModelClient]] = {}

    @classmethod
    def register(cls, provider: str, adapter_class: Type[ModelClient]):
        provider = provider.lower()
        if provider in cls._adapters:
            logger.warning("Overwriting adapter for provider: %s", provider)
        cls._adapters[provider] = adapter_class
        logger.info("Registered adapter for provider: %s", provider)

    @classmethod
    def get_adapter(cls, provider: str) -> Optional[Type[ModelClient]]:
        return cls._adapters.get(provider.lower())

    @classmethod
    def list_providers(self) -> list[str]:
        return list(self._adapters.keys())

# Global registry instance
registry = ModelAdapterRegistry
