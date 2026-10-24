from __future__ import annotations

from typing import Any, Dict, List, Optional
import json
import logging
import os
import re

from quentin.llm.tool_call_protocols.base import ToolCallProtocol, ProtocolDecision
from quentin.llm.client import call_llm_with_tools

logger = logging.getLogger(__name__)


def _robust_json_parse_fragment(text: str) -> Optional[Dict[str, Any]]:
    s = str(text or "").strip()
    if not s:
        return None
    if s.startswith("```"):
        s = re.sub(r"^```(?:json)?", "", s, flags=re.IGNORECASE).strip()
        s = re.sub(r"```$", "", s).strip()
    start = s.find("{")
    end = s.rfind("}")
    if start != -1 and end != -1 and end > start:
        s = s[start : end + 1]
    s = re.sub(r",\s*([\]\}])", r"\1", s)
    try:
        data = json.loads(s)
    except Exception:
        return None
    return data if isinstance(data, dict) else None

class NativeToolsProtocol(ToolCallProtocol):
    """
    Protocol that uses native provider tool-calling (e.g. Ollama /api/chat).
    """
    @property
    def id(self) -> str:
        return "native_tools"

    @property
    def priority(self) -> int:
        return 100

    def supports(self, provider: str, model_name: str, config: Any) -> bool:
        # Default to supporting if provider is Ollama and not explicitly disabled.
        # This can be refined based on model capabilities if needed.
        if provider != "ollama":
            return False
            
        disabled = os.getenv("QUENTIN_EXECUTOR_NATIVE_TOOL_CALLING", "1").lower() in ("0", "false", "no", "off")
        if disabled:
            return False
            
        # Optional: check if model name suggests no tools support
        lowered = model_name.lower()
        if "vl" in lowered or "vision" in lowered:
            # Usually vision models in Ollama don't support tools yet
            return False
            
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
            native_out = call_llm_with_tools(
                config,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                tools=tools,
                actor="executor_native_tools",
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
            
            content = str(native_out.get("content") or "").strip()
            tool_calls = native_out.get("tool_calls") or []
            
            normalized_tool_calls = []
            for raw_call in tool_calls:
                tc = self._normalize_native_tool_call(raw_call)
                if tc:
                    normalized_tool_calls.append(tc)
                    
            return ProtocolDecision(
                kind="tool_call" if normalized_tool_calls else "final",
                tool_calls=normalized_tool_calls,
                content=content,
                meta={"raw": native_out, "protocol": self.id}
            )
            
        except Exception as e:
            logger.warning(f"NativeToolsProtocol failed: {e}")
            return ProtocolDecision(
                kind="error",
                error=str(e),
                meta={"protocol": self.id}
            )

    def _normalize_native_tool_call(self, raw_call: Any) -> Optional[Dict[str, Any]]:
        if not isinstance(raw_call, dict):
            return None
        function = raw_call.get("function") if isinstance(raw_call.get("function"), dict) else {}
        name = str(function.get("name") or raw_call.get("name") or "").strip()
        if not name:
            return None
        arguments = function.get("arguments", raw_call.get("arguments"))
        if isinstance(arguments, str):
            try:
                arguments = json.loads(arguments)
            except Exception:
                parsed = _robust_json_parse_fragment(arguments)
                arguments = parsed if isinstance(parsed, dict) else {}
        if not isinstance(arguments, dict):
            arguments = {}
        return {"tool_name": name, "args": arguments}
