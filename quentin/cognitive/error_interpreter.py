from __future__ import annotations
import re
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

class ErrorInterpreter:
    """
    P5: Ported from OpenClaw's 'Reactive Guidance'.
    Translates raw tool errors into actionable insights for the Planner.
    """
    
    PATTERNS = {
        "command_not_found": {
            "regex": r"command not found|executable file not found",
            "hint": "The command you tried to run is not installed or not in the PATH. Try 'ls /usr/bin' or check if you need to install a package."
        },
        "grep_no_match": {
            "regex": r"grep:.*: No such file or directory|exit code 1",
            "hint": "Grep returned no results. Verify the file path exists and your regex pattern matches the actual file content."
        },
        "permission_denied": {
            "regex": r"permission denied|EACCES",
            "hint": "This path is protected. You may need to request sudo or work in the 'mutable/' directory."
        },
        "json_parse_error": {
            "regex": r"Expecting property name enclosed in double quotes|JSONDecodeError",
            "hint": "Your tool output was malformed JSON. Ensure you escape special characters and use double quotes."
        },
        "stale_element": {
            "regex": r"stale element reference|element is not attached",
            "hint": "The UI changed while you were acting. Refresh the UI tree with 'observe' and try again."
        }
    }

    @classmethod
    def interpret(cls, tool_name: str, raw_error: str) -> Optional[str]:
        """
        Scans raw error for patterns and returns a corrective hint.
        """
        low_err = raw_error.lower()
        
        # 1. Specialized tool logic
        if tool_name == "shell.run_command":
            if "grep" in low_err:
                return cls.PATTERNS["grep_no_match"]["hint"]
            
        # 2. General pattern matching
        for key, config in cls.PATTERNS.items():
            if re.search(config["regex"], low_err, re.IGNORECASE):
                return config["hint"]
                
        return None
