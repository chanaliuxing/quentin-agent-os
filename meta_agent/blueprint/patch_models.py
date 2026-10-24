# meta_agent/blueprint/patch_models.py
from __future__ import annotations
from quentin.utils.time import now_iso, now_utc
from dataclasses import dataclass, field
from typing import List, Literal, Optional, Dict, Any
import uuid
import datetime as dt


# 一条蓝皮书上的“原子修改”
# 比如：调整优先级、修改 status、调整条款描述、修改 acceptance_criteria 等
OperationType = Literal[
    "update_priority",
    "update_status",
    "edit_description",
    "edit_acceptance_criteria",
    "deprecate_clause",
    "split_clause",
    "merge_clauses",
    "add_clause",
    "remove_clause",
]


@dataclass
class BlueprintPatchOperation:
    op_type: OperationType
    target_clause_id: str

    # 通用字段：更新前后值，可以只用其中一个
    old_value: Optional[Any] = None
    new_value: Optional[Any] = None

    # 对于复杂操作（split/merge/add），可以放在 extra 中
    extra: Dict[str, Any] = field(default_factory=dict)


@dataclass
class BlueprintPatchProposal:
    """
    蓝皮书 Patch 提案：由 BlueprintSelfUpdateEngine + LLM 生成，
    由 BlueprintPatchEvaluator / GovernanceCouncil / SafeApplier 处理。
    """

    id: str
    title: str
    description: str

    created_at: str
    author: str

    # 操作列表
    operations: List[BlueprintPatchOperation] = field(default_factory=list)

    # 来源信息：比如来自 research / metrics / immune 等
    origin: str = "blueprint_self_update_v1"

    # 关联signal，方便追踪
    related_issues: List[str] = field(default_factory=list)  # eg: immune_case_ids / gap_ids
    related_metrics: Dict[str, Any] = field(default_factory=dict)

    # 风险标记：给治理层用
    risk_level: Literal["low", "medium", "high"] = "medium"
    requires_human_approval: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "created_at": self.created_at,
            "author": self.author,
            "operations": [
                {
                    "op_type": op.op_type,
                    "target_clause_id": op.target_clause_id,
                    "old_value": op.old_value,
                    "new_value": op.new_value,
                    "extra": op.extra,
                }
                for op in self.operations
            ],
            "origin": self.origin,
            "related_issues": self.related_issues,
            "related_metrics": self.related_metrics,
            "risk_level": self.risk_level,
            "requires_human_approval": self.requires_human_approval,
        }

    @classmethod
    def new(
        cls,
        title: str,
        description: str,
        operations: List[BlueprintPatchOperation],
        author: str = "meta_agent_blueprint_loop",
        origin: str = "blueprint_self_update_v1",
    ) -> "BlueprintPatchProposal":
        return cls(
            id=f"BP-PATCH-{uuid.uuid4().hex[:8]}",
            title=title,
            description=description,
            created_at=now_iso(),
            author=author,
            operations=operations,
            origin=origin,
        )
