from __future__ import annotations

import json
import os
import urllib.request

import pytest

from quentin.execution.skill_executor import Executor
from quentin.llm.client import call_llm_with_tools


def _ollama_reachable(base_url: str) -> bool:
    base = (base_url or "http://localhost:11434").rstrip("/")
    # tolerate base_url that points at an endpoint (e.g. /api/generate)
    for suffix in ("/api/generate", "/api/chat", "/api/embeddings"):
        if base.endswith(suffix):
            base = base[: -len(suffix)].rstrip("/")
    try:
        with urllib.request.urlopen(f"{base}/api/tags", timeout=2) as r:
            _ = json.loads(r.read().decode("utf-8"))
        return True
    except Exception:
        return False


@pytest.mark.skipif(
    str(os.getenv("RUN_OLLAMA_SMOKE") or "").strip().lower() not in {"1", "true", "yes", "on"},
    reason="Set RUN_OLLAMA_SMOKE=1 to run (requires local Ollama).",
)
def test_ollama_chat_with_tools_smoke() -> None:
    base_url = os.getenv("LLM_BASE_URL", "http://localhost:11434")
    if not _ollama_reachable(base_url):
        pytest.skip("Ollama not reachable at LLM_BASE_URL")

    # Use real tool spec + real /api/chat tools mode via call_llm_with_tools.
    cfg = type(
        "Cfg",
        (),
        {
            "name": os.getenv("LLM_MODEL", "qwen3-vl:latest"),
            "provider": "ollama",
            "base_url": base_url,
        },
    )()

    out = call_llm_with_tools(
        cfg,
        system_prompt="You are a tool-using assistant. Return JSON when possible.",
        user_prompt="Reply with a tool call to read a file named README.md, if you can.",
        tools=Executor._build_native_tool_specs(),
        provider="ollama",
        model_name=getattr(cfg, "name", "qwen3-vl:latest"),
        timeout=60,
    )

    assert isinstance(out, dict)
    assert "content" in out
    assert "tool_calls" in out
    assert isinstance(out.get("tool_calls"), list)

