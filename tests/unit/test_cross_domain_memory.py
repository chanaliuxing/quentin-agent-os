from __future__ import annotations

from pathlib import Path

from quentin.memory.fabric import MemoryFabric
from quentin.memory.models import MemoryQuery, MemoryTier
from quentin.memory.store_sqlite import SqliteMemoryStore


def test_memory_recall_includes_cross_domain(tmp_path: Path) -> None:
    store = SqliteMemoryStore(tmp_path / "mem.db")
    store.init()
    fabric = MemoryFabric(store=store)

    legal = fabric.remember_atomic("legal memo", source="t", tier=MemoryTier.MTS, domain="legal", kind="semantic")
    cross = fabric.remember_atomic("cross memo", source="t", tier=MemoryTier.MTS, domain="cross", kind="semantic")
    _core = fabric.remember_atomic("core memo", source="t", tier=MemoryTier.MTS, domain="core", kind="semantic")

    res = fabric.recall(MemoryQuery(text="memo", tier=MemoryTier.MTS, top_k=10, domain="legal", include_cross_domain=True))
    ids = {r.id for r in res}
    assert legal.id in ids
    assert cross.id in ids


def test_memory_recall_domain_filter_applies_to_vector_only(tmp_path: Path) -> None:
    store = SqliteMemoryStore(tmp_path / "mem.db")
    store.init()
    fabric = MemoryFabric(store=store)

    vec = [1.0, 0.0, 0.0, 0.0]
    legal = fabric.remember_atomic("legal vector memo", source="t", tier=MemoryTier.MTS, domain="legal", vector=vec)
    _noise = fabric.remember_atomic("noise vector memo", source="t", tier=MemoryTier.MTS, domain="finance", vector=vec)

    res = fabric.recall(
        MemoryQuery(
            text="memo",
            vector=vec,
            tier=MemoryTier.MTS,
            top_k=10,
            mode="vector_only",
            domain="legal",
            include_cross_domain=False,
        )
    )
    ids = {r.id for r in res}
    assert legal.id in ids
    assert all((r.domain or "").lower() == "legal" for r in res)


def test_memory_recall_domain_filter_applies_to_hybrid(tmp_path: Path) -> None:
    store = SqliteMemoryStore(tmp_path / "mem.db")
    store.init()
    fabric = MemoryFabric(store=store)

    vec = [0.0, 1.0, 0.0, 0.0]
    legal = fabric.remember_atomic("legal hybrid memo [TOKEN:LEGAL]", source="t", tier=MemoryTier.MTS, domain="legal", vector=vec)
    _cross = fabric.remember_atomic("cross hybrid memo [TOKEN:CROSS]", source="t", tier=MemoryTier.MTS, domain="cross", vector=vec)
    _noise = fabric.remember_atomic("finance hybrid memo [TOKEN:NOISE]", source="t", tier=MemoryTier.MTS, domain="finance", vector=vec)

    res = fabric.recall(
        MemoryQuery(
            text="[TOKEN:LEGAL]",
            vector=vec,
            tier=MemoryTier.MTS,
            top_k=10,
            mode="hybrid",
            domain="legal",
            include_cross_domain=False,
        )
    )
    ids = {r.id for r in res}
    assert legal.id in ids
    assert all((r.domain or "").lower() == "legal" for r in res)
