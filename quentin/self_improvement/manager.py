from __future__ import annotations

import json
import logging
from dataclasses import asdict
from pathlib import Path
from typing import Dict, Any, List, Optional

from quentin.self_improvement.schemas import ImprovementTask

logger = logging.getLogger(__name__)


class SelfImprovementManager:
    """
    自我改进总调度（v1）：
    - 从 BlueprintGapTracker 的结果生成/更新 ImprovementTask
    - 提供任务列表给其他模块使用
    """

    def __init__(self, path: str | Path = "data/improvement_tasks.json") -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._loaded = False
        self._tasks: Dict[str, ImprovementTask] = {}

    def _load(self) -> None:
        if self._loaded:
            return
        if self.path.exists():
            try:
                raw = json.loads(self.path.read_text(encoding="utf-8") or "{}")
                self._tasks = {
                    tid: ImprovementTask.from_dict(d)
                    for tid, d in raw.items()
                }
            except Exception:
                logger.exception("Failed to load improvement tasks from %s", self.path)
                self._tasks = {}
        else:
            self._tasks = {}
        self._loaded = True

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        raw = {tid: asdict(t) for tid, t in self._tasks.items()}
        self.path.write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")

    # --- 原来就有的接口（示意） ---
    def list_tasks(self) -> List[ImprovementTask]:
        self._load()
        return list(self._tasks.values())

    # --- 新增：按 task_id 取任务 ---
    def get_task(self, task_id: str) -> Optional[ImprovementTask]:
        self._load()
        return self._tasks.get(task_id)

    # --- 新增：插入或更新任务 ---
    def upsert_task(self, task: ImprovementTask) -> None:
        """
        如果 task_id 已存在则覆盖，否则新增。
        """
        self._load()
        self._tasks[task.task_id] = task
        self._save()
