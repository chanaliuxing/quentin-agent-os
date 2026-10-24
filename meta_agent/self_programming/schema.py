from dataclasses import dataclass
from typing import List, Optional, Literal, Dict, Any


# === 基础 patch 单元：给 FilePatcher 用 ===

@dataclass
class FileModification:
    """
    单文件修改（最终交给 FilePatcher 执行）。
    """
    file_path: str
    action: Literal["create", "modify", "delete"]
    original_snippet: Optional[str]  # modify 时用于定位
    new_content: str                 # 替换后的内容（或新文件全量）


@dataclass
class CodePatchSet:
    """
    一次自编程生成的一组文件修改。
    """
    task_id: str
    files: List[FileModification]
    summary: str


# === 编程任务 & 团队各角色的输入输出 ===

@dataclass
class ProgrammingTask:
    """
    自编程任务：通常由 BlueprintGap / Bug 抽象而来。
    """
    task_id: str
    origin: Literal["blueprint_gap", "bugfix", "refactor", "experiment"]
    description: str                 # 人 & AI 可读描述
    repo_root: str                   # 仓库根目录
    related_files: List[str]         # Architect 可见文件范围
    context_summary: str             # 蓝皮书 gap / 失败 trace 等
    constraints: Dict[str, Any]      # 安全/风格/领域约束
    acceptance_criteria: List[str]   # 验收标准（明文化）
    environment: str = "sandbox"



@dataclass
class DevPlan:
    """
    Architect 输出的开发计划。
    """
    task_id: str
    task_summary: str
    impact_analysis: Dict[str, Any]
    work_items: List[Dict[str, Any]]     # 每个 work item 包含 file_path / goal 等
    test_plan: Dict[str, Any]            # 需要哪些测试，放 Tester 那边解释
    notes: str = ""


@dataclass
class TestPlan:
    task_id: str
    framework: Literal["pytest", "unittest", "none"]
    tests: List[Dict[str, Any]]          # {id, file, description, type,...}


@dataclass
class TestReport:
    task_id: str
    overall_status: Literal["passed", "failed", "partial", "skipped"]
    results: List[Dict[str, Any]]        # 每个测试的结果
    raw_output: str


@dataclass
class ReviewDecision:
    task_id: str
    status: Literal["approve", "request_changes", "reject"]
    severity: Literal["low", "medium", "high"]
    issues: List[Dict[str, Any]]         # {type, location, description, suggestion}
    summary: str
    follow_up_actions: List[str]


@dataclass
class ProgrammingResult:
    """
    整条流水线的结果，交给 PatchEvaluator / GovernanceCouncil。
    """
    task: ProgrammingTask
    dev_plan: DevPlan
    patch_set: CodePatchSet
    test_plan: TestPlan
    test_report: TestReport
    review: ReviewDecision
    tools_used: List[str]