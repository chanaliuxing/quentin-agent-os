from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional

from quentin.cognitive.context_snapshots.base import ContextSnapshotRegistry, SnapshotBlock


@dataclass
class _Provider:
    pid: str
    prio: int
    text: str

    @property
    def id(self) -> str:
        return self.pid

    @property
    def priority(self) -> int:
        return self.prio

    def collect(self, repo_root: Path, context: Dict[str, object]) -> Optional[SnapshotBlock]:
        _ = (repo_root, context)
        return SnapshotBlock(id=self.pid, title=self.pid, content=self.text, size_bytes=len(self.text.encode("utf-8")))


def test_context_snapshot_registry_respects_total_budget(tmp_path) -> None:
    reg = ContextSnapshotRegistry()
    reg.register(_Provider("p1", 100, "A" * 60))
    reg.register(_Provider("p2", 90, "B" * 60))

    blocks = reg.collect_all(repo_root=tmp_path, context={}, max_total_bytes=100)
    assert [b.id for b in blocks] == ["p1"]

