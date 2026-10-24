from __future__ import annotations

import re
import logging
from typing import List, Optional, Callable

logger = logging.getLogger(__name__)

class BlockReplyCoalescer:
    """
    P5: Ported from OpenClaw's EmbeddedBlockChunker.
    Aggregates fine-grained LLM tokens into meaningful semantic blocks.
    """
    def __init__(self, on_block_ready: Callable[[str], None]):
        self.buffer = ""
        self.on_block_ready = on_block_ready
        # Pattern for block boundaries: double newline, list items, or code blocks
        self.boundary_pattern = re.compile(r"(\n\n|(?<=\n)[-*]\s|(?<=\n)\d+\.\s|```)")

    def push_token(self, token: str):
        self.buffer += token
        
        # Check if we have a complete block
        # We look for the last boundary marker
        matches = list(self.boundary_pattern.finditer(self.buffer))
        if matches:
            # Find the split point (excluding the last one if it's too fresh)
            # This is a simplified version of OpenClaw's complex chunking
            split_idx = matches[-1].start()
            
            # If the block is substantial, emit it
            if split_idx > 40: # OpenClaw uses dynamic thresholds
                ready_block = self.buffer[:split_idx].strip()
                if ready_block:
                    self.on_block_ready(ready_block)
                self.buffer = self.buffer[split_idx:]

    def flush(self):
        if self.buffer.strip():
            self.on_block_ready(self.buffer.strip())
        self.buffer = ""
