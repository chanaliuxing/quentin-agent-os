from __future__ import annotations

from pathlib import Path

from quentin.retrieval.codebase_index import extract_code_chunks


def test_extract_code_chunks_basic(tmp_path: Path) -> None:
    repo_root = tmp_path
    pkg = repo_root / "quentin"
    pkg.mkdir(parents=True, exist_ok=True)
    (pkg / "__init__.py").write_text("", encoding="utf-8")

    src = (
        '"""module doc"""\n\n'
        "def foo(a, b, *, c=None):\n"
        '    """Foo does a thing."""\n'
        "    return a + b\n\n"
        "class Bar:\n"
        '    """Bar docs."""\n\n'
        "    def baz(self, x):\n"
        '        """Baz docs."""\n'
        "        return x\n"
    )
    path = pkg / "sample.py"
    path.write_text(src, encoding="utf-8")

    chunks = extract_code_chunks(repo_root=repo_root, file_path=path, include_methods=True)
    assert len(chunks) >= 3

    ids = {c.chunk_id for c in chunks}
    assert len(ids) == len(chunks)

    # Must include metadata keys used by self-programming skill context lookup.
    for ch in chunks:
        assert "file_path" in ch.metadata
        assert "fully_qualified_name" in ch.metadata
        assert "docstring" in ch.metadata

