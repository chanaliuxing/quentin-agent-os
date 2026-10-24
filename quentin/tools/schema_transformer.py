from __future__ import annotations

from typing import Any, Dict


_GEMINI_UNSUPPORTED_KEYS = {
    "$schema",
    "$id",
    "unevaluatedProperties",
    "dependentSchemas",
    "patternProperties",
    "propertyNames",
    "contains",
    "prefixItems",
    "contentEncoding",
    "contentMediaType",
}


def _clean_schema_for_gemini(schema: Any) -> Any:
    if not isinstance(schema, dict):
        return schema
    cleaned: Dict[str, Any] = {}
    for k, v in schema.items():
        if k in _GEMINI_UNSUPPORTED_KEYS:
            continue
        if isinstance(v, dict):
            cleaned[k] = _clean_schema_for_gemini(v)
        elif isinstance(v, list):
            cleaned[k] = [_clean_schema_for_gemini(i) for i in v]
        else:
            cleaned[k] = v
    return cleaned


def _extract_enum_values(schema: Any) -> Optional[List[Any]]:
    if not isinstance(schema, dict):
        return None
    if "enum" in schema and isinstance(schema["enum"], list):
        return list(schema["enum"])
    if "const" in schema:
        return [schema["const"]]
    variants = schema.get("anyOf") or schema.get("oneOf")
    if isinstance(variants, list):
        values = []
        for v in variants:
            extracted = _extract_enum_values(v)
            if extracted:
                values.extend(extracted)
        return values if values else None
    return None


def _merge_property_schemas(existing: Any, incoming: Any) -> Any:
    if not existing:
        return incoming
    if not incoming:
        return existing

    existing_enum = _extract_enum_values(existing)
    incoming_enum = _extract_enum_values(incoming)
    if existing_enum or incoming_enum:
        values = list(dict.fromkeys((existing_enum or []) + (incoming_enum or [])))
        merged: Dict[str, Any] = {}
        for source in [existing, incoming]:
            if not isinstance(source, dict):
                continue
            for key in ["title", "description", "default"]:
                if key not in merged and key in source:
                    merged[key] = source[key]
        types = {type(v) for v in values}
        if len(types) == 1:
            t = list(types)[0]
            if t == str:
                merged["type"] = "string"
            elif t == int:
                merged["type"] = "integer"
            elif t == float:
                merged["type"] = "number"
            elif t == bool:
                merged["type"] = "boolean"
        merged["enum"] = values
        return merged

    return existing


def normalize_tool_schema(schema: Dict[str, Any]) -> Dict[str, Any]:
    if not schema:
        return {}
    schema = _clean_schema_for_gemini(schema)
    
    # If it's already a direct object schema, return it
    if schema.get("type") == "object" and "anyOf" not in schema and "oneOf" not in schema:
        return schema
        
    # Handle cases where type is missing but properties/required are present
    if "properties" in schema or "required" in schema:
        if "anyOf" not in schema and "oneOf" not in schema:
            return {**schema, "type": "object"}

    variant_key = "anyOf" if "anyOf" in schema else ("oneOf" if "oneOf" in schema else None)
    if not variant_key:
        if "type" not in schema and ("properties" in schema or "required" in schema):
             return {**schema, "type": "object"}
        return schema

    variants = schema.get(variant_key) or []
    merged_props: Dict[str, Any] = {}
    required_counts: Dict[str, int] = {}
    obj_variants = 0
    
    for v in variants:
        if not isinstance(v, dict):
            continue
        props = v.get("properties")
        if not isinstance(props, dict):
            continue
        obj_variants += 1
        for k, val in props.items():
            if k not in merged_props:
                merged_props[k] = val
            else:
                merged_props[k] = _merge_property_schemas(merged_props[k], val)
        
        required = v.get("required") or []
        for key in required:
            required_counts[key] = required_counts.get(key, 0) + 1
            
    base_required = schema.get("required")
    if isinstance(base_required, list):
        merged_required = [str(k) for k in base_required if isinstance(k, (str, int))]
    elif obj_variants > 0:
        merged_required = [k for k, cnt in required_counts.items() if cnt == obj_variants]
    else:
        merged_required = []

    out: Dict[str, Any] = {
        "type": "object",
        "properties": merged_props if merged_props else (schema.get("properties") or {}),
    }
    if merged_required:
        out["required"] = merged_required
    if "additionalProperties" in schema:
        out["additionalProperties"] = schema["additionalProperties"]
    if "title" in schema:
        out["title"] = schema["title"]
    if "description" in schema:
        out["description"] = schema["description"]
        
    return out


def normalize_tool_params(params: Any) -> Dict[str, Any]:
    """
    Normalize tool parameters from Claude Code conventions to Project Taylor conventions.
    
    Claude Code uses: file_path, old_string, new_string
    Taylor uses: path, oldText, newText
    """
    if not isinstance(params, dict):
        return params if isinstance(params, dict) else {}
        
    normalized = dict(params)
    
    # file_path -> path
    if "file_path" in normalized and "path" not in normalized:
        normalized["path"] = normalized.pop("file_path")
        
    # old_string -> oldText
    if "old_string" in normalized and "oldText" not in normalized:
        normalized["oldText"] = normalized.pop("old_string")
        
    # new_string -> newText
    if "new_string" in normalized and "newText" not in normalized:
        normalized["newText"] = normalized.pop("new_string")
        
    return normalized


def patch_tool_schema_for_claude_compatibility(schema: Dict[str, Any]) -> Dict[str, Any]:
    """
    P5: Ported from OpenClaw.
    Injects aliases into properties so Claude-style models see them in the schema.
    """
    if not isinstance(schema, dict) or "properties" not in schema:
        return schema
        
    properties = dict(schema["properties"])
    required = list(schema.get("required") or [])
    changed = False
    
    alias_pairs = [
        ("path", "file_path"),
        ("oldText", "old_string"),
        ("newText", "new_string")
    ]
    
    for original, alias in alias_pairs:
        if original in properties:
            if alias not in properties:
                properties[alias] = properties[original]
                changed = True
            if original in required:
                # If we have an alias, making it NOT required at the schema level
                # helps the model understand it can pick either.
                # (Actual validation happens in normalize_tool_params)
                required = [r for r in required if r != original]
                changed = True
                
    if not changed:
        return schema
        
    new_schema = dict(schema)
    new_schema["properties"] = properties
    if required:
        new_schema["required"] = required
    elif "required" in new_schema:
        new_schema.pop("required")
        
    return new_schema


def transform_for_provider(schema: Dict[str, Any], provider: str) -> Dict[str, Any]:
    """
    P5: Ported from OpenClaw's provider-specific schema transformation.
    Applies 'Last-mile' fixes for specific model vendors.
    """
    if not schema:
        return {}
        
    p = str(provider or "").lower()
    from quentin.tools.transformer_engine import SchemaTransformerEngine
    
    # 1. Base Normalization
    normalized = normalize_tool_schema(schema)
    
    # 2. Gemini / Google Fixes (Flattening)
    if p in ("gemini", "google"):
        return SchemaTransformerEngine.flatten_schema(normalized)
        
    # 3. Local Model Fixes (Pruning)
    if p == "ollama":
        return SchemaTransformerEngine.prune_for_local(normalized)
        
    # 4. OpenAI Fixes
    if p == "openai":
        if "type" not in normalized:
            return {**normalized, "type": "object"}
            
    return normalized
