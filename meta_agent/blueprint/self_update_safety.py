# meta_agent/blueprint/self_update_safety.py
from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Set

from meta_agent.blueprint.patch_models import BlueprintPatchProposal, BlueprintPatchOperation


@dataclass
class BlueprintPatchSafetyResult:
    is_blocked: bool
    reasons: List[str] = field(default_factory=list)


class BlueprintPatchSafetyChecker:
    """
    对蓝皮书级别的补丁做安全检查：
    - 不允许删除/降权安全关键条款
    - 控制每个 proposal 的 operation 数量上限
    """

    def __init__(
        self,
        max_operations_per_proposal: int = 10,
        safety_critical_prefixes: List[str] = None,
    ) -> None:
        self.max_operations_per_proposal = max_operations_per_proposal
        # 假设所有 id 以 "SEC-" 开头的是安全关键条款，你可以换成真实规则
        self.safety_critical_prefixes: List[str] = safety_critical_prefixes or ["SEC-"]

    def check_proposal(self, proposal: BlueprintPatchProposal) -> BlueprintPatchSafetyResult:
        reasons: List[str] = []

        if len(proposal.operations) > self.max_operations_per_proposal:
            reasons.append(
                f"too_many_operations({len(proposal.operations)} > {self.max_operations_per_proposal})"
            )

        # 安全相关条款 ID 集
        safety_targets: Set[str] = set(
            op.target_clause_id
            for op in proposal.operations
            if self._is_safety_critical_clause(op.target_clause_id)
        )

        for op in proposal.operations:
            if op.op_type in ("remove_clause", "deprecate_clause"):
                if self._is_safety_critical_clause(op.target_clause_id):
                    reasons.append(
                        f"cannot_{op.op_type}_safety_critical_clause({op.target_clause_id})"
                    )

            if op.op_type == "update_priority" and self._is_safety_critical_clause(op.target_clause_id):
                # 如果 new_value 比 old_value 小，判为风险
                try:
                    old_p = int(op.old_value) if op.old_value is not None else None
                    new_p = int(op.new_value) if op.new_value is not None else None
                    if old_p is not None and new_p is not None and new_p < old_p:
                        reasons.append(
                            f"cannot_lower_priority_for_safety_critical_clause({op.target_clause_id})"
                        )
                except Exception:
                    # 转换失败就保守一点
                    reasons.append(
                        f"update_priority_on_safety_critical_clause_needs_manual_review({op.target_clause_id})"
                    )

        return BlueprintPatchSafetyResult(
            is_blocked=bool(reasons),
            reasons=reasons,
        )

    def _is_safety_critical_clause(self, clause_id: str) -> bool:
        return any(clause_id.startswith(p) for p in self.safety_critical_prefixes)
