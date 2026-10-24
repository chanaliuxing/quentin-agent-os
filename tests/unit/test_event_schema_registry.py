from __future__ import annotations

from quentin.runtime.event_schema_registry import compatibility_matrix, migrate_v1_to_v2, parse_brain_event_envelope


def test_schema_registry_compatibility_matrix_present() -> None:
    rows = compatibility_matrix()
    assert rows
    assert any(r.get("from") == "v1" and r.get("to") == "v2" for r in rows)


def test_migrate_v1_to_v2_adds_idempotency_key() -> None:
    v1 = {"event_id": "e-1", "session_id": "s1"}
    v2 = migrate_v1_to_v2(v1)
    assert v2["event_id"] == "e-1"
    assert v2["idempotency_key"] == "e-1"


def test_parse_brain_event_envelope_reads_v2_then_v1() -> None:
    p2 = {"__brain_event_v2": {"event_id": "e-2", "idempotency_key": "k-2"}}
    o2 = parse_brain_event_envelope(p2)
    assert o2["event_id"] == "e-2"
    assert o2["idempotency_key"] == "k-2"

    p1 = {"__brain_event_v1": {"event_id": "e-1"}}
    o1 = parse_brain_event_envelope(p1)
    assert o1["event_id"] == "e-1"
    assert o1["idempotency_key"] == "e-1"
