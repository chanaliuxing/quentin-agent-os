from __future__ import annotations
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

class LatencyProfile:
    """
    P5: Ported from OpenClaw's latency-aware timeout system.
    Defines physical time budgets for different categories of tools.
    """
    
    # Timeouts in seconds
    PROFILES = {
        "io_fast": 5.0,      # ls, cat, pwd
        "io_standard": 15.0, # read_file, exists
        "io_heavy": 45.0,    # write_file, search_replace, patch
        "network": 60.0,     # browser.navigate, web_research
        "compute": 120.0,    # skill_mining, analysis
        "build": 600.0,      # shell.run_command (compilation)
    }

    TOOL_MAPPING = {
        "ls": "io_fast",
        "pwd": "io_fast",
        "cat": "io_fast",
        "fs.read_file": "io_standard",
        "fs.exists": "io_standard",
        "fs.write_file": "io_heavy",
        "fs.search_replace": "io_heavy",
        "browser.navigate": "network",
        "web.search": "network",
        "shell.run_command": "build",
    }

    @classmethod
    def get_timeout(cls, tool_name: str, user_override: Optional[float] = None) -> float:
        """
        Calculates the physical time budget for a tool.
        """
        if user_override is not None:
            return float(user_override)
            
        profile_key = cls.TOOL_MAPPING.get(tool_name, "io_heavy") # Default to safe heavy
        timeout = cls.PROFILES.get(profile_key, 30.0)
        
        logger.debug(f"LatencyProfile: Tool {tool_name} assigned {timeout}s (profile={profile_key})")
        return timeout
