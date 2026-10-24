from __future__ import annotations
import re
import logging
from typing import List, Set

logger = logging.getLogger(__name__)

class EchoSanitizer:
    """
    P5: Ported from OpenClaw's echo-detector.ts.
    Detects and removes command echoes from PTY stdout streams.
    """
    def __init__(self):
        self.recent_commands: List[str] = []
        self.max_history = 5

    def register_command(self, cmd: str):
        """Called when a command is sent to stdin."""
        clean_cmd = cmd.strip()
        if clean_cmd:
            self.recent_commands.append(clean_cmd)
            if len(self.recent_commands) > self.max_history:
                self.recent_commands.pop(0)

    def is_echo(self, line: str) -> bool:
        """
        Checks if the line is a physical echo of a recently sent command.
        """
        clean_line = line.strip()
        if not clean_line:
            return False
            
        for cmd in self.recent_commands:
            # 1. Exact match
            if clean_line == cmd:
                return True
            # 2. Prompt match: user@host:~$ ls
            if clean_line.endswith(cmd) and len(clean_line) > len(cmd):
                # Heuristic: check if the prefix looks like a prompt (contains @ or : or $)
                prefix = clean_line[:-len(cmd)]
                if any(c in prefix for c in ("@", ":", "$", "#", ">")):
                    return True
        return False
