from __future__ import annotations

from quentin.traces.core import TraceEvent


def test_trace_event_to_dict_cycle_safe() -> None:
    payload: dict = {"a": 1}
    payload["self"] = payload
    ev = TraceEvent(event_id="e1", trace_id="t1", event_type="execution", payload=payload)
    out = ev.to_dict()
    assert isinstance(out, dict)
    assert out["payload"]["a"] == 1
    assert out["payload"]["self"]["type"] == "cycle"


def test_trace_event_to_dict_does_not_deepcopy_payload_objects() -> None:
    class BadDeepcopy:
        def __deepcopy__(self, memo):  # noqa: ANN001
            raise RuntimeError("no deepcopy allowed")

    ev = TraceEvent(
        event_id="e2",
        trace_id="t2",
        event_type="execution",
        payload={"obj": BadDeepcopy()},
    )
    out = ev.to_dict()
    assert out["event_id"] == "e2"
    assert out["trace_id"] == "t2"
    assert out["payload"]["obj"]["type"] == "BadDeepcopy"
