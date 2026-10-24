from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Any

from quentin.tools.manager import ToolManager
from quentin.domains.base import DomainAdapter, DomainTask
from mutable.skills import example_skill

@dataclass
class DemoDomainAdapter(DomainAdapter):
    name: str = "demo"
    description: str = "Demo domain for testing self-correction workflow."

    async def register_tools(self, tool_manager: ToolManager) -> None:
        pass

    async def handle_task(
        self,
        task: DomainTask,
        tool_manager: ToolManager,
    ) -> Dict[str, Any]:
        if task.goal.startswith("add "):
            # Parse goal "add a + b" or check input
            # Assume input has "a" and "b"
            a = task.input.get("a", 0)
            b = task.input.get("b", 0)
            result = example_skill.add_numbers(a, b)
            return {"result": result}
        return {"error": "unknown goal"}
