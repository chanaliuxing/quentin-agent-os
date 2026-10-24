# meta_agent/tools/browser/base.py
from __future__ import annotations
from typing import List, Optional
from dataclasses import dataclass
from abc import ABC, abstractmethod


@dataclass
class WebSearchResult:
    url: str
    title: str
    snippet: str
    full_text: Optional[str] = None


class BrowserTool(ABC):
    @abstractmethod
    async def search(self, query: str) -> List[WebSearchResult]:
        raise RuntimeError("BrowserTool is abstract; provide a concrete implementation.")

    @abstractmethod
    async def fetch_page_text(self, url: str) -> str:
        raise RuntimeError("BrowserTool is abstract; provide a concrete implementation.")
