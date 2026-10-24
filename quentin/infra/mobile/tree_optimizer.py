from __future__ import annotations

import xml.etree.ElementTree as ET
import logging
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

class UITreeOptimizer:
    """
    Precision UI Tree Optimizer with Diffing support.
    """
    def __init__(self):
        self._last_tree_hash = None

    @staticmethod
    def diff_trees(old_tree: List[Dict], new_tree: List[Dict]) -> Optional[List[Dict]]:
        """
        Returns the delta if the tree has changed significantly.
        (Simplified: Returns None if hashes match, else full new tree).
        In atomic parity mode, we compare structured content.
        """
        if json.dumps(old_tree) == json.dumps(new_tree):
            return None
        return new_tree

    @staticmethod
    def optimize_xml(xml_content: str) -> List[Dict[str, Any]]:
        """
        Parses ADB XML dump and flattens it into an LLM-friendly semantic list.
        """
        if not xml_content: return []
        
        try:
            root = ET.fromstring(xml_content)
        except Exception as e:
            logger.error(f"XML Parse error: {e}")
            return []

        interactables = []
        
        def walk(node):
            # 1. Extract raw bounds: "[x1,y1][x2,y2]"
            bounds_str = node.attrib.get("bounds", "")
            import re
            match = re.findall(r"(\d+)", bounds_str)
            if len(match) == 4:
                x1, y1, x2, y2 = map(int, match)
                bounds = [x1, y1, x2 - x1, y2 - y1] # [x, y, w, h]
            else:
                bounds = None

            # 2. Check for semantic value (OpenClaw precision)
            text = node.attrib.get("text", "").strip()
            desc = node.attrib.get("content-desc", "").strip()
            resource_id = node.attrib.get("resource-id", "").split("/")[-1]
            role = node.attrib.get("class", "").split(".")[-1]
            
            is_clickable = node.attrib.get("clickable") == "true"
            
            # 3. Pruning: Only keep nodes that have text OR are clickable
            if bounds and (text or desc or is_clickable):
                interactables.append({
                    "role": role,
                    "id": resource_id,
                    "text": text or desc,
                    "bounds": bounds,
                    "clickable": is_clickable
                })

            for child in node:
                walk(child)

        walk(root)
        return interactables

# Global instance
tree_optimizer = UITreeOptimizer()
