from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional
import os

from meta_agent.tools.web_tools import WebResearchBackend as ToolsWebResearchBackend
from meta_agent.tools.web_tools import WebResearchResponse


@dataclass(frozen=True)
class WebResearchTask:
    query: str
    urls: Optional[List[str]] = None
    focus: str = "paper"
    notes: str = ""


class WebResearchBackend:
    """
    Thin wrapper around `meta_agent.tools.web_tools.WebResearchBackend`.

    Safety/zero-config defaults:
    - Disabled unless `META_AGENT_ENABLE_WEB_RESEARCH=1`.
    - When disabled, `run()` returns None (no network / no CLI dependency).
    """

    def __init__(
        self,
        *,
        enabled: Optional[bool] = None,
        browser_cmd: Optional[str] = None,
    ) -> None:
        env_enabled = os.environ.get("META_AGENT_ENABLE_WEB_RESEARCH", "").strip().lower() in ("1", "true", "yes", "on")
        self.enabled = env_enabled if enabled is None else bool(enabled)
        self._backend = ToolsWebResearchBackend(browser_cmd=browser_cmd)

    def run(self, task: WebResearchTask) -> Optional[WebResearchResponse]:
        if not self.enabled:
            return None
        return self._backend.search_and_summarize(
            query=task.query,
            urls=task.urls,
            focus=task.focus,
            notes=task.notes,
        )


class WebResearchWorker:
    def __init__(self, backend: Optional[WebResearchBackend] = None) -> None:
        self.backend = backend or WebResearchBackend()

    def run(self, task: WebResearchTask) -> Optional[WebResearchResponse]:
        return self.backend.run(task)


__all__ = [
    "WebResearchBackend",
    "WebResearchTask",
    "WebResearchWorker",
]
