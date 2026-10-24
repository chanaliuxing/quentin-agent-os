from __future__ import annotations

import os
import time
from pathlib import Path

from quentin.memory.fabric import MemoryFabric
from quentin.memory.models import MemoryQuery


def main() -> int:
    # Expected env:
    # - QUENTIN_MEMORY_STORE=champion
    # - PG_HOST/PG_* or PG_DSN
    # - QDRANT_URL
    repo_root = Path(__file__).resolve().parent.parent

    os.environ.setdefault("QUENTIN_MEMORY_STORE", "champion")
    os.environ.setdefault("QUENTIN_MEMORY_NAMESPACE", "smoke")
    os.environ.setdefault("PG_HOST", "localhost")
    os.environ.setdefault("PG_PORT", "55432")
    os.environ.setdefault("PG_USER", "postgres")
    os.environ.setdefault("PG_PASSWORD", "postgres")
    os.environ.setdefault("PG_DB", "quentin_memory")
    os.environ.setdefault("QDRANT_URL", "http://localhost:6333")
    os.environ.setdefault("MEM_EMBED_PROVIDER", "disabled")
    os.environ.setdefault("MEM_EMBED_DIM", "16")

    fabric = MemoryFabric(repo_root=repo_root)
    dim = int(os.environ["MEM_EMBED_DIM"])

    v1 = [1.0] + [0.0] * (dim - 1)
    v2 = [0.0, 1.0] + [0.0] * (dim - 2)
    r1 = fabric.remember_atomic(
        content="alpha memory about payments incident [SMOKE:001]",
        source="smoke",
        domain="payments",
        vector=v1,
        metadata={"domain": "payments"},
    )
    r2 = fabric.remember_atomic(
        content="beta memory about auth bug [SMOKE:002]",
        source="smoke",
        domain="auth",
        vector=v2,
        metadata={"domain": "auth"},
    )

    # Qdrant indexing is async by default; give it a brief moment.
    time.sleep(0.2)

    out = fabric.recall(MemoryQuery(vector=v1, top_k=5, mode="vector_only", debug=True))
    print("smoke_recall_n", len(out))
    print("smoke_expected_id", r1.id)
    if not out:
        return 2
    hit = any(r.id == r1.id for r in out)
    print("smoke_hit", hit)
    return 0 if hit else 3


if __name__ == "__main__":
    raise SystemExit(main())
