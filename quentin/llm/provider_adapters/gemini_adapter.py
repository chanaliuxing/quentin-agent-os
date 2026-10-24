from __future__ import annotations
from typing import Dict, Any, List
from .base import BaseSchemaAdapter
import copy

class GeminiSchemaAdapter(BaseSchemaAdapter):
    def transform_tools(self, tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        # Gemini specific tool transformation (e.g. remove anyOf)
        cleaned = []
        for t in tools:
            c = copy.deepcopy(t)
            # Example: Flatten complex types if needed (placeholder)
            cleaned.append(c)
        return cleaned

    def transform_messages(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        # Gemini expects 'parts' structure
        transformed = []
        for m in messages:
            role = "model" if m["role"] == "assistant" else m["role"]
            content = m.get("content", "")
            if isinstance(content, str):
                parts = [{"text": content}]
            else:
                parts = content # Assume already structured
            transformed.append({"role": role, "parts": parts})
        return transformed
