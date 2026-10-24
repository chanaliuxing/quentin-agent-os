import json
from pathlib import Path

from scripts.benchmark_websearch_tool import (
    BenchmarkConfig,
    _compare,
    run_benchmark,
)


def _write_tool(tmp_path: Path, *, valid_logic: bool = True) -> Path:
    tool_dir = tmp_path / "extensions" / "tools" / "web_search"
    tool_dir.mkdir(parents=True, exist_ok=True)
    (tool_dir / "manifest.yaml").write_text(
        "\n".join(
            [
                "name: WebSearchTool",
                "id: web_search_tool_id",
                "description: test",
                "entrypoint: logic.py",
                "output_trust: untrusted",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    if valid_logic:
        logic = """
def perform_search(query: str, max_results: int = 5):
    if not query:
        return []
    import requests
    r = requests.get(f"https://example.com?q={query}&num={max_results}")
    if r.status_code != 200:
        return []
    items = r.json().get("items", [])[:max_results]
    out = []
    for item in items:
        out.append({"title": item.get("title",""), "url": item.get("link",""), "snippet": item.get("snippet","")})
    return out
"""
    else:
        logic = "def broken(:\n    pass\n"
    (tool_dir / "logic.py").write_text(logic, encoding="utf-8")
    return tool_dir


def test_run_benchmark_valid_tool_scores_pass(tmp_path: Path) -> None:
    tool_dir = _write_tool(tmp_path, valid_logic=True)
    report = run_benchmark(tool_dir, config=BenchmarkConfig(pass_score=60))
    assert report["score"]["passed"] is True
    assert report["score"]["total"] >= 60


def test_run_benchmark_import_fail_is_critical(tmp_path: Path) -> None:
    tool_dir = _write_tool(tmp_path, valid_logic=False)
    report = run_benchmark(tool_dir, config=BenchmarkConfig(pass_score=10))
    assert report["score"]["critical_fail"] is True
    assert report["score"]["passed"] is False


def test_compare_delta() -> None:
    cur = {"score": {"total": 82.0}}
    prev = {"score": {"total": 79.5}}
    cmp = _compare(cur, prev)
    assert cmp["baseline_found"] is True
    assert cmp["delta_total"] == 2.5
    assert cmp["improved"] is True
