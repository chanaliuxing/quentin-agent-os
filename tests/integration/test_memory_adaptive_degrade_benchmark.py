from __future__ import annotations

import time

from quentin.memory.models import MemoryQuery
from quentin.memory.search_manager import ParallelSearchManager, SearchManagerConfig, SessionSearchSpec


class _SlowEmptyFabric:
    def recall(self, query, **kwargs):  # noqa: ANN001, ANN003
        _ = (query, kwargs)
        time.sleep(0.03)
        return []


def test_adaptive_degrade_under_high_fanout() -> None:
    mgr = ParallelSearchManager(
        config=SearchManagerConfig(
            max_workers=8,
            per_session_timeout_s=0.01,
            adaptive_degrade_enabled=True,
            adaptive_session_cap_factor=2,
            timeout_pressure_threshold=0.0,
            rerank_enabled=True,
        )
    )
    specs = [SessionSearchSpec(session_id=f"s{i}", source_prefixes=[]) for i in range(120)]
    result = mgr.search_across_sessions(
        memory_fabric=_SlowEmptyFabric(),
        base_query=MemoryQuery(text="load", top_k=20, mode="text_only"),
        session_specs=specs,
        top_k=20,
    )
    # 8 workers * cap_factor 2 => at most 16 sessions scanned under adaptive cap.
    assert int(result["total_sessions"]) <= 16
    assert bool(result["budget"]["adaptive_degrade_applied"]) is True
    assert bool(result["budget"]["timeout_pressure"]) is True
    assert result["rerank_applied"] is False
