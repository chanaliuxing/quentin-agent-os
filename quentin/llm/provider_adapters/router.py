from __future__ import annotations
from typing import Dict
from .base import BaseSchemaAdapter
from .gemini_adapter import GeminiSchemaAdapter

class SchemaAdapterRouter:
    def __init__(self):
        self._adapters: Dict[str, BaseSchemaAdapter] = {
            "gemini": GeminiSchemaAdapter(),
            "google": GeminiSchemaAdapter(),
        }
        
    def get_adapter(self, provider: str) -> BaseSchemaAdapter:
        return self._adapters.get(provider.lower())

# Global instance
adapter_router = SchemaAdapterRouter()
