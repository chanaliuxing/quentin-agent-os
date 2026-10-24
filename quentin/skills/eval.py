from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Dict, Any, List

from quentin.skills.models import SkillCandidate


@dataclass
class SkillEvalReport:
    """
    对一个 SkillCandidate 的评估结果。

    - ok       : 是否通过最小要求
    - score    : 0.0 ~ 1.0 的粗略评分
    - issues   : 发现的问题列表
    - warnings : 警告（不致命）
    """
    ok: bool
    score: float
    issues: List[str]
    warnings: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class SkillEvalHarness:
    """
    Skill 评估器 v1（非常简单，但接口清晰、可替换）：

    现在只做：
      - 检查 description / code / tests 是否为空
      - 根据完整度给一个粗略分数

    将来可以替换为：
      - 在 Sandbox 中真正 import/执行代码
      - 对照一组固定样例跑用例
      - 多模型一起做 robustness 检查
    """

    def evaluate_candidate(self, cand: SkillCandidate) -> SkillEvalReport:
        issues: List[str] = []
        warnings: List[str] = []

        score = 1.0

        if not cand.description.strip():
            issues.append("Missing DESCRIPTION.")
            score -= 0.3

        if not cand.code.strip():
            issues.append("Missing CODE implementation.")
            score -= 0.4

        if not cand.tests.strip():
            warnings.append("Missing TESTS description.")
            score -= 0.2

        if score < 0:
            score = 0.0

        ok = score >= 0.5 and not issues  # v1：有致命问题就不通过

        return SkillEvalReport(
            ok=ok,
            score=score,
            issues=issues,
            warnings=warnings,
        )
