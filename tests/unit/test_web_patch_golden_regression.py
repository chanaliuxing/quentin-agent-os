from __future__ import annotations

from quentin.tools.execution_parity import web_readability_tool


def test_web_patch_golden_regression_sites() -> None:
    cases = [
        (
            "https://github.com/org/repo/issues/1",
            "<html><body><header>h</header><main><article><h1>Issue</h1><p>Body</p></article></main><footer>f</footer></body></html>",
            ["Issue", "Body"],
            [" h ", " f "],
        ),
        (
            "https://dev.to/a/b",
            "<html><body><aside class=\"crayons-layout__sidebar-left\">left</aside><article><h1>Dev</h1><p>Body</p></article><div id=\"comments-container\">comments</div></body></html>",
            ["Dev", "Body"],
            ["comments"],
        ),
        (
            "https://stackoverflow.com/questions/1/x",
            "<html><body><aside class=\"left-sidebar\">left</aside><article><h1>Q</h1><p>A</p></article><div id=\"comments\">noise</div></body></html>",
            ["Q", "A"],
            ["noise"],
        ),
        (
            "https://medium.com/@x/y",
            "<html><body><div class=\"metabar\">meta</div><article><h1>Story</h1><p>Body</p></article><section aria-label=\"Responses\">r</section></body></html>",
            ["Story", "Body"],
            [" meta ", " r "],
        ),
    ]
    for url, html, keep_tokens, drop_tokens in cases:
        out = web_readability_tool({"url": url, "html": html}, None)
        assert out["status"] == "ok"
        content = str(out.get("content") or "")
        for t in keep_tokens:
            assert t in content
        for t in drop_tokens:
            assert t not in content
        dm = dict(out.get("diff_metrics") or {})
        assert int(dm.get("source_chars") or 0) > 0
        assert int(dm.get("clean_chars") or 0) >= 1
