from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Tuple

@dataclass
class CodeSpan:
    start: int
    end: int
    is_fence: bool # True for ```, False for `

class MarkdownCodeDetector:
    """
    P5: Ported from OpenClaw's code-spans.ts.
    Detects code blocks and inline code to prevent destructive tag stripping.
    """
    def __init__(self):
        self.fences = []
        self.inlines = []

    def build_index(self, text: str):
        self.fences = self._parse_fences(text)
        self.inlines = self._parse_inlines(text, self.fences)

    def is_inside_code(self, index: int) -> bool:
        for span in self.fences:
            if span[0] <= index < span[1]:
                return True
        for span in self.inlines:
            if span[0] <= index < span[1]:
                return True
        return False

    def _parse_fences(self, text: str) -> List[Tuple[int, int]]:
        spans = []
        # Match ```blocks
        matches = re.finditer(r"```[\s\S]*?```", text)
        for m in matches:
            spans.append((m.start(), m.end()))
        
        # Handle unclosed fences at the end
        unclosed = re.search(r"```[a-zA-Z]*\n?[\s\S]*$", text)
        if unclosed and not any(s[0] <= unclosed.start() < s[1] for s in spans):
            spans.append((unclosed.start(), len(text)))
            
        return spans

    def _parse_inlines(self, text: str, fences: List[Tuple[int, int]]) -> List[Tuple[int, int]]:
        spans = []
        # Simple backtick parser, skipping content inside fences
        i = 0
        open_start = -1
        while i < len(text):
            # Skip if inside a fence
            inside_fence = False
            for f in fences:
                if f[0] <= i < f[1]:
                    i = f[1]
                    inside_fence = True
                    break
            if inside_fence: continue

            if text[i] == "`":
                if open_start == -1:
                    open_start = i
                else:
                    spans.append((open_start, i + 1))
                    open_start = -1
            i += 1
            
        if open_start != -1:
            spans.append((open_start, len(text)))
            
        return spans
