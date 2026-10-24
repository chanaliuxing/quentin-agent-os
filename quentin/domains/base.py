from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Protocol

from quentin.infra.logging import Tracer
from quentin.tools.manager import ToolManager
from quentin.tools.schemas import ToolSpec, ToolCallRequest, ToolCallResult


@dataclass
class DomainTask:
    """
    领域任务抽象：
    - domain: 领域名称，例如 "generic" / "desktop" / "legal" / "trading"
    - goal: 任务目标（自然语言）
    - input: 任意 payload，由具体 DomainAdapter 自己解释
    """
    domain: str
    goal: str
    input: Dict[str, Any] = field(default_factory=dict)
    meta: Dict[str, Any] = field(default_factory=dict)


class DomainAdapter(Protocol):
    """
    DomainAdapter 协议：
    - name: 领域名称
    - description: 给 Planner / UI 看的介绍
    - register_tools: 在 ToolManager 中注册自己的工具
    - handle_task: 执行一个高层任务（可以用到多个工具）
    """

    name: str
    description: str

    async def register_tools(self, tool_manager: ToolManager) -> None:
        ...

    async def handle_task(
        self,
        task: DomainTask,
        tool_manager: ToolManager,
    ) -> Dict[str, Any]:
        """
        返回一个结果 dict（可以带 log / steps / output 等）
        """
        ...


@dataclass
class DomainRegistry:
    """
    用于管理多个 DomainAdapter：
    - 注册 / 查询 domain
    - 提供 route_task：把 DomainTask 路由到对应 adapter
    """
    tracer: Tracer
    tool_manager: ToolManager
    domains: Dict[str, DomainAdapter] = field(default_factory=dict)

    async def register_domain(self, adapter: DomainAdapter) -> None:
        if adapter.name in self.domains:
            raise ValueError(f"Domain '{adapter.name}' already registered.")

        self.domains[adapter.name] = adapter
        await adapter.register_tools(self.tool_manager)

        self.tracer.span(
            "L1",
            "domain_register",
            module="domain_registry",
            input={"domain": adapter.name},
        )

    def list_domains(self) -> List[Dict[str, Any]]:
        return [
            {
                "name": a.name,
                "description": getattr(a, "description", ""),
            }
            for a in self.domains.values()
        ]

    def get(self, name: str) -> Optional[DomainAdapter]:
        return self.domains.get(name)

    async def route_task(self, task: DomainTask) -> Dict[str, Any]:
        adapter = self.domains.get(task.domain)
        if not adapter:
            raise ValueError(f"Unknown domain '{task.domain}'")
        self.tracer.span(
            "L1",
            "domain_task_route",
            module="domain_registry",
            input={"domain": task.domain, "goal": task.goal},
        )
        return await adapter.handle_task(task, self.tool_manager)