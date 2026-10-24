from __future__ import annotations
import hashlib
import logging
from pathlib import Path
from typing import Tuple, Optional

logger = logging.getLogger(__name__)

class PhysicalVerifier:
    """
    P5: Ported from OpenClaw's 'Action Echo' system.
    Ensures physical file state matches intended cognitive state.
    """
    
    @staticmethod
    def compute_content_hash(text: str) -> str:
        """Standardized hash for in-memory text."""
        return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()

    @classmethod
    def verify_file_content(cls, file_path: str | Path, expected_content: str) -> Tuple[bool, str]:
        """
        Physically reads the file from disk and compares hashes.
        Returns (success, actual_hash).
        """
        p = Path(file_path)
        if not p.exists():
            return False, "file_not_found"
            
        try:
            # Atomic Read Echo
            actual_content = p.read_text(encoding="utf-8", errors="ignore")
            actual_hash = cls.compute_content_hash(actual_content)
            expected_hash = cls.compute_content_hash(expected_content)
            
            if actual_hash == expected_hash:
                return True, actual_hash
            else:
                logger.error(f"PhysicalVerifier: Hash mismatch for {file_path}! Expected {expected_hash}, got {actual_hash}")
                return False, actual_hash
        except Exception as e:
            logger.exception(f"PhysicalVerifier: Failed to read {file_path} for verification")
            return False, f"error: {str(e)}"
