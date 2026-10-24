# quentin/self_improvement/design.py
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Dict, Any, Optional, List

from quentin.self_improvement.schemas import ImprovementTask
from quentin.agents.multi_llm_council import (
    MultiLLMCouncil,
    CouncilResult,
)
from quentin.blueprint.spec import BlueprintSpec
from quentin.self_improvement.manager import SelfImprovementManager
from quentin.agents.multi_llm_roles import MeetingType
from quentin.utils.time import now_iso


logger = logging.getLogger(__name__)


@dataclass
class DesignDraft:
    """
    针对某个 ImprovementTask，由多 AI 会议生成的“设计草案”。

    当前版本主要是保存：
    - 会议类型
    - 多个 proposal 的原文
    - 主持人合并后的综合方案
    - 风险复审意见
    后续可以再细化解析成更结构化的 plan/steps。
    """
    draft_id: str                # 例如 f"{task_id}:v1"
    task_id: str
    capability: str
    requirement_id: Optional[str]

    meeting_type: str            # planning / debugging / patch_review / reflection ...
    created_at: str = field(default_factory=lambda: now_iso())

    merged_answer: str = ""      # 主持人综合方案（CouncilResult.merged_answer）
    risks: str = ""              # 风险复审意见（CouncilResult.risks）

    council_meta: Dict[str, Any] = field(default_factory=dict)
    raw_proposals: List[Dict[str, Any]] = field(default_factory=list)

    blueprint_snapshot: Dict[str, Any] = field(default_factory=dict)
    task_snapshot: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DesignDraft":
        return cls(**data)


class FileBackedDesignStore:
    """
    简单的设计草案存储：JSON 文件 {draft_id: draft_dict}
    """

    def __init__(self, path: str | Path = "data/improvement_designs.json") -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._loaded = False
        self._cache: Dict[str, Dict[str, Any]] = {}

    def _load(self) -> None:
        if self._loaded:
            return
        if self.path.exists():
            try:
                with self.path.open("r", encoding="utf-8") as f:
                    self._cache = json.load(f)
            except Exception as e:
                logger.exception("Failed to load design store from %s", self.path)
                self._cache = {}
        else:
            self._cache = {}
        self._loaded = True

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("w", encoding="utf-8") as f:
            json.dump(self._cache, f, ensure_ascii=False, indent=2)

    def get_all(self) -> Dict[str, Dict[str, Any]]:
        self._load()
        return dict(self._cache)

    def list_for_task(self, task_id: str) -> List[DesignDraft]:
        self._load()
        drafts = [
            DesignDraft.from_dict(d)
            for d in self._cache.values()
            if d.get("task_id") == task_id
        ]
        # 按创建时间排序
        drafts.sort(key=lambda d: d.created_at)
        return drafts


class ImprovementDesignPlanner:
    """
    负责：
    - 从 ImprovementTask 中选一个任务
    - 拉取蓝皮书 spec 和 gap 信息
    - 调用 MultiLLMCouncil 开会
    - 生成 DesignDraft 存盘

    这一层相当于“研究/设计前置”，后面自编程引擎可以拿 DesignDraft 来写 patch。
    """

    def __init__(
        self,
        blueprint_path: str = "blueprint/meta_agent_v3.yaml",
        council: Optional[MultiLLMCouncil] = None,
        task_store_path: str | Path = "data/improvement_tasks.json",
        design_store: Optional[FileBackedDesignStore] = None,
    ) -> None:
        self.blueprint_path = blueprint_path
        self.blueprint = BlueprintSpec.load_from_file(blueprint_path)
        self.council = council or MultiLLMCouncil()
        self.si_manager = SelfImprovementManager(
            blueprint_path=blueprint_path,
        )
        self.design_store = design_store or FileBackedDesignStore()

    # ------------ 对外主入口：为单个任务生成设计草案 ------------

    def propose_design_for_task(
        self,
        task_id: str,
        meeting_type: MeetingType = "planning",
    ) -> DesignDraft:
        """
        针对指定的 ImprovementTask 召开一次“多 AI 设计会”，产出一个 DesignDraft。
        """
        task = self._get_task_by_id(task_id)
        if not task:
            raise ValueError(f"Task not found: {task_id}")

        # 构造会议问题 + 上下文
        problem, context = self._build_problem_and_context(task)

        # 调用多 AI 会议
        council_result: CouncilResult = self.council.deliberate(
            meeting_type=meeting_type,
            problem=problem,
            context=context,
        )

        # 把结果落为 DesignDraft
        draft_id = self._make_draft_id(task, suffix=f"{meeting_type}:{len(self.design_store.get_all())+1}")

        draft = DesignDraft(
            draft_id=draft_id,
            task_id=task.task_id,
            capability=task.capability,
            requirement_id=task.requirement_id,
            meeting_type=meeting_type,
            merged_answer=council_result.merged_answer,
            risks=council_result.risks,
            council_meta=council_result.notes,
            raw_proposals=[
                {
                    "role_id": p.role_id,
                    "role_name": p.role_name,
                    "model": p.model,
                    "content": p.content,
                }
                for p in council_result.proposals
            ],
            blueprint_snapshot=self._snapshot_capability(task.capability),
            task_snapshot=task.to_dict(),
        )

        self.design_store.upsert(draft)
        logger.info("DesignDraft created: %s for task %s", draft.draft_id, task.task_id)

        return draft

    # ------------ 辅助：选任务 / 构造会议问题 / 截图蓝皮书 ------------

    def _get_task_by_id(self, task_id: str) -> Optional[ImprovementTask]:
        tasks = self.si_manager.list_tasks()
        for t in tasks:
            if t.task_id == task_id:
                return t
        return None

    @staticmethod
    def _make_draft_id(task: ImprovementTask, suffix: Optional[str] = None) -> str:
        base = f"{task.task_id}"
        if suffix:
            return f"{base}::{suffix}"
        return base

    def _snapshot_capability(self, capability_name: str) -> Dict[str, Any]:
        cap = self.blueprint.capabilities.get(capability_name)
        if not cap:
            return {}
        return {
            "name": cap.name,
            "layer": cap.layer,
            "category": cap.category,
            "description": cap.description,
            "components": cap.components,
            "requirements": [
                {
                    "id": r.id,
                    "type": r.type,
                    "description": r.description,
                }
                for r in cap.requirements
            ],
            "definition_of_done": cap.definition_of_done,
        }

    def _build_problem_and_context(self, task: ImprovementTask) -> tuple[str, Dict[str, Any]]:
        """
        给 AI 会议的“问题 + 上下文”。
        目标：让它们知道：
        - 蓝皮书对这项能力的要求
        - 当前 repo 的 gap（来自 task.meta.components）
        - 我们希望输出什么样的设计结果
        """
        cap_spec = self.blueprint.capabilities.get(task.capability)

        problem = f"""我们需要为 Meta-Agent v3 蓝皮书中的能力 `{task.capability}` 设计一个落地实现方案。

具体目标：
- 当前状态：{task.overall_status}
- 对应蓝皮书 requirement: {task.requirement_id or "（无具体 requirement id，按能力整体设计）"}
- 输出：一份面向 Python 代码库的工程设计草案（包括模块结构、类/函数职责、关键数据结构、与现有组件的集成方式）。

请你们作为多位 AI 角色，从工程落地角度给出可执行的设计。
"""

        context: Dict[str, Any] = {
            "task": task.to_dict(),
            "capability_spec": self._snapshot_capability(task.capability),
            "gap_components": task.meta.get("components", []),
            "blueprint_id": self.blueprint.id,
            "blueprint_version": self.blueprint.version,
        }

        return problem, context
