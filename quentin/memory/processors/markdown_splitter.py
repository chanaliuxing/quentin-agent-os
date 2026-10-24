from __future__ import annotations
import re
import logging
from typing import List, Dict, Any, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)

@dataclass
class MemoryChunk:
    text: str
    start_line: int
    end_line: int
    headers: List[str]
    metadata: Dict[str, Any]

class MarkdownSplitter:
    """
    P5: Ported from OpenClaw's internal.ts chunkMarkdown.
    Splits long Markdown files into semantic chunks with header injection.
    """
    def __init__(self, chunk_size: int = 1500, overlap: int = 200):
        self.chunk_size = chunk_size
        self.overlap = overlap

    def split(self, text: str, file_path: str = "") -> List[MemoryChunk]:
        lines = text.splitlines()
        chunks: List[MemoryChunk] = []
        
        current_headers = ["", "", "", "", "", ""] # H1 to H6
        current_chunk_lines = []
        current_chunk_len = 0
        
        header_pattern = re.compile(r"^(#{1,6})\s+(.+)$")

        for line_idx, line in enumerate(lines):
            # 1. Track Headers
            header_match = header_pattern.match(line)
            if header_match:
                level = len(header_match.group(1))
                title = header_match.group(2).strip()
                # Update stack: reset lower levels
                current_headers[level-1] = title
                for i in range(level, 6):
                    current_headers[i] = ""

            current_chunk_lines.append(line)
            current_chunk_len += len(line) + 1

            # 2. Check Chunk Boundary
            if current_chunk_len >= self.chunk_size:
                chunks.append(self._create_chunk(current_chunk_lines, current_headers, line_idx, file_path))
                
                # Apply Overlap (Sliding Window)
                overlap_lines = []
                overlap_len = 0
                for back_line in reversed(current_chunk_lines):
                    overlap_lines.insert(0, back_line)
                    overlap_len += len(back_line) + 1
                    if overlap_len >= self.overlap:
                        break
                
                current_chunk_lines = overlap_lines
                current_chunk_len = overlap_len

        # Final chunk
        if current_chunk_lines:
            chunks.append(self._create_chunk(current_chunk_lines, current_headers, len(lines)-1, file_path))

        return chunks

    def _create_chunk(self, lines: List[str], headers: List[str], end_line: int, file_path: str) -> MemoryChunk:
        content = "\n".join(lines)
        
        # 3. Title Injection (Surgery Twenty-eight)
        active_headers = [h for h in headers if h]
        header_prefix = " > ".join(active_headers)
        
        context_prefix = f"[File: {file_path}]"
        if header_prefix:
            context_prefix += f" [Section: {header_prefix}]"
            
        injected_text = f"{context_prefix}\n\n{content}"
        
        start_line = end_line - len(lines) + 1
        return MemoryChunk(
            text=injected_text,
            start_line=max(0, start_line),
            end_line=end_line,
            headers=active_headers,
            metadata={"file_path": file_path, "context_prefix": context_prefix}
        )
