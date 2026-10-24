from __future__ import annotations

from datetime import datetime, UTC

from quentin.traces.episode_builder import TraceEpisodeBuilder
from quentin.traces.schemas import TraceSpan


def test_trace_episode_builder_groups_by_task_id():
    b = TraceEpisodeBuilder()

    t0 = datetime.now(UTC)
    spans = [
        TraceSpan(span_id="s1", ts=t0, layer="L1", module="m", event="e1", input={"task_id": "t1"}, output={}, meta={}),
        TraceSpan(span_id="s2", ts=t0, layer="L1", module="m", event="e2", input={"task_id": "t1"}, output={}, meta={}),
        TraceSpan(span_id="s3", ts=t0, layer="L1", module="m", event="e3", input={"task_id": "t2"}, output={}, meta={}),
    ]

    eps = b.build_episodes_from_spans(spans)
    ep_ids = sorted([e.episode_id for e in eps])
    assert ep_ids == ["t1", "t2"]

