from pathlib import Path

from meta_agent.self_programming.infra.context_extractor import build_context_chunks, summarize_file_signatures


def test_summarize_file_signatures_basic(tmp_path: Path) -> None:
    code = """
class Foo:
    def method(self, x):
        pass

def bar(y, z):
    return y + z
"""
    p = tmp_path / "sample.py"
    p.write_text(code, encoding="utf-8")
    summary = summarize_file_signatures(str(p))
    assert "class Foo" in summary
    assert "def bar" in summary


def test_build_context_chunks_includes_target_full_text(tmp_path: Path) -> None:
    target = tmp_path / "target.py"
    target.write_text("def target_fn():\n    return 1\n", encoding="utf-8")

    other = tmp_path / "other.py"
    other.write_text("def other_fn(x):\n    return x\n", encoding="utf-8")

    chunks = build_context_chunks(str(target), [str(target), str(other)])
    paths = [c.file_path for c in chunks]
    assert str(target) in paths
    assert str(other) in paths

    target_content = next(c.content for c in chunks if c.file_path == str(target))
    assert "target_fn" in target_content

    other_content = next(c.content for c in chunks if c.file_path == str(other))
    assert "other_fn" in other_content and "return" not in other_content
