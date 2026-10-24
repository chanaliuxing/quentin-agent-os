from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional
import json
import threading

from quentin.runtime.session_write_lock import acquire_session_write_lock


@dataclass
class MemoryItem:
    id: str
    tier: str          # """STS""" | """MTS""" | """LTS"""
    content: str
    meta: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class SimpleMemoryFabric:
    """
    一个极简版本的 Memory Fabric：
      - 只存 JSON 文件
      - 通过 tier 字段区分 STS / MTS / LTS
    """

    def __init__(self, repo_root: str | Path) -> None:
        self.repo_root = Path(repo_root).resolve()
        self.path = self.repo_root / "data" / "memory" / "fabric.jsonl"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    # 真正的实现会有复杂检索，这里只给最小 CRUD 接口

    def append(self, item: MemoryItem) -> None:
        with self._lock:
            lock = acquire_session_write_lock(session_file=self.path)
            try:
                with self.path.open("a", encoding="utf-8") as f:
                    f.write(json.dumps(item.to_dict(), ensure_ascii=False) + "\n")
            finally:
                lock["release"]()

    def list_all(self) -> List[MemoryItem]:
        if not self.path.exists():
            return []
        out: List[MemoryItem] = []
        with self.path.open("r", encoding="utf-8") as f:
            for line in f:
                try:
                    data = json.loads(line)
                    out.append(MemoryItem(**data))
                except Exception:
                    continue
        return out

    # 预留：向量检索/分层迁移等，以后蓝皮书自迭代可以自己来扩展
    
    # Compatibility stub for SleepLoop usage which calls consolidate_from_traces
    def consolidate_from_traces(
        self, 
        traces: List[Dict[str, Any]], 
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        # Minimal stub to prevent crash if using SimpleMemoryFabric with new SleepLoop
        return {"status": "stub_ok", "note": "SimpleMemoryFabric doesn't support consolidation yet."}
