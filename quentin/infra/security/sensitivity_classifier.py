from __future__ import annotations
import os
import re
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)

class SensitivityClassifier:
    """
    P5: Ported from OpenClaw's path-policy system.
    Identifies sensitive paths and recommends execution mode degradation.
    """
    
    SECRET_PATTERNS = [
        r"\.ssh/", r"\.gnupg/", r"\.aws/", r"\.kube/",
        r"\.env(\..+)?$", r".*\.pem$", r"id_rsa",
        r"\.git/config$", r"\.npmrc$", r"\.pypirc$"
    ]

    @classmethod
    def get_sensitivity_level(cls, path_str: str) -> int:
        """
        0: Normal, 1: Engineering Infrastructure, 2: CRITICAL SECRET
        """
        if not path_str: return 0
        
        normalized = path_str.replace("\\", "/").lower()
        
        # Level 2 Check
        if any(re.search(p, normalized) for p in cls.SECRET_PATTERNS):
            return 2
            
        # Level 1 Check (Internal but not secret)
        if ".git/" in normalized or "package-lock.json" in normalized:
            return 1
            
        return 0

    @classmethod
    def should_restrict_execution(cls, params: Dict[str, Any]) -> bool:
        """
        Scans all string parameters for sensitive path references.
        """
        for v in params.values():
            if isinstance(v, str):
                if cls.get_sensitivity_level(v) >= 2:
                    return True
        return False
