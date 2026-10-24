from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List


@dataclass(frozen=True)
class SchemaVersion:
    version: str
    payload_key: str
    status: str
    notes: str


SCHEMA_VERSIONS: List[SchemaVersion] = [
    SchemaVersion(version="v1", payload_key="__brain_event_v1", status="active", notes="Initial stable brain event envelope."),
    SchemaVersion(version="v2", payload_key="__brain_event_v2", status="active", notes="Adds idempotency_key and cursor metadata."),
]


def compatibility_matrix() -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for src in SCHEMA_VERSIONS:
        for dst in SCHEMA_VERSIONS:
            out.append(
                {
                    "from": src.version,
                    "to": dst.version,
                    "compatible": True if src.version == dst.version else True,
                    "migration": f"{src.version}_to_{dst.version}",
                }
            )
    return out


def parse_brain_event_envelope(payload: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    raw_v2 = payload.get("__brain_event_v2")
    if isinstance(raw_v2, dict):
        out = dict(raw_v2)
        if "idempotency_key" not in out:
            out["idempotency_key"] = str(out.get("event_id") or "")
        return out
    raw_v1 = payload.get("__brain_event_v1")
    if isinstance(raw_v1, dict):
        return migrate_v1_to_v2(raw_v1)
    return {}


def migrate_v1_to_v2(raw_v1: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(raw_v1 or {})
    out.setdefault("idempotency_key", str(out.get("event_id") or ""))
    return out
