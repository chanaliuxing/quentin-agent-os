from __future__ import annotations
import logging
from typing import Any, Dict, List
from quentin.llm.provider_adapters.router import adapter_router

logger = logging.getLogger(__name__)

class ToolSchemaAdapter:
    """
    Transforms standard JSON Schema tools to provider-specific 'dialects'.
    Now delegates to P1-D modular adapters.
    """
    
    @staticmethod
    def to_gemini(tool_def: Dict[str, Any]) -> Dict[str, Any]:
        adapter = adapter_router.get_adapter("gemini")
        if adapter:
            return adapter.transform_tools([tool_def])[0]
        return tool_def

    @staticmethod
    def to_anthropic(tool_def: Dict[str, Any]) -> Dict[str, Any]:
        # Legacy fallback or future migration
        return {
            "name": tool_def["name"],
            "description": tool_def.get("description", ""),
            "input_schema": tool_def.get("parameters", {
                "type": "object",
                "properties": {}
            })
        }

    @classmethod
    def transform(cls, tool_defs: List[Dict[str, Any]], provider: str) -> List[Dict[str, Any]]:
        adapter = adapter_router.get_adapter(provider)
        if adapter:
            return adapter.transform_tools(tool_defs)
        
        # Fallback for non-adapted providers (like Anthropic if not in router yet)
        if provider.lower() in ("anthropic", "claude"):
            return [cls.to_anthropic(t) for t in tool_defs]
            
        return tool_defs

# Global instance
schema_adapter = ToolSchemaAdapter()
