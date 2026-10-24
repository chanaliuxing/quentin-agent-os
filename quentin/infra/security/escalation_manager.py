from __future__ import annotations
import logging
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)

class EscalationManager:
    """
    P5: Ported from OpenClaw's dynamic privilege logic.
    Manages the lifecycle of high-privilege command requests.
    """
    
    ESCALATION_PATTERNS = [
        "permission denied",
        "operation not permitted",
        "eacces",
        "requires root privileges",
        "sudo: a password is required"
    ]

    @classmethod
    def is_escalation_needed(cls, stderr: str) -> bool:
        """
        Scans output for physical signs of permission failure.
        """
        if not stderr:
            return False
        low = stderr.lower()
        return any(p in low for p in cls.ESCALATION_PATTERNS)

    @classmethod
    def prepare_escalation_request(cls, command: str, reason: str) -> Dict[str, Any]:
        """
        Builds a HITL (Human-in-the-loop) payload.
        """
        return {
            "status": "requires_approval",
            "type": "privilege_escalation",
            "command": command,
            "reason": reason,
            "hint": "This command requires elevated privileges (sudo). Confirm via UI or CLI to proceed."
        }

    @classmethod
    def format_elevated_command(cls, command: str) -> str:
        """
        Wraps command with sudo if not already present.
        """
        if command.strip().startswith("sudo"):
            return command
        return f"sudo {command}"
