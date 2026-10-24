from __future__ import annotations

import os
from types import SimpleNamespace

import pytest

from quentin.llm.client import call_llm_with_tools


@pytest.mark.skipif(
    str(os.getenv("RUN_OLLAMA_SMOKE") or "").strip().lower() not in {"1", "true", "yes", "on"},
    reason="Set RUN_OLLAMA_SMOKE=1 to run (requires local Ollama).",
)
def test_ollama_tools_fallback_from_unsupported_model() -> None:
    """
    Ollama returns HTTP 400 for models that do not support tools (e.g. qwen2.5vl).
    Ensure we recover by retrying with a text tools-capable model.
    """
    # Force first attempt to use a known unsupported tools model.
    os.environ["LLM_TOOL_MODEL"] = "qwen2.5vl:latest"
    os.environ["LLM_TEXT_MODEL"] = "qwen3-vl:latest"

    cfg = SimpleNamespace(name="qwen2.5vl:latest", provider="ollama", base_url="http://localhost:11434")
    out = call_llm_with_tools(
        cfg,
        system_prompt="You are a tool-using assistant.",
        user_prompt="Call fs.read_file with path=README.md",
        tools=[
            {
                "type": "function",
                "function": {
                    "name": "fs.read_file",
                    "description": "Read a file.",
                    "parameters": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]},
                },
            }
        ],
        provider="ollama",
        model_name="qwen2.5vl:latest",
        timeout=60.0,
    )
    assert isinstance(out, dict)
    assert "raw" in out
    assert "message" in out

