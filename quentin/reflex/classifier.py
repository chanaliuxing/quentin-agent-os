from __future__ import annotations
import re
from typing import Optional, Dict, Any, Tuple
from dataclasses import dataclass

@dataclass
class ReflexAction:
    tool_name: str
    params: Dict[str, Any]
    description: str

class ReflexClassifier:
    """
    L0 Intent Classifier (Spinal Cord).
    Detects trivial requests that don't need a full frontal cortex (LLM).
    P5: Ported from OpenClaw's reactive command handling.
    """
    def __init__(self):
        # Expanded patterns for instant execution
        self.patterns = [
            (r"^(?:list|ls)\s*(.*)$", "ls", "path"),
            (r"^(?:read|cat)\s+(.*)$", "fs.read_file", "path"),
            (r"^(?:show|display)\s+(.*)$", "fs.read_file", "path"),
            (r"^(?:mkdir|make directory)\s+(.*)$", "mkdir", "path"),
            (r"^pwd$", "shell.run_command", "command"),
            (r"^whoami$", "shell.run_command", "command"),
            (r"^date$", "shell.run_command", "command"),
            (r"^env$", "shell.run_command", "command"),
        ]

    def classify(self, user_input: str) -> Optional[ReflexAction]:
        text = user_input.strip()
        
        # 1. Direct Pattern Matching
        for pattern, tool, arg_name in self.patterns:
            match = re.match(pattern, text, re.IGNORECASE)
            if match:
                params = {}
                if tool == "shell.run_command" and arg_name == "command":
                    params["command"] = text
                elif arg_name:
                    val = match.group(1).strip().strip("\"' ")
                    params[arg_name] = val or "."
                
                return ReflexAction(
                    tool_name=tool,
                    params=params,
                    description=f"Spinal Reflex: {tool} {params}"
                )
        
        # 2. Command-like recognition (e.g. ./script.sh)
        if text.startswith("./") and not " " in text:
             return ReflexAction(
                tool_name="shell.run_command",
                params={"command": text},
                description=f"Spinal Reflex: Executing local script {text}"
            )

        return None
