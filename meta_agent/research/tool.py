# meta_agent/research/tool.py
from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
import json
import textwrap
import uuid
import os

from meta_agent.llm.cli_clients import CLIModelClient, make_codex_cli_client, make_gemini_cli_client, StubCLIModelClient
from meta_agent.research.headless_browser import HeadlessBrowserClient, default_headless_client
from quentin.traces.core import JsonlTraceRecorder, new_trace_event, TraceEventType
from quentin.security.external_content import wrap_external_content

trace = JsonlTraceRecorder(repo_root=".")


@dataclass
class ResearchChunk:
    source: str
    kind: str
    content: str
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ResearchResult:
    query: str
    focus: str
    merged_summary: str
    chunks: List[ResearchChunk]


class ResearchTool:
    def __init__(
        self,
        codex_client: Optional[CliLLMClient] = None,
        gemini_client: Optional[CliLLMClient] = None,
        headless_client: Optional[HeadlessBrowserClient] = None,
    ) -> None:
        self.codex = codex_client or make_codex_cli_client()
        self.gemini = gemini_client or make_gemini_cli_client()
        self.headless = headless_client or default_headless_client()

    @staticmethod
    def _shield_enabled() -> bool:
        raw = (os.getenv("QUENTIN_EXTERNAL_CONTENT_SHIELD", "true") or "").strip().lower()
        return raw in ("1", "true", "yes", "on")

    def _shield_text(self, text: str, *, source: str, include_warning: bool = True) -> str:
        if not self._shield_enabled():
            return text
        safe_source = source if source in ("email", "webhook", "api", "web_search", "web_fetch", "unknown") else "unknown"
        return wrap_external_content(
            text,
            source=safe_source,  # type: ignore[arg-type]
            include_warning=include_warning,
        )

    def research_gap(self, gap: Any) -> ResearchResult:
        raw_desc = {
            "id": getattr(gap, "id", None), "title": getattr(gap, "title", ""),
            "description": getattr(gap, "description", ""), "category": getattr(gap, "category", "")
        }
        query = json.dumps(raw_desc, ensure_ascii=False)
        trace_id = str(uuid.uuid4())
        trace.record_event(new_trace_event(
            trace_id=trace_id,
            event_type=TraceEventType.TOOL_CALL,
            payload={"action": "research_gap_start", "gap": raw_desc}
        ))

        codex_summary = self._codex_gap_summary(raw_desc)
        search_queries = self._gemini_generate_search_queries(raw_desc, codex_summary)
        web_chunks = [chunk for q in search_queries for chunk in self._run_headless_queries(q, trace_id)]
        
        merged_summary = self._merge_all(raw_desc, codex_summary, search_queries, web_chunks)
        
        chunks = [
            ResearchChunk(source="codex_cli", kind="gap_internal_summary", content=codex_summary, metadata={}),
            ResearchChunk(source="gemini_cli", kind="search_queries", content="\n".join(search_queries), metadata={})
        ] + web_chunks

        result = ResearchResult(query=query, focus="gap", merged_summary=merged_summary, chunks=chunks)
        trace.record_event(new_trace_event(
            trace_id=trace_id,
            event_type=TraceEventType.TOOL_CALL,
            payload={"action": "research_gap_done", "gap_id": raw_desc.get("id"), "num_chunks": len(chunks)}
        ))
        return result

    def research_web(self, query: str) -> ResearchResult:
        """
        Performs a general web research using the headless browser.
        """
        trace_id = str(uuid.uuid4())
        trace.record_event(new_trace_event(
            trace_id=trace_id,
            event_type=TraceEventType.TOOL_CALL,
            payload={"action": "research_web_start", "query": query}
        ))
        
        web_content_json = self.headless.run("web_research", query)
        web_chunks_raw = json.loads(web_content_json)
        
        chunks = []
        for item in web_chunks_raw:
            chunks.append(ResearchChunk(
                source="web_research_script",
                kind="web_page_content",
                content=self._shield_text(str(item.get("content", "") or ""), source="web_fetch", include_warning=True),
                metadata={"url": item.get("url", ""), "query": query}
            ))

        merged_summary = self._merge_all_web_content(query, chunks)

        result = ResearchResult(query=query, focus="web", merged_summary=merged_summary, chunks=chunks)
        trace.record_event(new_trace_event(
            trace_id=trace_id,
            event_type=TraceEventType.TOOL_CALL,
            payload={"action": "research_web_done", "query": query, "num_chunks": len(chunks)}
        ))
        return result


    def _codex_gap_summary(self, gap_desc: Dict[str, Any]) -> str:
        prompt = f"Summarize the core need, impacted modules, and potential difficulties of the following blueprint gap:\n{json.dumps(gap_desc, indent=2)}"
        return self.codex.generate(system="You are a laconic system architect.", user=prompt).strip()

    def _gemini_generate_search_queries(self, gap_desc: Dict[str, Any], codex_summary: str) -> List[str]:
        prompt = f"Generate 3-6 English search queries for an academic search engine based on the following gap summary.\nGap: {json.dumps(gap_desc)}\nSummary: {codex_summary}\nOutput one query per line."
        raw = self.gemini.generate(system="You generate search queries from technical descriptions.", user=prompt)
        return [ln.strip() for ln in raw.splitlines() if ln.strip()][:6]

    def _run_headless_queries(self, query: str, trace_id: str) -> List[ResearchChunk]:
        chunks: List[ResearchChunk] = []
        for provider in ["chatgpt", "gemini"]:
            try:
                ans = self.headless.run(provider, query)
                chunks.append(
                    ResearchChunk(
                        source=f"{provider}_web",
                        kind="web_answer",
                        content=self._shield_text(ans, source="web_fetch", include_warning=True),
                        metadata={"query": query},
                    )
                )
            except Exception as e:
                trace.record_event(new_trace_event(
                    trace_id=trace_id,
                    event_type=TraceEventType.ERROR,
                    payload={"action": f"research_headless_{provider}_error", "query": query, "error": repr(e)}
                ))
        return chunks

    def _merge_all(self, raw_desc: Dict, codex_summary: str, search_queries: List, web_chunks: List) -> str:
        web_texts = "\n\n".join(f"[{ch.source} for query '{ch.metadata.get('query')}']:\n{ch.content}" for ch in web_chunks)
        prompt = f"Synthesize the following information into a structured research report for the gap described below.\n\n# Gap\n{json.dumps(raw_desc, indent=2)}\n\n# Internal Summary\n{codex_summary}\n\n# Web Research\n{web_texts}"
        return self.codex.generate(system="You are a research director summarizing findings.", user=prompt).strip()

    def _merge_all_web_content(self, query: str, web_chunks: List[ResearchChunk]) -> str:
        web_texts = "\n\n".join(f"[URL: {ch.metadata.get('url', 'N/A')}]\n{ch.content}" for ch in web_chunks)
        prompt = f"You are a research assistant. Summarize the following web content related to the query: '{query}'.\n\n# Web Content\n{web_texts}"
        return self.codex.generate(system="You summarize web content.", user=prompt).strip()
