from __future__ import annotations
import os
import logging
from typing import Tuple, Optional

logger = logging.getLogger(__name__)

class IOUtils:
    """
    P5: Ported from OpenClaw's byte-range file syncing.
    Efficiently reads only the new parts of a growing file.
    """
    @staticmethod
    def read_delta(file_path: str, last_offset: int = 0) -> Tuple[str, int]:
        """
        Reads content from the given offset to the end.
        Returns (new_content, new_offset).
        """
        if not os.path.exists(file_path):
            return "", 0
            
        current_size = os.path.getsize(file_path)
        
        # 1. Truncation Check (OpenClaw Parity)
        if current_size < last_offset:
            logger.info(f"IOUtils: File {file_path} was truncated. Resetting offset.")
            last_offset = 0
            
        if current_size == last_offset:
            return "", last_offset
            
        # 2. Atomic Seek & Read
        with open(file_path, "rb") as f:
            f.seek(last_offset)
            new_bytes = f.read()
            
        try:
            new_text = new_bytes.decode("utf-8", errors="ignore")
            return new_text, current_size
        except Exception as e:
            logger.error(f"IOUtils: Failed to decode delta from {file_path}: {e}")
            return "", last_offset
