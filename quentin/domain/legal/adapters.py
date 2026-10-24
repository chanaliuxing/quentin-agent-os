from __future__ import annotations

from typing import Dict, Any

from quentin.domain.base import DomainAdapter


class LegalAdapter(DomainAdapter):
    """
    Minimal Legal domain adapter (skeleton).

    Notes:
    - High-risk domain: self-programming is expected to be human-gated by default via PolicyEngine.
    - Tools registered here should remain low-risk helpers (formatting, summarization, citation extraction).
    """

    name = "legal"

    def register_tools(self, tool_manager) -> None:
        from quentin.mutable.skills.common_text_tools import simple_summarizer

        tool_manager.register("LEGAL_SUMMARIZE", lambda params: simple_summarizer(params))

    async def normalize_task(self, raw_task: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "task_id": raw_task.get("task_id", "legal-task"),
            "domain": "legal",
            "goal": raw_task["goal"],
            "meta": {k: v for k, v in raw_task.items() if k not in ("goal",)},
        }

