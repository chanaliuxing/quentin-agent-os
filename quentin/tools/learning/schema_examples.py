from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class SchemaExample:
    """
    A synthetic example derived from a tool's JSON schema.
    """

    input: Dict[str, Any]
    description: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {"input": dict(self.input or {}), "description": str(self.description or "")}


def _pick_enum(value: Any) -> Any:
    if isinstance(value, list) and value:
        return value[0]
    return None


def _example_for_schema(schema: Dict[str, Any], *, depth: int, max_depth: int) -> Any:
    if not isinstance(schema, dict):
        return None
    if depth >= max_depth:
        return None

    enum_v = _pick_enum(schema.get("enum"))
    if enum_v is not None:
        return enum_v

    typ = schema.get("type")
    if isinstance(typ, list):
        typ = typ[0] if typ else None
    typ = str(typ or "").strip().lower()

    if typ in {"string"}:
        fmt = str(schema.get("format") or "").strip().lower()
        if fmt == "date-time":
            return "2026-02-11T00:00:00Z"
        if fmt == "date":
            return "2026-02-11"
        if fmt == "email":
            return "user@example.com"
        if fmt == "uri" or fmt == "url":
            return "https://example.com"
        return "example"
    if typ in {"integer"}:
        return 1
    if typ in {"number"}:
        return 1.0
    if typ in {"boolean"}:
        return True
    if typ in {"array"}:
        items = schema.get("items") if isinstance(schema.get("items"), dict) else {}
        return [_example_for_schema(items, depth=depth + 1, max_depth=max_depth)]
    if typ in {"object"} or (not typ and isinstance(schema.get("properties"), dict)):
        props = schema.get("properties") if isinstance(schema.get("properties"), dict) else {}
        required = schema.get("required") if isinstance(schema.get("required"), list) else []
        out: Dict[str, Any] = {}
        # Prefer required keys first, then a small number of optional keys.
        keys: List[str] = []
        for k in required:
            ks = str(k or "").strip()
            if ks and ks in props and ks not in keys:
                keys.append(ks)
        for k in props.keys():
            if k not in keys:
                keys.append(str(k))
        # Cap optional expansion to keep examples small.
        keys = keys[: min(len(keys), 10)]
        for k in keys:
            sub = props.get(k)
            if isinstance(sub, dict):
                out[k] = _example_for_schema(sub, depth=depth + 1, max_depth=max_depth)
            else:
                out[k] = None
        return out

    # Fallback: attempt to infer from common JSON-schema keywords.
    if "properties" in schema and isinstance(schema.get("properties"), dict):
        return _example_for_schema({**schema, "type": "object"}, depth=depth, max_depth=max_depth)
    return None


def synthesize_examples_from_schema(
    *,
    input_schema: Dict[str, Any],
    tool_name: str = "",
    signature: str = "",
    max_examples: int = 3,
    max_depth: int = 4,
) -> List[Dict[str, Any]]:
    """
    v0 example synthesizer from JSON schema (deterministic, conservative).
    """
    n = max(0, min(10, int(max_examples or 0)))
    if n <= 0:
        return []
    if not isinstance(input_schema, dict) or not input_schema:
        return []

    base = _example_for_schema(input_schema, depth=0, max_depth=max_depth)
    if not isinstance(base, dict):
        return []

    desc_tool = str(tool_name or "").strip()
    desc_sig = str(signature or "").strip()
    desc = "Synthetic example derived from schema."
    if desc_tool and desc_sig:
        desc = f"Synthetic example for {desc_tool} ({desc_sig})."
    elif desc_tool:
        desc = f"Synthetic example for {desc_tool}."

    ex = SchemaExample(input=base, description=desc).to_dict()
    return [ex]

