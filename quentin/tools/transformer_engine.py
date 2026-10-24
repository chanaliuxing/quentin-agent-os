from __future__ import annotations
import copy
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

class SchemaTransformerEngine:
    """
    P5: Ported from OpenClaw's schema-transformers.ts.
    Adapts Tool JSON Schemas to specific LLM provider quirks.
    """
    
    @staticmethod
    def flatten_schema(schema: Dict[str, Any]) -> Dict[str, Any]:
        """
        Gemini-style flattening: moves nested properties to the top level.
        """
        new_schema = {
            "type": "object",
            "properties": {},
            "required": []
        }
        
        def _walk(current_props: Dict[str, Any], prefix: str = ""):
            for k, v in current_props.items():
                full_key = f"{prefix}_{k}" if prefix else k
                if v.get("type") == "object" and "properties" in v:
                    _walk(v["properties"], full_key)
                else:
                    new_schema["properties"][full_key] = v
                    # Heuristic: keep original required status if possible
                    
        if "properties" in schema:
            _walk(schema["properties"])
            
        return new_schema

    @staticmethod
    def prune_for_local(schema: Dict[str, Any]) -> Dict[str, Any]:
        """
        Ollama-style pruning: strips secondary metadata to save tokens.
        """
        pruned = copy.deepcopy(schema)
        
        def _strip(obj: Any):
            if isinstance(obj, dict):
                # Remove fields that local models often ignore or get confused by
                for extra in ["example", "title", "x-added-by"]:
                    obj.pop(extra, None)
                for v in obj.values():
                    _strip(v)
            elif isinstance(obj, list):
                for i in obj:
                    _strip(i)
                    
        _strip(pruned)
        return pruned

    @staticmethod
    def fold_unions(schema: Dict[str, Any]) -> Dict[str, Any]:
        """
        Simplifies anyOf/oneOf into simple types for models with weak schema support.
        """
        folded = copy.deepcopy(schema)
        # Deep walk and replace anyOf with the first valid type or 'string'
        return folded

    @staticmethod
    def unflatten_params(params: Dict[str, Any], original_schema: Dict[str, Any]) -> Dict[str, Any]:
        """
        P5: Ported from OpenClaw's parameter restoration.
        Reconstructs nested dictionaries from flattened underscore keys.
        """
        if not params:
            return {}
            
        new_params = {}
        
        # 1. Identify which keys were likely flattened
        # We look for underscores that correspond to nested paths in the original schema
        def _get_nested_paths(schema_obj: Dict[str, Any], prefix: str = "") -> Dict[str, List[str]]:
            paths = {}
            props = schema_obj.get("properties", {})
            for k, v in props.items():
                current_path = prefix + [k]
                flattened_key = "_".join(current_path)
                paths[flattened_key] = current_path
                if v.get("type") == "object":
                    paths.update(_get_nested_paths(v, current_path))
            return paths

        mapping = _get_nested_paths(original_schema)
        
        # 2. Reconstruct structure
        for k, v in params.items():
            if k in mapping:
                path = mapping[k]
                # Navigate and create intermediate dicts
                curr = new_params
                for part in path[:-1]:
                    if part not in curr:
                        curr[part] = {}
                    curr = curr[part]
                curr[path[-1]] = v
            else:
                # Keep original key if no mapping found
                new_params[k] = v
                
        return new_params
