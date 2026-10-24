from __future__ import annotations
import logging
from typing import List, Optional

logger = logging.getLogger(__name__)

class InstructionBooster:
    """
    P5: Ported from OpenClaw's dynamic retry instructions.
    Injects forceful constraints based on the level of failure.
    """
    @staticmethod
    def get_boosted_instruction(failure_count: int, last_error: Optional[str] = None) -> str:
        if failure_count <= 0:
            return ""
            
        boosters = []
        
        # Level 1: Gentle Reminder
        if failure_count >= 1:
            boosters.append("NOTE: Your last attempt did not succeed. Review the error and adjust your plan.")
            
        # Level 2: Repetition Prohibition
        if failure_count >= 2:
            boosters.append("CRITICAL: You are repeating unsuccessful actions. DO NOT use the same tool arguments as before. Try a DIFFERENT strategy.")
            
        # Level 3: Strategic Shift
        if failure_count >= 3:
            boosters.append("WARNING: You are stuck. If the current tool isn't working, consider an alternative tool or a broader exploration. Re-read the file or check the directory structure again.")

        if last_error:
            boosters.append(f"LAST ERROR OBSERVED: {last_error}")

        return "\n\n" + "\n".join(f"[RETRY_GUIDE_L{failure_count}] {b}" for b in boosters)
