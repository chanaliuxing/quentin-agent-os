from __future__ import annotations

from typing import Dict, Any

from quentin.domain.base import DomainAdapter


class TradingAdapter(DomainAdapter):
    """
    Minimal Trading domain adapter (skeleton).

    Notes:
    - High-risk domain: by default, PolicyEngine disables self-programming here.
    - This adapter intentionally registers only safe helper tools.
    """

    name = "trading"

    def register_tools(self, tool_manager) -> None:
        from quentin.mutable.skills.common_text_tools import simple_summarizer

        tool_manager.register("TRADING_SUMMARIZE", lambda params: simple_summarizer(params))

    async def normalize_task(self, raw_task: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "task_id": raw_task.get("task_id", "trading-task"),
            "domain": "trading",
            "goal": raw_task["goal"],
            "meta": {k: v for k, v in raw_task.items() if k not in ("goal",)},
        }

