from __future__ import annotations

import json
import time
import logging
from dataclasses import dataclass, asdict, field
from typing import Dict, List, Optional
from pathlib import Path

logger = logging.getLogger(__name__)

import uuid

@dataclass
class SubagentRecord:
    run_id: str
    child_session_id: str
    parent_session_id: str
    task: str
    label: str
    status: str  # pending, completed, failed
    model: str
    cleanup: str  # delete, keep
    created_at: float = field(default_factory=time.time)
    workspace_path: str = "." # P5: Isolation Path

class SubagentRegistry:
    """
    P5: Ported from OpenClaw's subagent-registry.ts.
    Tracks active sub-agent runs with state machine support.
    """
    def __init__(self, repo_root: Path):
        self.repo_root = repo_root
        self.db_path = repo_root / "data" / "subagent_status.json"
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    def _load(self) -> Dict[str, Any]:
        if not self.db_path.exists():
            return {}
        try:
            return json.loads(self.db_path.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _save(self, data: Dict[str, Any]):
        self.db_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    def register(self, record: SubagentRecord):
        # P5: Surgery Sixty-seven - Ephemeral Workspace Isolation (OpenClaw Parity)
        from quentin.infra.isolation.workspace_factory import WorkspaceFactory
        try:
            iso_path = WorkspaceFactory.create_ephemeral_workspace(
                source_root=self.repo_root, 
                session_id=record.child_session_id
            )
            record.workspace_path = str(iso_path)
        except Exception as e:
            logger.error(f"SubagentRegistry: Failed to create isolation: {e}")
            record.workspace_path = str(self.repo_root)

        data = self._load()
        data[record.child_session_id] = asdict(record)
        self._save(data)
        logger.info(f"Registry: Registered subagent {record.child_session_id} at {record.workspace_path}")

    def update_status(self, child_session_id: str, status: str, result_summary: str = ""):
        data = self._load()
        if child_session_id in data:
            data[child_session_id]["status"] = status
            data[child_session_id]["updated_at"] = time.time()
            if result_summary:
                data[child_session_id]["result_summary"] = result_summary[:500]
            self._save(data)
            logger.info(f"Registry: Updated {child_session_id} to {status}")

# Singleton-ish access via Tool instance
