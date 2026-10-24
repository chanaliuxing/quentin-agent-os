from __future__ import annotations
import os
import json
import time
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)

class ActionRecorder:
    """
    P5: Ported from OpenClaw's Action Recording system.
    Captures visual frames of Agent interactions for audit and debugging.
    """
    def __init__(self, session_id: str, base_dir: str | Path = "data/recordings"):
        self.session_id = session_id
        self.output_dir = Path(base_dir).resolve() / session_id
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.index_path = self.output_dir / "index.jsonl"
        self.frame_count = 0

    def capture_frame(self, image_b64: str, action_name: str, metadata: Dict[str, Any] = None):
        """
        Physically persists a frame and updates the index.
        """
        import base64
        self.frame_count += 1
        ts = int(time.time() * 1000)
        filename = f"{self.frame_count:04d}_{ts}_{action_name}.jpg"
        frame_path = self.output_dir / filename
        
        try:
            # 1. Physical Save
            img_data = base64.b64decode(image_b64)
            frame_path.write_bytes(img_data)
            
            # 2. Index Entry
            entry = {
                "frame": self.frame_count,
                "timestamp": ts,
                "action": action_name,
                "path": str(frame_path.relative_to(Path.cwd())),
                "meta": metadata or {}
            }
            
            with open(self.index_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry) + "\n")
                
            return str(frame_path)
        except Exception as e:
            logger.error(f"ActionRecorder: Failed to save frame: {e}")
            return None

    def get_recording_summary(self) -> str:
        return f"Recording active: {self.frame_count} frames captured in {self.output_dir}"
