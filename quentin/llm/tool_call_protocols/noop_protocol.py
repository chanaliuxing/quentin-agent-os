from __future__ import annotations

from typing import Any, Dict, List, Optional
import logging

from quentin.llm.tool_call_protocols.base import ToolCallProtocol, ProtocolDecision
from quentin.llm.client import call_llm

logger = logging.getLogger(__name__)

class NoopProtocol(ToolCallProtocol):
    """
    Protocol that just returns the LLM text output as a final answer.
    """
    @property
    def id(self) -> str:
        return "noop"

    @property
    def priority(self) -> int:
        return 0

    def supports(self, provider: str, model_name: str, config: Any) -> bool:
        return True

    async def next_action(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        tools: List[Dict[str, Any]],
        config: Any,
        context: Dict[str, Any],
    ) -> ProtocolDecision:
        from quentin.infra.concurrency.cancellation import CancellationToken
        cancel_token = context.get("cancel_token")

        try:
            out_raw = call_llm(
                config,
                user_prompt=user_prompt,
                system_prompt=system_prompt,
                actor="executor_noop",
                domain=str(context.get("domain", "core")),
                environment=str(context.get("environment", "sandbox")),
                risk_level=str(context.get("risk_level", "medium")),
                action_metadata={
                    "component": "executor",
                    "step_id": context.get("current_step_id"),
                    "iteration": context.get("iteration"),
                    "protocol": self.id,
                },
                provider=getattr(config, "provider", None),
                model_name=getattr(config, "name", None),
                cancel_token=cancel_token if isinstance(cancel_token, CancellationToken) else None,
            )
            
            return ProtocolDecision(
                kind="final",
                content=out_raw,
                meta={"protocol": self.id}
            )

        except Exception as e:
            return ProtocolDecision(
                kind="error",
                error=str(e),
                meta={"protocol": self.id}
            )
