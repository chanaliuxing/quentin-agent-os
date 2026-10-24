from __future__ import annotations

from meta_agent.research.tool import ResearchTool


class _StubClient:
    def generate(self, system: str, user: str) -> str:  # noqa: ARG002
        return "ok"


class _StubHeadless:
    def run(self, provider: str, query: str, max_tokens: int = 2000) -> str:  # noqa: ARG002
        return "web content"


def test_research_tool_shield_enabled(monkeypatch) -> None:
    monkeypatch.setenv("QUENTIN_EXTERNAL_CONTENT_SHIELD", "true")
    tool = ResearchTool(
        codex_client=_StubClient(),
        gemini_client=_StubClient(),
        headless_client=_StubHeadless(),
    )
    out = tool._shield_text("hello", source="web_fetch", include_warning=True)
    assert "EXTERNAL_UNTRUSTED_CONTENT" in out


def test_research_tool_shield_disabled(monkeypatch) -> None:
    monkeypatch.setenv("QUENTIN_EXTERNAL_CONTENT_SHIELD", "false")
    tool = ResearchTool(
        codex_client=_StubClient(),
        gemini_client=_StubClient(),
        headless_client=_StubHeadless(),
    )
    out = tool._shield_text("hello", source="web_fetch", include_warning=True)
    assert out == "hello"
