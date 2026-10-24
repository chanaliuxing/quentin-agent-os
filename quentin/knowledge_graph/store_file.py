from __future__ import annotations

import json
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, List, Optional

from quentin.runtime.session_write_lock import acquire_session_write_lock

from .schema import KGEdge, KGNode, NodeType, EdgeType


class FileGraphStore:
    """
    Minimal file-backed graph store.

    Data model:
    {
      "nodes": { "<node_id>": {..KGNode..}, ... },
      "node_index": { "<node_type>:<ref_id>": "<node_id>", ... },
      "edges": { "<edge_id>": {..KGEdge..}, ... },
      "edge_index": { "<src>:<dst>:<type>": "<edge_id>", ... }
    }
    """

    def __init__(self, *, path: str | Path = "data/kg_store.json") -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def init_schema(self) -> None:
        if self.path.exists():
            return
        self._save({"nodes": {}, "node_index": {}, "edges": {}, "edge_index": {}})

    def upsert_node(self, node: KGNode) -> str:
        data = self._load()
        nodes = data.setdefault("nodes", {})
        idx = data.setdefault("node_index", {})
        key = f"{node.node_type.value}:{node.ref_id}"
        existing_id = idx.get(key)
        if existing_id and existing_id in nodes:
            # merge metadata; keep title if new title provided
            existing = nodes[existing_id]
            existing_meta = dict(existing.get("metadata") or {})
            existing_meta.update(node.metadata or {})
            existing["metadata"] = existing_meta
            if node.title:
                existing["title"] = node.title
            existing["updated_at"] = time.time()
            nodes[existing_id] = existing
            self._save(data)
            return existing_id

        nodes[node.node_id] = {
            "node_id": node.node_id,
            "node_type": node.node_type.value,
            "ref_id": node.ref_id,
            "title": node.title,
            "metadata": node.metadata or {},
            "created_at": getattr(node, "created_at", None) or time.time(),
            "updated_at": time.time(),
        }
        idx[key] = node.node_id
        self._save(data)
        return node.node_id

    def upsert_edge(self, edge: KGEdge):
        data = self._load()
        edges = data.setdefault("edges", {})
        idx = data.setdefault("edge_index", {})
        key = f"{edge.src_node_id}:{edge.dst_node_id}:{edge.edge_type.value}"
        existing_id = idx.get(key)
        if existing_id and existing_id in edges:
            existing = edges[existing_id]
            existing["weight"] = edge.weight
            existing_ev = dict(existing.get("evidence") or {})
            existing_ev.update(edge.evidence or {})
            existing["evidence"] = existing_ev
            existing["updated_at"] = time.time()
            edges[existing_id] = existing
            self._save(data)
            return existing_id

        edges[edge.edge_id] = {
            "edge_id": edge.edge_id,
            "src_node_id": edge.src_node_id,
            "dst_node_id": edge.dst_node_id,
            "edge_type": edge.edge_type.value,
            "weight": edge.weight,
            "evidence": edge.evidence or {},
            "created_at": getattr(edge, "created_at", None) or time.time(),
            "updated_at": time.time(),
        }
        idx[key] = edge.edge_id
        self._save(data)
        return edge.edge_id

    def get_node_by_ref(self, node_type: NodeType, ref_id: str) -> Optional[KGNode]:
        data = self._load()
        idx = data.get("node_index") or {}
        nodes = data.get("nodes") or {}
        node_id = idx.get(f"{node_type.value}:{ref_id}")
        if not node_id:
            return None
        raw = nodes.get(node_id)
        if not isinstance(raw, dict):
            return None
        return self._raw_to_node(raw)

    def get_node_by_id(self, node_id: str) -> Optional[KGNode]:
        data = self._load()
        nodes = data.get("nodes") or {}
        raw = nodes.get(node_id)
        if not isinstance(raw, dict):
            return None
        return self._raw_to_node(raw)

    def _raw_to_node(self, raw: Dict[str, Any]) -> KGNode:
        return KGNode(
            node_id=raw["node_id"],
            node_type=NodeType(raw["node_type"]),
            ref_id=raw["ref_id"],
            title=raw.get("title") or "",
            metadata=raw.get("metadata") or {},
            created_at=raw.get("created_at"),
        )

    def get_neighbors(self, node_id: str, edge_type: Optional[EdgeType] = None, direction: str = "out") -> List[Dict]:
        data = self._load()
        nodes = data.get("nodes") or {}
        edges = data.get("edges") or {}
        out: List[Dict[str, Any]] = []
        for e in edges.values():
            if not isinstance(e, dict):
                continue
            if edge_type and e.get("edge_type") != edge_type.value:
                continue
            if direction == "out":
                if e.get("src_node_id") != node_id:
                    continue
                other_id = e.get("dst_node_id")
            else:
                if e.get("dst_node_id") != node_id:
                    continue
                other_id = e.get("src_node_id")
            other = nodes.get(other_id) or {}
            out.append(
                {
                    "edge_id": e.get("edge_id"),
                    "src_node_id": e.get("src_node_id"),
                    "dst_node_id": e.get("dst_node_id"),
                    "edge_type": e.get("edge_type"),
                    "weight": e.get("weight"),
                    "node_id": other.get("node_id"),
                    "node_type": other.get("node_type"),
                    "ref_id": other.get("ref_id"),
                    "title": other.get("title"),
                }
            )
        return out

    def _load(self) -> Dict[str, Any]:
        if not self.path.exists():
            return {"nodes": {}, "node_index": {}, "edges": {}, "edge_index": {}}
        try:
            return json.loads(self.path.read_text(encoding="utf-8") or "{}")
        except Exception:
            return {"nodes": {}, "node_index": {}, "edges": {}, "edge_index": {}}

    def _save(self, data: Dict[str, Any]) -> None:
        lock = acquire_session_write_lock(session_file=self.path)
        try:
            self.path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        finally:
            lock["release"]()

