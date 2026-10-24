from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from quentin.tools.execution_parity import web_search_tool


def _ctx(tmp_path: Path):
    return SimpleNamespace(metadata={"repo_root": str(tmp_path.resolve())})


def test_web_search_empty_query_safe(tmp_path: Path) -> None:
    out = web_search_tool({"query": "", "max_results": 5}, _ctx(tmp_path))
    assert out["status"] == "ok"
    assert out["results"] == []
    assert out["mode"] == "empty_query"


def test_web_search_local_corpus_ranking(tmp_path: Path) -> None:
    corpus = [
        {"title": "OpenAI API Quickstart", "url": "https://example.com/a", "snippet": "Use OpenAI API in Python."},
        {"title": "Cron Notes", "url": "https://example.com/b", "snippet": "Cron syntax."},
    ]
    out = web_search_tool({"query": "openai quickstart", "max_results": 3, "corpus": corpus}, _ctx(tmp_path))
    assert out["status"] == "ok"
    rows = list(out.get("results") or [])
    assert rows
    assert "openai" in str(rows[0].get("title") or "").lower()
    assert "content" in rows[0]


def test_web_search_mock_items_normalization(tmp_path: Path) -> None:
    mock_items = [
        {"title": "T1", "link": "https://x", "text": "S1"},
        {"title": "T2", "url": "https://y", "snippet": "S2"},
    ]
    out = web_search_tool({"query": "x", "max_results": 2, "mock_items": mock_items}, _ctx(tmp_path))
    assert out["status"] == "ok"
    assert out["mode"] == "mock_items"
    rows = list(out.get("results") or [])
    assert len(rows) == 2
    assert rows[0]["url"] == "https://x"

