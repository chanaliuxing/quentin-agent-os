from __future__ import annotations

from dataclasses import dataclass, asdict, field
from typing import Any, Dict, List, Optional
from quentin.utils.time import now_iso as utc_now_iso


@dataclass
class PatchTarget:
    """
    Patch 的作用对象：
      - 只允许修改 /mutable/ 下被标记为 auto_updatable 的模块
      - path 一律用 repo_root 的相对路径
    """
    kind: str                     # "module" | "skill" | "config" 等
    path: str                     # 例: "mutable/skills/desktop_clicker.py"
    symbol: Optional[str] = None  # 可选: 具体函数/类名
    constraints: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class PatchTestPlan:
    """
    Patch 对应的测试计划：
      - 用于描述需要跑哪些测试（单测/回归/静态分析等）
      - 真实执行逻辑可以后面再补
    """
    unit_tests: List[str] = field(default_factory=list)       # 例如 pytest -k "test_xxx"
    regression_scenarios: List[str] = field(default_factory=list)
    static_checks: List[str] = field(default_factory=list)    # 例如 "mypy", "ruff"
    fuzzing: List[str] = field(default_factory=list)          # 预留

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class PatchProposal:
    """
    自编程引擎生成的“补丁提案”，不会直接改代码，只作为候选。
    """

    proposal_id: str
    created_at: str
    created_by: str              # "self_programming_engine" | "human" 等
    target: PatchTarget
    rationale: str               # 为什么要这么改（来自 LLM/ResearchLayer）
    # patch_content 可以有多种形式：
    #   - unified_diff: 纯 diff
    #   - full_file: 整个文件替换
    #   - snippet: 局部函数/类定义
    patch_type: str              # "unified_diff" | "full_file" | "snippet"
    patch_content: str
    test_plan: PatchTestPlan
    meta: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        # 手动展开嵌套 dataclass，方便 JSON 序列化
        d["target"] = self.target.to_dict()
        d["test_plan"] = self.test_plan.to_dict()
        return d


@dataclass
class PatchExecutionResult:
    """
    在 Sandbox / CI 中跑 patch 相关测试的结果（占位）
    """

    proposal_id: str
    tests_run: List[str]
    tests_passed: List[str]
    tests_failed: List[str]
    static_issues: List[str]
    # 指标变化，例如成功率/延迟/成本的变化（由 Eval Harness 写入）
    metrics_delta: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class PatchReport:
    """
    综合报告：Patch 从建议 -> 测试 -> 是否推荐接受
    """

    proposal: PatchProposal
    execution_result: Optional[PatchExecutionResult]
    recommended_action: str     # "accept" | "reject" | "needs_review"
    reasoning: str              # 对这个结论的解释

    def to_dict(self) -> Dict[str, Any]:
        d = {
            "proposal": self.proposal.to_dict(),
            "execution_result": self.execution_result.to_dict() if self.execution_result else None,
            "recommended_action": self.recommended_action,
            "reasoning": self.reasoning,
        }
        return d

PatchCandidate = PatchProposal
PatchTestResult = PatchExecutionResult

def now_iso() -> str:
    return utc_now_iso()
