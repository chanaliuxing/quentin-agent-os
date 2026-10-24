from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

@dataclass
class CanvasElement:
    id: str
    type: str  # "button", "text", "layout", "container"
    content: str
    properties: Dict[str, Any] = field(default_factory=dict)

class VirtualCanvas:
    """
    Placeholder for visual feedback (Canvas).
    Even in text-only mode, providing a 'virtual canvas' allows the model to
    maintain a spatial mental model of the UI it is attempting to evolve.
    """
    def __init__(self) -> None:
        self._elements: Dict[str, CanvasElement] = {}
        self._last_snapshot: str = ""

    def update_element(self, element: CanvasElement) -> None:
        self._elements[element.id] = element

    def render_text_description(self) -> str:
        """
        Produces a text-only representation of the UI for model sensing.
        """
        if not self._elements:
            return "Canvas is empty."
        
        lines = ["Current Virtual Canvas State:"]
        for el_id, el in sorted(self._elements.items()):
            lines.append(f"- [{el.type}] {el_id}: {el.content}")
        return "\n".join(lines)

    def clear(self) -> None:
        self._elements = {}
