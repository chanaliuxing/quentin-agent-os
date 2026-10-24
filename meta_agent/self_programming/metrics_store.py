from __future__ import annotations
from quentin.utils.time import now_iso, now_utc, normalize_to_utc_iso

import json
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Protocol, TypedDict, Literal


class RunRecord(TypedDict, total=False):
    task_id: str
    status: Literal["approved", "rejected", "test_fail", "error"]
    timestamp: datetime
    commit_hash: Optional[str]
    branch_name: Optional[str]
    raw_test_output: Optional[str]
    metrics: Dict[str, Any]
    task_payload: Dict[str, Any]


class MetricsStoreProtocol(Protocol):
    def log_run(self, record: RunRecord) -> None:
        ...

    def get_runs_by_status(self, status: str, limit: int = 10) -> List[RunRecord]:
        ...


@dataclass
class _SerializableRunRecord:
    task_id: str
    status: str
    timestamp: str
    commit_hash: Optional[str]
    branch_name: Optional[str]
    raw_test_output: Optional[str]
    metrics: Dict[str, Any]
    task_payload: Dict[str, Any]


class JsonlMetricsStore(MetricsStoreProtocol):
    """
    Minimal JSONL-backed metrics store for self-programming runs.

    Each line is a serialized RunRecord; retrieval filters by status.
    """

    def __init__(self, *, repo_root: str | Path = ".", filename: str = "data/metrics/runs.jsonl") -> None:
        self.repo_root = Path(repo_root).resolve()
        self.path = self.repo_root / filename
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def log_run(self, record: RunRecord) -> None:
        serializable = _SerializableRunRecord(
            task_id=record["task_id"],
            status=record["status"],
            timestamp=record["timestamp"].isoformat(),
            commit_hash=record.get("commit_hash"),
            branch_name=record.get("branch_name"),
            raw_test_output=record.get("raw_test_output"),
            metrics=record.get("metrics", {}),
            task_payload=record.get("task_payload", {}),
        )
        line = json.dumps(asdict(serializable), ensure_ascii=False)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as f:
            f.write(line + "\n")

    def get_runs_by_status(self, status: str, limit: int = 10) -> List[RunRecord]:
        if not self.path.exists():
            return []

        matches: List[RunRecord] = []
        try:
            with self.path.open("r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        obj = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if str(obj.get("status")) != status:
                        continue
                    ts_raw = obj.get("timestamp")
                    timestamp = (
                        datetime.fromisoformat(normalize_to_utc_iso(ts_raw))
                        if isinstance(ts_raw, str)
                        else now_utc()
                    )
                    matches.append(
                        {
                            "task_id": obj.get("task_id", ""),
                            "status": obj.get("status", ""),
                            "timestamp": timestamp,
                            "commit_hash": obj.get("commit_hash"),
                            "branch_name": obj.get("branch_name"),
                            "raw_test_output": obj.get("raw_test_output"),
                            "metrics": obj.get("metrics", {}) or {},
                            "task_payload": obj.get("task_payload", {}) or {},
                        }
                    )
        except Exception:
            return []

        matches.sort(key=lambda r: r["timestamp"], reverse=True)
        return matches[:limit]
