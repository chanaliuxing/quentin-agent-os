# meta_agent/tools/coder/router.py
from __future__ import annotations
from typing import Dict, List, Optional

from meta_agent.tools.coder.base import (
    CoderBackend,
    CodeGenerationRequest,
    CodeGenerationResult,
)
import os

from meta_agent.tools.coder.codex_cli_backend import CodexCliBackend
from meta_agent.tools.coder.gemini_cli_backend import GeminiCliBackend
from meta_agent.tools.coder.claude_code_cli_backend import ClaudeCodeCliBackend
from meta_agent.tools.coder.stub_backend import StubCoderBackend
from meta_agent.tools.coder.ollama_backend import OllamaCoderBackend
from meta_agent.tools.coder.deterministic_backend import DeterministicCoderBackend
from meta_agent.tools.coder.llm_client_backend import LLMClientCoderBackend


class CoderRouter:
    # Order matters: prefer Gemini CLI, then Codex CLI, then Claude Code CLI.
    CLI_PRIORITY = ("gemini_cli", "codex_cli", "claude_code_cli")

    def __init__(self, backends: Optional[Dict[str, CoderBackend]] = None):
        self.backends: Dict[str, CoderBackend] = backends or {
            "gemini_cli": GeminiCliBackend(),
            "codex_cli": CodexCliBackend(),
            "claude_code_cli": ClaudeCodeCliBackend(),
            "stub": StubCoderBackend(),
            "ollama": OllamaCoderBackend(),
            "deterministic": DeterministicCoderBackend(),
            "llm_client": LLMClientCoderBackend(),
        }
        env_backend = (os.environ.get("CODER_BACKEND") or "gemini_cli").strip().lower()
        if env_backend == "auto":
            env_backend = "gemini_cli"
        if env_backend and env_backend in self.backends:
            self.default_backend = env_backend
        else:
            self.default_backend = "gemini_cli"

    def _candidate_backends(self, requested_backend: Optional[str]) -> List[str]:
        name = (requested_backend or self.default_backend).strip().lower()
        if name == "auto":
            name = "auto_cli"
        candidates: List[str] = []
        if name == "auto_cli":
            candidates.extend(self.CLI_PRIORITY)
        else:
            candidates.append(name)
            if name in self.CLI_PRIORITY:
                candidates.extend([n for n in self.CLI_PRIORITY if n != name])
        if "stub" not in candidates:
            candidates.append("stub")
        return candidates

    def generate(
        self,
        req: CodeGenerationRequest,
        backend_name: Optional[str] = None,
    ) -> CodeGenerationResult:
        failures: List[str] = []
        for name in self._candidate_backends(backend_name):
            backend = self.backends.get(name)
            if not backend:
                failures.append(f"{name}: backend not registered")
                continue
            if not getattr(backend, "available", True) and name != "stub":
                failures.append(f"{name}: unavailable")
                continue
            result = backend.generate(req)
            if result.success:
                if failures:
                    trail = " -> ".join(failures)
                    reason = (result.reasoning or "").strip()
                    result.reasoning = f"{reason}; fallback_chain={trail}" if reason else f"fallback_chain={trail}"
                return result
            failures.append(f"{name}: {result.reasoning or 'failed'}")

        fallback = self.backends.get("stub")
        if fallback:
            result = fallback.generate(req)
            trail = " -> ".join(failures)
            reason = (result.reasoning or "").strip()
            result.reasoning = f"{reason}; fallback_chain={trail}" if reason else f"fallback_chain={trail}"
            return result
        return CodeGenerationResult(
            success=False,
            code="",
            reasoning="no coder backend succeeded",
        )


coder_router = CoderRouter()
