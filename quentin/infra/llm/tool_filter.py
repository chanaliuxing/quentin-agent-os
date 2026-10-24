from __future__ import annotations

import logging
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

class ToolFilter:
    """
    Context-aware Tool Selector.
    Prevents context bloat by focusing the brain on relevant tools.
    Aligned with OpenClaw's dynamic tool injection logic.
    """
    
    # Domain -> Relevant Tool Prefixes
    DOMAIN_MAPPING = {
        "web": ["browser.", "fs.", "web."],
        "mobile": ["mobile.", "fs.", "vision."],
        "desktop": ["desktop.", "fs.", "shell."],
        "core": ["fs.", "shell.", "cron."],
    }

    @staticmethod
    def filter_tools(all_tools: List[Dict[str, Any]], domain: str) -> List[Dict[str, Any]]:
        """
        Returns a refined list of tools.
        High-relevance tools get full descriptions.
        Low-relevance tools get summarized or hidden.
        """
        domain = domain.lower()
        allowed_prefixes = ToolFilter.DOMAIN_MAPPING.get(domain, [])
        # Always include universal tools
        allowed_prefixes.extend(["memory.", "system."])
        
        refined_tools = []
        for tool in all_tools:
            tool_id = tool.get("skill_id") or tool.get("name")
            
            # Check relevance
            is_relevant = any(tool_id.startswith(p) for p in allowed_prefixes)
            
            if is_relevant:
                # Full fidelity
                refined_tools.append(tool)
            else:
                # 10% chance to keep as "distraction check" or hidden completely
                # OpenClaw logic: hide completely to save tokens
                pass
                
        return refined_tools

# Global instance
tool_filter = ToolFilter()
