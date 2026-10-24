from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

@dataclass
class ModelEntry:
    id: str
    provider: str
    name: str
    context_window: int
    supports_vision: bool = False
    supports_tools: bool = True
    input_cost_per_1m: float = 0.0
    output_cost_per_1m: float = 0.0
    tags: List[str] = field(default_factory=list)

class ModelCatalog:
    """
    Centralized knowledge base of model capabilities.
    Aligned with OpenClaw's model-catalog.
    """
    def __init__(self):
        self._models: Dict[str, ModelEntry] = {}
        self._load_defaults()

    def _load_defaults(self):
        # Sample Catalog (In real world, this could be loaded from JSON)
        defaults = [
            ModelEntry("gpt-4o", "openai", "GPT-4o", 128000, True, True, 5.0, 15.0, ["fast", "premium"]),
            ModelEntry("claude-3-5-sonnet", "anthropic", "Claude 3.5 Sonnet", 200000, True, True, 3.0, 15.0, ["premium"]),
            ModelEntry("gemini-1.5-pro", "google", "Gemini 1.5 Pro", 1000000, True, True, 3.5, 10.5, ["vision"]),
            ModelEntry("deepseek-v3", "deepseek", "DeepSeek V3", 64000, False, True, 0.1, 0.3, ["cheap", "fast"]),
        ]
        for m in defaults:
            self._models[m.id] = m

    def get_model(self, model_id: str) -> Optional[ModelEntry]:
        return self._models.get(model_id)

    def find_capable_models(self, min_context: int = 0, vision: bool = False) -> List[ModelEntry]:
        results = []
        for m in self._models.values():
            if m.context_window >= min_context and (not vision or m.supports_vision):
                results.append(m)
        return results

# Global instance
model_catalog = ModelCatalog()
