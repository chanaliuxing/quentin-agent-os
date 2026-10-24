from __future__ import annotations

from typing import List, Optional
from pathlib import Path
import json
import logging

from quentin.trace.spec import ExecutionTrace, StepTrace
from quentin.runtime.session_write_lock import acquire_session_write_lock

logger = logging.getLogger(__name__)


class TraceStore:
    """
    v1: 简单 JSONL 存储，用于：
    - ImmuneLoop 检查最近一段时间的 trace
    - SleepLoop 做记忆巩固与技能挖掘
    """

    def __init__(self, *, repo_root: str | Path = ".") -> None:
        self.repo_root = Path(repo_root).resolve()
        self.base_dir = self.repo_root / "data" / "traces"
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.jsonl_path = self.base_dir / "traces.jsonl"

    def append(self, trace: ExecutionTrace) -> None:
        line = json.dumps(trace.to_dict(), ensure_ascii=False)
        try:
            lock = acquire_session_write_lock(session_file=self.jsonl_path)
            try:
                with self.jsonl_path.open("a", encoding="utf-8") as f:
                    f.write(line + "\n")
            finally:
                lock["release"]()
        except Exception:
            logger.exception("TraceStore: failed to append trace")

    def load_recent(self, limit: int = 200) -> List[ExecutionTrace]:
        """
        v1: 粗暴从尾部往前读 limit 行。
        后续可按时间索引优化。
        """
        traces: List[ExecutionTrace] = []
        if not self.jsonl_path.exists():
            return traces

        try:
            with self.jsonl_path.open("r", encoding="utf-8") as f:
                lines = f.readlines()[-limit:]
        except Exception:
            logger.exception("TraceStore: failed to read traces")
            return traces

        for line in lines:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                steps = [StepTrace(**s) for s in obj.get("steps", [])]
                tr = ExecutionTrace(
                    trace_id=obj["trace_id"],
                    task_id=obj.get("task_id", ""),
                    domain=obj.get("domain", "general"),
                    status=obj.get("status", "unknown"),
                    steps=steps,
                    created_at=obj.get("created_at", ""),
                    execution_summary=obj.get("execution_summary", {{}}),
                    lessons_learned=obj.get("lessons_learned", {{}}),
                    top_level_metrics=obj.get("top_level_metrics", {{}}),
                    meta=obj.get("meta", {{}})
                )
                traces.append(tr)
            except Exception:
                logger.exception("TraceStore: failed to parse trace line")

        return traces
