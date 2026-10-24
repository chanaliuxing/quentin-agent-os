# quentin/immune/store.py
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Optional
from pathlib import Path
from datetime import datetime, UTC
import json
import uuid
import logging

from quentin.immune.anomaly import AnomalySignal
from quentin.runtime.session_write_lock import acquire_session_write_lock

logger = logging.getLogger(__name__)


@dataclass
class ImmuneCase:
    """
    一个完整的“免疫案例”：一次异常周期的上下文。
    """
    case_id: str
    goal_summary: Dict[str, Any]
    anomaly: Dict[str, Any]
    metrics: Dict[str, Any]
    recent_traces: List[Dict[str, Any]]
    created_at: str = datetime.now(UTC).isoformat()
    tags: List[str] = None

    def _safe_serialize(self, obj: Any) -> Any:
        # Phase 5.4: Handle non-serializable objects recursively
        from datetime import datetime
        if isinstance(obj, datetime):
            return obj.isoformat()
        if isinstance(obj, dict):
            return {str(k): self._safe_serialize(v) for k, v in obj.items() if k != "cancel_token"}
        if isinstance(obj, list):
            return [self._safe_serialize(v) for v in obj]
        if hasattr(obj, "to_dict"):
            try: return self._safe_serialize(obj.to_dict())
            except: pass
        if hasattr(obj, "__dict__"):
            return {k: self._safe_serialize(v) for k, v in obj.__dict__.items() if k != "cancel_token"}
        return str(obj) if not isinstance(obj, (int, float, bool, type(None))) else obj

    def to_dict(self) -> Dict[str, Any]:
        return {
            "case_id": self.case_id,
            "goal_summary": self._safe_serialize(self.goal_summary),
            "anomaly": self._safe_serialize(self.anomaly),
            "metrics": self._safe_serialize(self.metrics),
            "recent_traces": self._safe_serialize(self.recent_traces),
            "created_at": self.created_at,
            "tags": self.tags or []
        }


class ImmuneCaseStore:
    def __init__(self, *, repo_root: str | Path = ".") -> None:
        self.repo_root = Path(repo_root).resolve()
        self.base_dir = self.repo_root / "data" / "immune_cases"
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.jsonl_path = self.base_dir / "immune_cases.jsonl"

    def append_case(
        self,
        *,
        goal: Any,
        anomaly: AnomalySignal,
        metrics: Dict[str, Any],
        recent_traces: List[Dict[str, Any]],
    ) -> ImmuneCase:
        case_id = uuid.uuid4().hex
        goal_summary = self._summarize_goal(goal)
        case = ImmuneCase(
            case_id=case_id,
            goal_summary=goal_summary,
            anomaly=anomaly.to_dict(),
            metrics=metrics,
            recent_traces=recent_traces,
            tags=[anomaly.anomaly_type, anomaly.severity],
        )
        
        # Double-safe dump with default handler
        def _default(o):
            from datetime import datetime
            if isinstance(o, datetime): return o.isoformat()
            return str(o)

        line = json.dumps(case.to_dict(), ensure_ascii=False, default=_default)
        try:
            lock = acquire_session_write_lock(session_file=self.jsonl_path)
            try:
                with self.jsonl_path.open("a", encoding="utf-8") as f:
                    f.write(line + "\n")
            finally:
                lock["release"]()
        except Exception:
            logger.exception("ImmuneCaseStore: failed to append case to %s", self.jsonl_path)

        # 也可以每 case 单独存一份，便于调试
        try:
            per_file = self.base_dir / f"{case_id}.json"
            per_file.write_text(
                json.dumps(case.to_dict(), ensure_ascii=False, indent=2, default=_default),
                encoding="utf-8",
            )
        except Exception:
            logger.exception("ImmuneCaseStore: failed to write per-case json file for %s", case_id)

        return case

    def list_cases(self, limit: int = 100) -> List[ImmuneCase]:
        cases: List[ImmuneCase] = []
        if not self.jsonl_path.exists():
            return cases
        try:
            with self.jsonl_path.open("r", encoding="utf-8") as f:
                for _ in range(limit):
                    line = f.readline()
                    if not line:
                        break
                    obj = json.loads(line)
                    cases.append(
                        ImmuneCase(
                            case_id=obj.get("case_id", ""),
                            goal_summary=obj.get("goal_summary", {{}}),
                            anomaly=obj.get("anomaly", {{}}),
                            metrics=obj.get("metrics", {{}}),
                            recent_traces=obj.get("recent_traces", []),
                            created_at=obj.get("created_at", ""),
                            tags=obj.get("tags", []),
                        )
                    )
        except Exception:
            logger.exception("ImmuneCaseStore: failed to read cases from %s", self.jsonl_path)
        return cases

    def _summarize_goal(self, goal: Any) -> Dict[str, Any]:
        if isinstance(goal, dict):
            g = goal
        else:
            g = {}
            for attr in ("id", "title", "description", "domain", "metadata"):
                if hasattr(goal, attr):
                    g[attr] = getattr(goal, attr)
        # 可以做进一步裁剪
        return g
