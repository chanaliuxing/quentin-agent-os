# meta_agent/safety/checker.py
from __future__ import annotations
from typing import List, Dict
from pathlib import Path

from meta_agent.safety.policy import SafetyPolicy
from meta_agent.safety.result import SafetyCheckResult
from meta_agent.patches.models import PatchProposal


class PatchSafetyChecker:
    def __init__(self, policy: SafetyPolicy | None = None, repo_root: str | Path = "."):
        self.policy = policy or SafetyPolicy.default(repo_root=repo_root)
        self.repo_root = Path(repo_root).resolve()

    def check(self, patch: PatchProposal) -> SafetyCheckResult:
        reasons: List[str] = []
        requires_human = False

        # 1) 文件数量
        files = [Path(f) for f in patch.target_files]
        if len(files) > self.policy.max_files_per_patch:
            reasons.append(
                f"Patch touches {len(files)} files, exceeds max_files_per_patch={self.policy.max_files_per_patch}."
            )
            return SafetyCheckResult(
                allow_apply=False,
                requires_human_review=True,
                reasons=reasons,
                meta={"num_files": len(files)},
            )

        total_added = 0
        total_removed = 0
        high_risk_files: List[str] = []

        # 2) 逐文件检查路径安全 & 高风险标记
        for path in files:
            abs_path = (self.repo_root / path).resolve()

            if not self.policy.is_path_allowed(abs_path):
                reasons.append(f"Path not allowed by policy: {abs_path}")
                return SafetyCheckResult(
                    allow_apply=False,
                    requires_human_review=True,
                    reasons=reasons,
                    meta={},
                )

            if self.policy.is_path_high_risk(abs_path):
                high_risk_files.append(str(abs_path))

            # diff 行数统计（需要 patch.diff_stats 提供；如果没有，可以以后扩展）
            if patch.diff_stats:
                stat = patch.diff_stats.get(str(path), {})
                added = int(stat.get("added", 0))
                removed = int(stat.get("removed", 0))
                total_added += added
                total_removed += removed

        # 3) 整体 diff 行数限制
        total_lines = total_added + total_removed
        if total_lines > self.policy.max_diff_lines:
            reasons.append(
                f"Patch changes too many lines: {total_lines} > max_diff_lines={self.policy.max_diff_lines}."
            )
            requires_human = True

        # 4) 高风险文件 → 强制人工复核
        if high_risk_files:
            reasons.append(
                f"Patch touches high-risk files: {', '.join(high_risk_files)}"
            )
            requires_human = True

        if not reasons:
            # 完全 clean，允许自动 apply
            return SafetyCheckResult(
                allow_apply=True,
                requires_human_review=False,
                reasons=[],
                meta={
                    "total_files": len(files),
                    "total_lines": total_lines,
                },
            )

        # 有理由，但不一定阻塞（比如只要求人工 review）
        return SafetyCheckResult(
            allow_apply=not requires_human,   # v1：如果 requires_human 就不自动 apply
            requires_human_review=requires_human,
            reasons=reasons,
            meta={
                "total_files": len(files),
                "total_lines": total_lines,
                "high_risk_files": high_risk_files,
            },
        )
