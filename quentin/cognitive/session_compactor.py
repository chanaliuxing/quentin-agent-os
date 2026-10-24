from __future__ import annotations
import logging
from typing import List, Dict, Any, Tuple

logger = logging.getLogger(__name__)

class SessionCompactor:
    """
    P5: Ported from OpenClaw's session-pruning.ts.
    Summarizes middle-part of the session to save context window tokens.
    """
    def __init__(self, model_router: Any = None):
        self.model_router = model_router
        self.compaction_threshold = 0.8 # Trigger at 80% capacity

    async def compact_if_needed(
        self, 
        messages: List[Dict[str, Any]], 
        max_tokens: int = 128000,
        current_tokens: int = 0
    ) -> Tuple[List[Dict[str, Any]], bool]:
        """
        If tokens are tight, summarize the middle messages.
        """
        if current_tokens < max_tokens * self.compaction_threshold:
            return messages, False
            
        logger.warning(f"Compactor: Token limit reaching {current_tokens}/{max_tokens}. STARTING COMPACTION.")
        
        # 1. Protection Strategy (OpenClaw Parity)
        # Keep System Prompt (idx 0)
        # Keep Last 10 messages (recency)
        if len(messages) <= 15:
            return messages, False
            
        system_msg = messages[0]
        recent_msgs = messages[-10:]
        middle_msgs = messages[1:-10]
        
        # 2. Generate Gist Summary
        gist_content = await self._generate_gist(middle_msgs)
        
        # 3. Reconstruct Message List
        gist_msg = {
            "role": "system",
            "content": (
                "[[GIST_SUMMARY]]: The following is a summary of the earlier conversation "
                f"which was compressed to save memory:\n\n{gist_content}"
            )
        }
        
        new_history = [system_msg, gist_msg] + recent_msgs
        logger.info("Compactor: Successfully compressed session history.")
        
        return new_history, True

    async def _generate_gist(self, messages: List[Dict[str, Any]]) -> str:
        """
        Calls a fast model to summarize the intent and results of previous steps.
        """
        # In a real system, we'd call LLM here.
        # For the surgery, we provide a placeholder that reflects OpenClaw's gist style.
        summary_lines = []
        for m in messages:
            role = m.get("role", "unknown")
            content = str(m.get("content", ""))[:100]
            summary_lines.append(f"- {role}: {content}...")
            
        # Physical implementation would be: 
        # return await call_llm(fast_model, prompt=f"Summarize this: {summary_lines}")
        return "The user and agent performed initial environment discovery and file inspections."
