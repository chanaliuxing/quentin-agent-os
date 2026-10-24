from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from quentin.llm.client import call_llm


def _messages_to_prompt(messages: List[Dict[str, Any]]) -> str:
    # Minimal conversion for legacy chat-style calls.
    # Prefer preserving roles to keep prompts stable across providers.
    lines: List[str] = []
    for m in messages or []:
        role = str(m.get("role") or "user")
        content = str(m.get("content") or "")
        lines.append(f"[{role}] {content}")
    return "\n".join(lines).strip()


@dataclass
class DefaultRouterBackend:
    """
    Adapter used by ModelRouter to perform a real provider call.

    Supports both legacy signatures used across the repo:
    - (model_id, prompt, **kwargs)
    - (model_id, messages, extra_meta_dict)
    - (provider=..., model_id=..., prompt=..., **kwargs)
    """

    safety_kernel: Any = None

    def __call__(self, *args: Any, **kwargs: Any) -> str:
        model_id: str = ""
        provider: Optional[str] = None
        prompt: str = ""
        extra_meta: Dict[str, Any] = {}

        if "model_id" in kwargs and "prompt" in kwargs:
            model_id = str(kwargs.get("model_id") or "")
            prompt = str(kwargs.get("prompt") or "")
            provider = str(kwargs.get("provider") or "") or None
            extra_meta = dict(kwargs)
        elif len(args) >= 2 and isinstance(args[1], str):
            model_id = str(args[0] or "")
            prompt = str(args[1] or "")
            provider = str(kwargs.get("provider") or "") or None
            extra_meta = dict(kwargs)
        elif len(args) >= 3 and isinstance(args[1], list) and isinstance(args[2], dict):
            model_id = str(args[0] or "")
            prompt = _messages_to_prompt(args[1])
            meta = dict(args[2])
            provider = str(meta.get("provider") or "") or None
            extra_meta = {**meta, **dict(kwargs)}
        else:
            raise TypeError("Unsupported backend_call signature")

        domain = str(extra_meta.get("domain") or extra_meta.get("task_domain") or "core")
        environment = str(extra_meta.get("environment") or "sandbox")
        risk_level = str(extra_meta.get("risk_level") or "medium")

        return call_llm(
            model_id,
            user_prompt=prompt,
            system_prompt="",
            provider=provider,
            model_name=model_id,
            safety_kernel=self.safety_kernel,
            actor=str(extra_meta.get("actor") or "model_router_backend"),
            domain=domain,
            environment=environment,
            risk_level=risk_level,
            action_metadata={k: v for k, v in extra_meta.items() if k not in ("prompt",)},
        )

