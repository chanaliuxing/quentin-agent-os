from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from quentin.tools.execution_parity import web_fetch_tool


def _ctx(tmp_path: Path):
    return SimpleNamespace(metadata={"repo_root": str(tmp_path.resolve())})


def test_web_fetch_blocks_localhost_ssrf(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    out = web_fetch_tool({"url": "http://localhost:8080/secret"}, ctx)
    assert out["status"] == "error"
    assert "blocked" in str(out.get("error") or "").lower()


def test_web_fetch_offline_html_extracts_text_and_applies_site_patch(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    url = "https://github.com/org/repo/issues/1"
    html = "<html><body><header>Top</header><nav>Side</nav><main><article><h1>Issue</h1><p>Body</p></article></main><footer>Foot</footer></body></html>"
    out = web_fetch_tool({"url": url, "html": html, "extract_mode": "text", "max_chars": 2000, "apply_site_patch": True}, ctx)
    assert out["status"] == "ok"
    assert "Issue" in out["content"]
    assert "Body" in out["content"]
    # Ensure header/footer noise removed by patch+strip.
    assert "Top" not in out["content"]
    assert "Foot" not in out["content"]
    assert isinstance(out.get("wrapped_content"), str) and out["wrapped_content"]


def test_web_fetch_markdown_mode_produces_links(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    out = web_fetch_tool(
        {
            "url": "https://example.com/a",
            "html": "<html><head><title>T</title></head><body><h1>Hello</h1><p>See <a href=\"https://x.com\">X</a></p></body></html>",
            "extract_mode": "markdown",
            "max_chars": 2000,
            "apply_site_patch": False,
        },
        ctx,
    )
    assert out["status"] == "ok"
    assert "Hello" in out["content"]
    assert "[X](https://x.com)" in out["content"]
