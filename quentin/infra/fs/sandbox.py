from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

class VirtualWorkspace:
    """
    Implements Path Virtualization.
    Maps AI-visible paths to physical host paths.
    Aligned with OpenClaw's src/agents/workspace logic.
    """
    def __init__(self, physical_root: str = ".", virtual_root: str = "/home/agent/workspace"):
        self.physical_root = Path(physical_root).resolve()
        self.virtual_root = Path(virtual_root)
        self.is_windows = os.name == 'nt'

    def normalize_path(self, raw_path: str) -> str:
        """Atomic: Ensures correct slashes based on host OS."""
        if self.is_windows:
            return raw_path.replace("/", "\\")
        return raw_path.replace("\\", "/")

    def to_physical(self, virtual_path: str) -> Path:
        """Converts /home/agent/workspace/file.py to absolute physical path."""
        # Atomic: first normalize incoming virtual path
        v_path_str = self.normalize_path(virtual_path)
        v_path = Path(v_path_str)
        
        if str(v_path).startswith(str(self.virtual_root)):
            rel_path = v_path.relative_to(self.virtual_root)
            return (self.physical_root / rel_path).resolve()
        
        return (self.physical_root / v_path).resolve()

    def to_virtual(self, physical_path: str | Path) -> str:
        """Converts local path to /home/agent/workspace/ format for LLM."""
        p_path = Path(physical_path).resolve()
        if p_path.is_relative_to(self.physical_root):
            rel_path = p_path.relative_to(self.physical_root)
            return str(self.virtual_root / rel_path)
        return str(physical_path)

# Global instance
workspace = VirtualWorkspace()
