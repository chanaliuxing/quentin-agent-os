# meta_agent/tools/web_tools.py
from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Dict, List, Optional
import os

from meta_agent.tools.cli_runner import JsonCliRunner, CliResult


@dataclass
class WebSummary:
    url: str
    title: str
    summary: str


@dataclass
class WebResearchResponse:
    query: str
    summaries: List[WebSummary]
    combined: str
    raw: Dict[str, Any]


class WebResearchBackend:
    def __init__(self, browser_cmd: Optional[str] = None) -> None:
        self.browser_cmd = browser_cmd or os.environ.get("BROWSER_CLI_CMD", "headless-browser-cli")
        self.runner = JsonCliRunner(self.browser_cmd)

    def search_and_summarize(
        self,
        *,
        query: str,
        urls: Optional[List[str]] = None,
        focus: str = "paper",
        notes: str = "",
    ) -> Optional[WebResearchResponse]:
        req = {
            "tool": "web_research",
            "mode": "browser_search",
            "payload": {
                "query": query,
                "urls": urls or [],
                "focus": focus,
                "notes": notes,
            },
        }
        res: CliResult = self.runner.run(req)
        if not res.ok or not res.result:
            return None

        raw = res.result
        summaries_raw = raw.get("summaries") or []
        summaries = [WebSummary(**s) for s in summaries_raw]

        return WebResearchResponse(
            query=query,
            summaries=summaries,
            combined=raw.get("combined", ""),
            raw=raw,
        )
