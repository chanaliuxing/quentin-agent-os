from __future__ import annotations

import asyncio

from quentin.memory.models import MemoryRecord, MemoryTier
from quentin.memory.processors.summarizer import Summarizer


def test_summarizer_uses_stub_when_force_stub_enabled(monkeypatch) -> None:
    monkeypatch.setenv("QUENTIN_LLM_FORCE_STUB", "1")
    s = Summarizer()
    assert s.client.__class__.__name__ == "StubClient"

    rec = MemoryRecord.new(
        tier=MemoryTier.STS,
        content="Observed repeated timeout while calling tool X; fallback to safe mode.",
        source="unit_test",
    )
    insight = asyncio.run(s.distill([rec]))
    assert insight is not None
