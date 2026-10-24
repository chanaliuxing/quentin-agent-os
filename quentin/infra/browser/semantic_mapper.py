from __future__ import annotations
import logging
from typing import Dict, Any, List, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)

@dataclass
class SemanticElement:
    ref_id: str
    role: str
    name: str
    description: Optional[str] = None
    is_interactive: bool = True
    metadata: Dict[str, Any] = None

class SemanticMapper:
    """
    P5: Ported from OpenClaw's Role-based referencing system.
    Converts a complex DOM/Aria tree into a flattened semantic list for LLM.
    Includes physical bounding boxes for SoM.
    """
    def __init__(self):
        self.ref_counter = 0
        self.registry: Dict[str, Any] = {} # ref_id -> data

    def reset(self):
        self.ref_counter = 0
        self.registry = {}

    def generate_snapshot(self, aria_tree: Dict[str, Any], viewport: Optional[Dict[str, float]] = None) -> str:
        """
        Flattens the aria tree and assigns eN IDs.
        Includes physical bounding boxes normalized to 1000-point grid.
        """
        self.reset()
        self.viewport = viewport or {"width": 1280, "height": 720}
        lines = []
        self._traverse(aria_tree, lines)
        return "\n".join(lines)

    def _traverse(self, node: Dict[str, Any], lines: List[str], depth: int = 0):
        role = node.get("role")
        name = node.get("name", "").strip()
        
        # We only assign refs to interactive or meaningful elements
        interactive_roles = {"button", "link", "textbox", "checkbox", "menuitem", "combobox", "tab"}
        
        if role in interactive_roles or (name and role not in {"generic", "presentation"}):
            self.ref_counter += 1
            ref_id = f"e{self.ref_counter}"
            
            raw_bounds = node.get("bounds")
            
            # P5: Surgery Forty-five - Spatial Normalization (OpenClaw Parity)
            from quentin.infra.perception.spatial_utils import SpatialUtils
            norm_bounds = SpatialUtils.normalize_bounds(
                raw_bounds, 
                self.viewport["width"], 
                self.viewport["height"]
            ) if raw_bounds else None
            
            # Store in registry for later physical lookup and SoM visualization
            self.registry[ref_id] = {
                "role": role,
                "name": name,
                "selector": node.get("selector"),
                "bounds": raw_bounds, # Keep raw for SoM/Click
                "norm_bounds": norm_bounds,
                "xpath": node.get("xpath")
            }
            
            indent = "  " * depth
            bounds_str = ""
            if norm_bounds:
                # Atomic Detail: Use normalized grid for LLM to simplify spatial reasoning
                b = norm_bounds
                hint = SpatialUtils.get_layout_hint(b)
                bounds_str = f" [box={b[0]},{b[1]},{b[2]},{b[3]}] [pos={hint}]"
                
            lines.append(f"{indent}- {role} \"{name}\" [ref={ref_id}]{bounds_str}")
            
        # Recursive traverse children
        for child in node.get("children", []):
            self._traverse(child, lines, depth + 1)

    def get_selector(self, ref_id: str) -> Optional[str]:
        entry = self.registry.get(ref_id)
        return entry["selector"] if entry else None
        
    def get_bounds(self, ref_id: str) -> Optional[List[float]]:
        entry = self.registry.get(ref_id)
        return entry.get("bounds") if entry else None
