# meta_agent/self_programming/mcp_integration/schema_utils.py
from __future__ import annotations
from typing import Any, Dict, List


def synthesize_examples_from_schema(schema: Dict[str, Any], max_examples: int = 2) -> List[Dict[str, Any]]:
    """
    Convert a JSON schema-like dict into simple example inputs.
    Currently supports primitive properties; can be extended for enums/arrays.
    """
    if not schema or not isinstance(schema, dict):
        return []

    props = schema.get("properties", {}) if isinstance(schema.get("properties"), dict) else {}
    example_input: Dict[str, Any] = {}
    for name, cfg in props.items():
        if cfg.get("enum"):
            example_input[name] = cfg["enum"][0]
            continue
        typ = cfg.get("type")
        if typ == "string":
            example_input[name] = f"example_{name}"
        elif typ == "number":
            example_input[name] = 1
        elif typ == "integer":
            example_input[name] = 1
        elif typ == "boolean":
            example_input[name] = True
        elif typ == "array":
            example_input[name] = [cfg.get("items", {}).get("example", "item")]
        elif typ == "object":
            example_input[name] = cfg.get("example", {})

    if not example_input:
        return []

    return [{"input": example_input, "usage_note": "auto-generated from schema"}][:max_examples]
