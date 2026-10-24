from __future__ import annotations
import logging
import uuid
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)

class UIComponent:
    """Standard definition for a serializable UI element."""
    def __init__(self, type: str, props: Dict[str, Any] = None):
        self.type = type
        self.props = props or {}
        self.id = f"comp_{uuid.uuid4().hex[:8]}"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "component_id": self.id,
            "type": self.type,
            "props": self.props
        }

class UIProtocol:
    """
    P5: Ported from OpenClaw's A2UI (Agent-to-UI) system.
    Builds structured UI payloads for the frontend canvas.
    """
    
    @staticmethod
    def create_diff_view(file_path: str, diff_text: str) -> Dict[str, Any]:
        return UIComponent("DiffViewer", {
            "path": file_path,
            "diff": diff_text,
            "title": f"Review Changes: {file_path}"
        }).to_dict()

    @staticmethod
    def create_action_card(title: str, actions: List[str]) -> Dict[str, Any]:
        return UIComponent("ActionCard", {
            "title": title,
            "buttons": [{"label": a, "action_id": a.lower().replace(" ", "_")} for a in actions]
        }).to_dict()

    @staticmethod
    def create_data_table(headers: List[str], rows: List[List[Any]]) -> Dict[str, Any]:
        return UIComponent("DataTable", {
            "headers": headers,
            "rows": rows
        }).to_dict()
