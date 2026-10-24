# meta_agent/runtime/__init__.py

from __future__ import annotations

from meta_agent.runtime.council_runtime import CouncilRuntime, CouncilTask, CouncilResult

# 全局单例，也可以在你的 DI 容器里管理
council = CouncilRuntime()

__all__ = [
    "council",
    "CouncilRuntime",
    "CouncilTask",
    "CouncilResult",
]