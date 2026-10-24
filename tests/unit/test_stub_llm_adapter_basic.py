from __future__ import annotations

import asyncio
import json

from quentin.infra.llm.factory import ModelClientFactory
from quentin.infra.llm.stub_client import StubClient


def test_stub_client_generate_returns_json_text() -> None:
    client = ModelClientFactory.create_client(model_id="stub-model", provider="stub")
    resp = asyncio.run(
        client.generate(
            [
                {"role": "system", "content": "Council: done. Topic: done_check. Return JSON."},
                {
                    "role": "user",
                    "content": json.dumps(
                        {"prompt": "done?", "payload": {"execution_summary": {"final_output": "BENCH_DONE: x"}}},
                        ensure_ascii=False,
                    ),
                },
            ]
        )
    )
    obj = json.loads(resp.text)
    assert isinstance(obj, dict)
    assert obj.get("is_done") is True


def test_force_stub_overrides_non_stub_provider(monkeypatch) -> None:
    monkeypatch.setenv("QUENTIN_LLM_FORCE_STUB", "1")
    client = ModelClientFactory.create_client(model_id="qwen3.5:4b", provider="ollama")
    assert isinstance(client, StubClient)
