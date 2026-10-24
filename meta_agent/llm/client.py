from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Optional

from meta_agent.llm.cli_clients import CLIModelClient, make_codex_cli_client


@dataclass
class LLMRequest:
    model: str
    prompt: str
    max_tokens: int = 2048
    temperature: float = 0.2
    json_mode: bool = False


class LLMClient:
    """
    Minimal LLM client interface used by meta-agent components.

    Use `CliLLMClient` for an offline-friendly default implementation.
    """

    def generate(self, req: LLMRequest) -> str:  # pragma: no cover - interface
        raise RuntimeError("LLMClient is an interface; use CliLLMClient or a provider-backed client.")


class CliLLMClient(LLMClient):
    """
    CLI-backed LLM client (default).

    This delegates to `meta_agent.llm.cli_clients` and keeps the repo runnable without
    hardcoding any external provider credentials.
    """

    def __init__(self, client: Optional[CLIModelClient] = None) -> None:
        self._client = client or make_codex_cli_client()

    def generate(self, req: LLMRequest) -> str:
        system = ""
        user = str(req.prompt)
        # `CLIModelClient.generate` expects system/user fields.
        out = self._client.generate(system=system, user=user)
        return str(out)
