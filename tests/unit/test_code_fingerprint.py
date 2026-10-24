from __future__ import annotations

from pathlib import Path

from quentin.memory.code_fingerprint import (
    build_code_function_fingerprints,
    build_function_fingerprint_hash,
)
from quentin.memory.fabric import MemoryFabric


class _DummyEmbeddingClient:
    def embed_text(self, text: str):
        n = float(len(text))
        return [n, n + 1.0]

    @property
    def dim(self) -> int:
        return 2


def test_build_code_function_fingerprints_python() -> None:
    content = """
def a(x):
    return x + 1

async def b(y):
    return y
"""
    fps = build_code_function_fingerprints(file_path="x.py", content=content)
    names = [str(x.get("name")) for x in fps]
    assert "a" in names
    assert "b" in names
    assert all(x.get("fingerprint") for x in fps)
    assert any(x.get("semantic_fingerprint") for x in fps)


def test_function_fingerprint_hash_is_position_insensitive() -> None:
    c1 = "def a():\n    return 1\n\ndef b():\n    return 2\n"
    c2 = "def b():\n    return 2\n\ndef a():\n    return 1\n"
    f1 = build_code_function_fingerprints(file_path="x.py", content=c1)
    f2 = build_code_function_fingerprints(file_path="x.py", content=c2)
    assert build_function_fingerprint_hash(f1, position_insensitive=True) == build_function_fingerprint_hash(
        f2, position_insensitive=True
    )


def test_python_class_method_qualname_included() -> None:
    content = """
class A:
    def m(self):
        return 1
"""
    fps = build_code_function_fingerprints(file_path="x.py", content=content)
    assert any(str(x.get("qualname")) == "A.m" for x in fps)


def test_remember_file_includes_function_fingerprint_metadata(tmp_path: Path, monkeypatch) -> None:
    f = tmp_path / "m.py"
    f.write_text("def alpha():\n    return 1\n", encoding="utf-8")
    monkeypatch.setenv("QUENTIN_MEMORY_EMBED_CACHE_PATH", str(tmp_path / "memory_embed_cache.sqlite"))
    fabric = MemoryFabric(db_path=":memory:", embedding_client=_DummyEmbeddingClient())
    recs = fabric.remember_file(f)
    assert recs
    meta = recs[0].metadata
    assert "function_fingerprints" in meta
    assert "function_fingerprint_hash" in meta


def test_remember_file_skips_when_function_fingerprint_unchanged(tmp_path: Path, monkeypatch) -> None:
    f = tmp_path / "k.py"
    f.write_text("def alpha():\n    return 1\n\ndef beta():\n    return 2\n", encoding="utf-8")
    monkeypatch.setenv("QUENTIN_MEMORY_EMBED_CACHE_PATH", str(tmp_path / "memory_embed_cache.sqlite"))
    fabric = MemoryFabric(db_path=":memory:", embedding_client=_DummyEmbeddingClient())

    first = fabric.remember_file(f)
    assert first
    second = fabric.remember_file(f)
    assert second == []

    # Reorder functions only: semantic bodies unchanged => still skip.
    f.write_text("def beta():\n    return 2\n\ndef alpha():\n    return 1\n", encoding="utf-8")
    third = fabric.remember_file(f)
    assert third == []
