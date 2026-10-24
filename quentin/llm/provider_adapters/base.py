from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Dict, Any, List

class BaseSchemaAdapter(ABC):
    @abstractmethod
    def transform_tools(self, tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        return tools

    @abstractmethod
    def transform_messages(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        return messages
