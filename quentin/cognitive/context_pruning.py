from __future__ import annotations
import logging
from typing import List, Dict, Any, Set

from quentin.agents.pi_extensions.context_pruning import prune_message_history

logger = logging.getLogger(__name__)

class ContextPruner:
    """
    P5: Ported from OpenClaw's context-pruning module.
    Refines message history by stripping redundant and low-value tokens.
    """
    def __init__(self):
        self.repetition_threshold = 3
        self.seen_tool_outputs: Dict[str, int] = {} # hash -> count

    def prune(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Executes multi-stage pruning on the message history.
        """
        if not messages:
            return []
        before = len(messages)
        out = prune_message_history(
            messages,
            seen_counts=self.seen_tool_outputs,
            repetition_threshold=self.repetition_threshold,
        )
        removed = before - len(out)
        if removed > 0:
            logger.info("ContextPruner: removed %s repetitive/noisy messages", removed)
        return out

    def _is_redundant_error(self, content: str) -> bool:
        """Identifies if this message is a repeated failure we can skip."""
        # Kept for backward compatibility with existing callers.
        from quentin.agents.pi_extensions.context_pruning.repetition import is_redundant_error_message

        return is_redundant_error_message(
            content=content,
            seen_counts=self.seen_tool_outputs,
            repetition_threshold=self.repetition_threshold,
        )

    def _squash_large_noise(self, content: str) -> str:
        """Collapses extremely large outputs that are likely just noise."""
        # Kept for backward compatibility with existing callers.
        from quentin.agents.pi_extensions.context_pruning.size import squash_large_content

        return squash_large_content(content)
