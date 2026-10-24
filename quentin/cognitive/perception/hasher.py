from __future__ import annotations
import hashlib
import json
import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

class PerceptionHasher:
    """
    P5: Ported from OpenClaw's perception-hashing.ts.
    Generates a stable semantic fingerprint of a UI state.
    """
    @staticmethod
    def compute_ui_hash(ui_tree: Dict[str, Any], url: str = "") -> str:
        """
        Computes a hash that is stable across minor non-semantic changes.
        """
        # 1. Simplify tree for hashing (OpenClaw Parity)
        # We strip transient data like exact pixels if we only want semantic stability
        def get_semantic_core(node: Dict[str, Any]) -> Any:
            if not node: return None
            # Only hash role and name, and recursivly children
            core = {
                "r": node.get("role"),
                "n": node.get("name"),
                "c": [get_semantic_core(c) for c in node.get("children", [])]
            }
            return core

        semantic_tree = get_semantic_core(ui_tree)
        
        # 2. Combine with URL
        payload = {
            "u": url,
            "t": semantic_tree
        }
        
        # 3. Deterministic JSON and Hash
        encoded = json.dumps(payload, sort_keys=True, ensure_ascii=True).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()
