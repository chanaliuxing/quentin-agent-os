from __future__ import annotations

from pathlib import Path

from quentin.memory.fabric import MemoryFabric
from quentin.memory.models import MemoryTier


class _DummyEmbeddingClient:
    def embed_text(self, text: str):
        n = float(len(text))
        return [n, n + 1.0]

    @property
    def dim(self) -> int:
        return 2


def test_sync_memory_files_indexes_then_skips_unchanged(tmp_path: Path, monkeypatch) -> None:
    mem_dir = tmp_path / "memory"
    mem_dir.mkdir(parents=True, exist_ok=True)
    (mem_dir / "a.md").write_text("# A\nhello\n", encoding="utf-8")
    monkeypatch.setenv("QUENTIN_MEMORY_EMBED_CACHE_PATH", str(tmp_path / "memory_embed_cache.sqlite"))
    fabric = MemoryFabric(repo_root=tmp_path, db_path=":memory:", embedding_client=_DummyEmbeddingClient())

    r1 = fabric.sync_memory_files(workspace_dir=tmp_path, force=True, tier=MemoryTier.MTS)
    assert r1["indexed"] >= 1
    assert r1["errors"] == 0

    r2 = fabric.sync_memory_files(workspace_dir=tmp_path, force=False, tier=MemoryTier.MTS)
    assert r2["indexed"] == 0
    assert r2["skipped"] >= 1


def test_sync_memory_files_cleans_stale_deleted_files(tmp_path: Path, monkeypatch) -> None:
    mem_dir = tmp_path / "memory"
    mem_dir.mkdir(parents=True, exist_ok=True)
    p = mem_dir / "gone.md"
    p.write_text("# G\nbye\n", encoding="utf-8")
    monkeypatch.setenv("QUENTIN_MEMORY_EMBED_CACHE_PATH", str(tmp_path / "memory_embed_cache.sqlite"))
    fabric = MemoryFabric(repo_root=tmp_path, db_path=":memory:", embedding_client=_DummyEmbeddingClient())

    r1 = fabric.sync_memory_files(workspace_dir=tmp_path, force=True, source_prefix="memory_file")
    assert r1["indexed"] >= 1

    p.unlink()
    r2 = fabric.sync_memory_files(workspace_dir=tmp_path, force=False, source_prefix="memory_file")
    assert r2["stale_deleted"] >= 1

    src = f"memory_file:{str(p.resolve())}"
    row = fabric.store.conn.execute("SELECT COUNT(*) AS c FROM memories WHERE source = ?", (src,)).fetchone()
    assert int(row["c"]) == 0


def test_sync_memory_files_respects_dirty_files_filter(tmp_path: Path, monkeypatch) -> None:
    mem_dir = tmp_path / "memory"
    mem_dir.mkdir(parents=True, exist_ok=True)
    a = mem_dir / "a.md"
    b = mem_dir / "b.md"
    a.write_text("# A\nv1\n", encoding="utf-8")
    b.write_text("# B\nv1\n", encoding="utf-8")
    monkeypatch.setenv("QUENTIN_MEMORY_EMBED_CACHE_PATH", str(tmp_path / "memory_embed_cache.sqlite"))
    fabric = MemoryFabric(repo_root=tmp_path, db_path=":memory:", embedding_client=_DummyEmbeddingClient())
    fabric.sync_memory_files(workspace_dir=tmp_path, force=True, source_prefix="memory_file")

    a.write_text("# A\nv2\n", encoding="utf-8")
    b.write_text("# B\nv2\n", encoding="utf-8")
    r = fabric.sync_memory_files(
        workspace_dir=tmp_path,
        force=False,
        dirty_files={str(a)},
        source_prefix="memory_file",
    )
    assert r["index_all"] is False
    assert r["indexed"] >= 1
