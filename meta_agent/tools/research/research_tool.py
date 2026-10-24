# meta_agent/tools/research/research_tool.py
from __future__ import annotations
import os
from typing import List, Optional


_ENABLED = os.getenv("ENABLE_RESEARCH_TOOL", "0").lower() in {"1", "true", "yes"}

if _ENABLED:
    # Optional heavy dependency path (network/browser). Disabled by default.
    from meta_agent.tools.browser.playwright_tool import PlaywrightBrowserTool
    from meta_agent.tools.browser.base import WebSearchResult

    def chat(system: str, user: str) -> str:
        # Best-effort: use the canonical LLM client if present.
        try:
            from quentin.llm.client import call_llm
        except Exception:
            query_line = next((line for line in user.splitlines() if line.strip()), "")
            return f"[research_tool] LLM client unavailable. Query: {query_line}"

        model_name = os.getenv("LLM_MODEL")
        if not model_name:
             raise ValueError("Environment variable LLM_MODEL is not set.")
        return call_llm(model_name, system_prompt=system, user_prompt=user, action_metadata={"topic": "research_tool"})


class ResearchTool:
    def __init__(self):
        if not _ENABLED:
            raise RuntimeError("ResearchTool is disabled. Set ENABLE_RESEARCH_TOOL=1 to enable.")
        self.browser = PlaywrightBrowserTool(headless=True)

    async def search_and_summarize(self, query: str, max_pages: int = 3) -> str:
        """
        Uses the browser tool to search a query, fetches the top results,
        and uses an LLM to summarize the findings.
        """
        results: List[WebSearchResult] = await self.browser.search(query)
        texts = []
        for r in results[:max_pages]:
            try:
                text = await self.browser.fetch_page_text(r.url)
                texts.append(f"=== {r.title} ({r.url}) ===\n{text[:4000]}")  # Limit length per page
            except Exception as e:
                print(f"Failed to fetch or process URL {r.url}: {e}")
                texts.append(f"=== {r.title} ({r.url}) ===\n[Failed to fetch content]")

        merged = "\n\n".join(texts)
        
        summary_prompt = f"以下是一些网页内容（可能有噪音），请围绕查询：{query}，总结关键结论和可用方法。\n\n{merged}"
        
        summary = chat(
            system="你是一个研究助手，用于总结网页内容。",
            user=summary_prompt,
        )
        return summary


def is_enabled() -> bool:
    return _ENABLED
