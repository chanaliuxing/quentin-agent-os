from __future__ import annotations

import re
import logging
from pathlib import Path
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)

class ExecutiveAuditor:
    """
    Hardened security auditor for tool calls and shell commands.
    Directly ported from OpenClaw's exec-safety logic.
    """
    
    # 1. Dangerous Command Patterns (Blacklist)
    DANGEROUS_COMMANDS = [
        r"rm\s+-rf\s+/",           # Delete root
        r"chmod\s+777",            # Insecure permissions
        r"mkfs",                   # Format disk
        r"dd\s+if=/dev/zero",      # Wipe disk
        r":\(\)\{ :\|:& \};:",     # Fork bomb
        r"ssh-keygen",             # Key manipulation
        r"cat\s+.*\.ssh",          # Reading keys
        r"env\s+>\s+",             # Leaking env to file
    ]

    # 2. Protected Paths (No-write zone)
    PROTECTED_PATHS = [
        "/etc", "/bin", "/sbin", "/usr/bin", "/usr/sbin",
        ".ssh", ".gnupg", ".aws", ".config/gcloud"
    ]

    # 3. Credential Scrubbing (Regex for API Keys)
    SENSITIVE_REGEX = [
        r"sk-[a-zA-Z0-9]{32,}",    # OpenAI style
        r"AIza[a-zA-Z0-9\-_]{35}", # Gemini style
        r"(?i)password|token|secret"
    ]

    def audit_command(self, command: str) -> Tuple[bool, Optional[str]]:
        """
        Check if a shell command is safe to execute.
        Returns (is_safe, reason).
        """
        # A. Dangerous Keyword Check
        for pattern in self.DANGEROUS_COMMANDS:
            if re.search(pattern, command):
                return False, f"Dangerous command pattern detected: {pattern}"

        # B. Path Traversal Check
        if ".." in command:
            return False, "Potential path traversal detected (..)"

        # C. Absolute Path Protection
        for path in self.PROTECTED_PATHS:
            if path in command:
                # Basic check, can be improved with proper path resolution
                return False, f"Attempt to access protected system path: {path}"

        return True, None

    def audit_file_operation(self, operation: str, path: str) -> Tuple[bool, Optional[str]]:
        """
        Audits file reads/writes.
        """
        p = str(path).lower()
        
        # 1. Deny access to sensitive system paths
        for protected in self.PROTECTED_PATHS:
            if protected in p:
                return False, f"Unauthorized access to system path: {protected}"
        
        # 2. Deny path traversal
        if ".." in p:
            return False, "Path traversal attempt detected."

        # 3. Restrict write operations to certain zones if needed
        if operation == "write":
            # Example: Only allow writing to data/ or repo subdirs
            pass

        return True, None

    def audit_skill_call(self, skill_id: str, args: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        """
        Audits high-level skill calls based on their arguments.
        """
        if skill_id == "run_bash":
            return self.audit_command(args.get("command", ""))
        
        if skill_id in ("fs.write_file", "fs.search_replace"):
            return self.audit_file_operation("write", args.get("file_path", ""))
            
        return True, None

# Global instance
auditor = ExecutiveAuditor()
