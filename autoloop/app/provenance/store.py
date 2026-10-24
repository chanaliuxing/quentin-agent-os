from __future__ import annotations

import json
from collections import deque
from pathlib import Path
from uuid import uuid4

from app.config import settings
from app.models import ProvenanceEdge, ProvenanceEvent, ProvenanceRelation


class ProvenanceStore:
    def __init__(self, base_dir: Path | None = None) -> None:
        self.base_dir = base_dir or (settings.runtime_dir / "provenance")

    def _events_path(self, run_id: str) -> Path:
        return self.base_dir / run_id / "events.jsonl"

    def _edges_path(self, run_id: str) -> Path:
        return self.base_dir / run_id / "edges.jsonl"

    def record_event(
        self,
        *,
        run_id: str,
        phase_id: str,
        artifact_id: str,
        event_type: str,
        payload: dict,
    ) -> ProvenanceEvent:
        event = ProvenanceEvent(
            event_id=f"evt_{uuid4().hex[:12]}",
            run_id=run_id,
            phase_id=phase_id,
            artifact_id=artifact_id,
            event_type=event_type,
            payload=payload,
        )
        self._append_jsonl(self._events_path(run_id), event.model_dump(mode="json"))
        return event

    def record_edge(
        self,
        *,
        run_id: str,
        src_artifact_id: str,
        dst_artifact_id: str,
        relation: ProvenanceRelation,
    ) -> ProvenanceEdge:
        edge = ProvenanceEdge(
            src_artifact_id=src_artifact_id,
            dst_artifact_id=dst_artifact_id,
            relation=relation,
        )
        self._append_jsonl(self._edges_path(run_id), edge.model_dump(mode="json"))
        return edge

    def find_upstream_artifacts(self, *, run_id: str, artifact_id: str) -> list[str]:
        edges = self._load_edges(run_id)
        upstream: list[str] = []
        queue: deque[str] = deque([artifact_id])
        seen: set[str] = {artifact_id}
        while queue:
            current = queue.popleft()
            for edge in edges:
                if edge.dst_artifact_id != current:
                    continue
                candidate = edge.src_artifact_id
                if candidate in seen:
                    continue
                seen.add(candidate)
                upstream.append(candidate)
                queue.append(candidate)
        return upstream

    def _append_jsonl(self, path: Path, payload: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False) + "\n")

    def _load_edges(self, run_id: str) -> list[ProvenanceEdge]:
        path = self._edges_path(run_id)
        if not path.exists():
            return []
        edges: list[ProvenanceEdge] = []
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                edges.append(ProvenanceEdge.model_validate(json.loads(line)))
        return edges
