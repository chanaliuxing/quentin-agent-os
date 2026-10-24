from __future__ import annotations

import re
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional
from quentin.cognitive.perception.base import PerceptionProvider
from quentin.llm.client import call_llm
from meta_agent.tools.web_tools import WebResearchBackend

logger = logging.getLogger(__name__)

class LinkPerceptionProvider(PerceptionProvider):
    """
    P5: Ported from OpenClaw's link understanding.
    Identifies URLs in the task input and provides summaries of their content.
    """
    def __init__(self, model_router: Any):
        self.model_router = model_router
        self.url_pattern = re.compile(r'https?://[^\s<>"]+|www\.[^\s<>"]+')
        # Use existing research backend if available
        self.research_backend = WebResearchBackend()

    def _clean_html(self, html: str) -> str:
        """
        P5: Ported from OpenClaw's readability logic.
        Strips scripts, styles, and tags to get clean content.
        """
        if not html:
            return ""
        
        # 1. Remove scripts and styles
        cleaned = re.sub(r"<(script|style|nav|footer|header)\b[^>]*>[\s\S]*?</\1>", "", html, flags=re.IGNORECASE)
        
        # 2. Extract text from tags
        cleaned = re.sub(r"<[^>]+>", " ", cleaned)
        
        # 3. Normalize whitespace
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        
        # 4. Limit length
        if len(cleaned) > 2000:
            cleaned = cleaned[:1997] + "..."
            
        return cleaned

    def get_perception_data(self, ctx: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extracts and summarizes links from the task input.
        """
        task_input = ctx.get("task_input", "")
        if not task_input:
            return {}

        urls = self.url_pattern.findall(task_input)
        if not urls:
            return {}

        # De-duplicate
        urls = list(dict.fromkeys(urls))
        
        # P5: Implementation - Real URL Summarization
        # Use WebResearchBackend to search and summarize
        outputs = []
        for url in urls[:2]: # Limit to 2 for performance
            try:
                res = self.research_backend.search_and_summarize(
                    query=f"Analyze content of {url}",
                    urls=[url],
                    focus="content_summary",
                    notes="Summarize key info for an AI agent's task context."
                )
                if res and res.combined:
                    # Apply readability cleaning
                    clean_summary = self._clean_html(res.combined)
                    outputs.append({
                        "url": url,
                        "summary": clean_summary
                    })
                else:
                    outputs.append({
                        "url": url,
                        "summary": f"[Unable to fetch content for {url}]"
                    })
            except Exception as e:
                logger.warning(f"LinkPerception: Failed to fetch {url}: {e}")
        
        return {"link_understanding": outputs} if outputs else {}
