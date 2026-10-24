from __future__ import annotations

import os
import json
import logging
import shutil
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

class AtomicFS:
    """
    Safe file system operations ported from OpenClaw.
    Ensures data integrity via atomic writes.
    """
    
    @staticmethod
    def write_json(file_path: str | Path, data: Any, indent: int = 2):
        """
        Writes JSON to a file atomically.
        Logic: Write to .tmp -> sync to disk -> rename to final path.
        """
        path = Path(file_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        
        # 1. Create a temporary file in the same directory
        fd, tmp_path = tempfile.mkstemp(
            dir=str(path.parent), 
            prefix=f"{path.name}.tmp-", 
            text=True
        )
        
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=indent)
                f.flush()
                os.fsync(f.fileno()) # Force write to physical disk
            
            # 2. Atomic rename (overwrites existing file)
            os.replace(tmp_path, path)
        except Exception as e:
            logger.error(f"Atomic write failed for {path}: {e}")
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
            raise

    @staticmethod
    def read_json(file_path: str | Path) -> Optional[Any]:
        """Safely reads JSON with error logging."""
        path = Path(file_path)
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding='utf-8'))
        except Exception as e:
            logger.error(f"Failed to read JSON from {path}: {e}")
            return None

# Global instance
fs_safe = AtomicFS()
