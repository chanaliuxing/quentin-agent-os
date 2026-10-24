# meta_agent/blueprint/version_store.py
from __future__ import annotations
from quentin.utils.time import now_iso, now_utc
from dataclasses import dataclass, asdict
from typing import Dict, Any, List, Optional
from pathlib import Path
import datetime as dt
import json
import difflib
import uuid

from meta_agent.blueprint.patch_types import BlueprintPatch, make_blueprint_patch_id
from quentin.traces.core import JsonlTraceRecorder

trace = JsonlTraceRecorder(repo_root=".")

@dataclass
class BlueprintVersionRecord:
    version_id: str; created_at: str; patch_id: str; source: str; author: str
    target_section: str; risk_level: str; blueprint_snapshot_path: str
    diff_path: str; summary: str; metadata: Dict[str, Any]

class BlueprintVersionStore:
    def __init__(self, root_dir: str | Path = "data/blueprint/versions"):
        self.root_dir = Path(root_dir)
        self.snapshots_dir = self.root_dir / "snapshots"
        self.diffs_dir = self.root_dir / "diffs"
        self.index_path = self.root_dir / "index.jsonl"
        self.snapshots_dir.mkdir(parents=True, exist_ok=True)
        self.diffs_dir.mkdir(parents=True, exist_ok=True)

    def create_version_from_patch(self, patch: BlueprintPatch, old_text: str, new_text: str, summary: Optional[str] = None) -> BlueprintVersionRecord:
        now = now_utc()
        version_id = f"v{now.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:4].upper()}"
        
        snapshot_path = self.snapshots_dir / f"{version_id}.md"
        snapshot_path.write_text(new_text, encoding="utf-8")
        diff_text = "".join(difflib.unified_diff(old_text.splitlines(keepends=True), new_text.splitlines(keepends=True), fromfile=f"before_{version_id}", tofile=f"after_{version_id}"))
        diff_path = self.diffs_dir / f"{version_id}.diff"
        diff_path.write_text(diff_text, encoding="utf-8")

        record = BlueprintVersionRecord(
            version_id=version_id, created_at=now.isoformat(), patch_id=patch.id,
            source=patch.source, author=patch.author, target_section=patch.target_section,
            risk_level=patch.risk_level, blueprint_snapshot_path=str(snapshot_path),
            diff_path=str(diff_path), summary=summary or patch.rationale[:200],
            metadata={"change_type": patch.change_type, "patch_metadata": patch.metadata}
        )
        self._append_index_record(record)
        return record

    def rollback_to(self, version_id: str, blueprint_path: Path, reason: str = "", author: str = "human_rollback") -> bool:
        rec = self.get_version(version_id)
        if not rec: return False
        
        snapshot_text = self.load_snapshot_text(version_id)
        if snapshot_text is None: return False

        old_text = blueprint_path.read_text(encoding="utf-8") if blueprint_path.exists() else ""
        blueprint_path.write_text(snapshot_text, encoding="utf-8")

        rollback_patch = BlueprintPatch(
            id=f"ROLLBACK-{make_blueprint_patch_id()}", created_at=now_iso(),
            source="rollback_tool", author=author, target_section=f"ROLLBACK_TO::{version_id}",
            change_type="rollback_to_version", new_content=snapshot_text[:500],
            rationale=reason or f"Rollback to version {version_id}", risk_level="medium",
            metadata={"rollback_to_version": version_id}, status="applied",
        )
        
        self.create_version_from_patch(patch=rollback_patch, old_text=old_text, new_text=snapshot_text)
        trace.record_event(event_type="blueprint_rollback_done", trace_id=version_id, payload={"rollback_to": version_id})
        return True

    def list_versions(self, limit: Optional[int] = None) -> List[BlueprintVersionRecord]:
        if not self.index_path.exists(): return []
        records = []
        with self.index_path.open("r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    try: records.append(BlueprintVersionRecord(**json.loads(line)))
                    except: continue
        records.sort(key=lambda r: r.created_at, reverse=True)
        return records[:limit] if limit else records

    def get_version(self, version_id: str) -> Optional[BlueprintVersionRecord]:
        return next((r for r in self.list_versions() if r.version_id == version_id), None)

    def load_diff_text(self, version_id: str) -> Optional[str]:
        if rec := self.get_version(version_id): return Path(rec.diff_path).read_text(encoding="utf-8")
        return None

    def load_snapshot_text(self, version_id: str) -> Optional[str]:
        if rec := self.get_version(version_id): return Path(rec.blueprint_snapshot_path).read_text(encoding="utf-8")
        return None

    def _append_index_record(self, record: BlueprintVersionRecord) -> None:
        with self.index_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(asdict(record)) + "\n")
