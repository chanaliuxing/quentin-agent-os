from __future__ import annotations
import os
import socket
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple

logger = logging.getLogger(__name__)

class ContractEngine:
    """
    P5: Ported from OpenClaw's 'Workflow State Machine'.
    Verifies that the physical world matches the Agent's promised outcomes.
    """
    
    @staticmethod
    def verify_contract(expected_state: Dict[str, Any], repo_root: Path) -> Tuple[bool, List[str]]:
        """
        Validates a list of physical expectations.
        Returns (success, error_messages).
        """
        errors = []
        
        # 1. File Existence Contract
        for path_str in expected_state.get("files_exist", []):
            full_path = repo_root / path_str
            if not full_path.exists():
                errors.append(f"Missing expected file: {path_str}")
                
        # 2. Port Open Contract
        for port in expected_state.get("ports_open", []):
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(1.0)
            if sock.connect_ex(('127.0.0.1', int(port))) != 0:
                errors.append(f"Expected port {port} to be OPEN, but it is CLOSED")
            sock.close()
            
        # 3. Environment Variable Contract
        for var_name in expected_state.get("env_vars_set", []):
            if var_name not in os.environ:
                errors.append(f"Missing expected environment variable: {var_name}")
                
        return len(errors) == 0, errors
