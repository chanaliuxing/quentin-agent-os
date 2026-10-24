from __future__ import annotations

from typing import Dict, Any, Optional
from datetime import datetime
from enum import Enum
from pydantic import BaseModel, Field


class PatchKind(str, Enum):
    code = "code"
    config = "config"
    docs = "docs"


class PatchStatus(str, Enum):
    proposed = "proposed"       # 刚提出，还没测
    testing = "testing"         # 正在跑测试
    ready = "ready"             # 测试通过，可候选上线
    applied = "applied"         # 已经应用到代码
    rolled_back = "rolled_back" # 应用了又撤回
    rejected = "rejected"       # 不合格，被废弃


class PatchTestSummary(BaseModel):
    """
    测试结果摘要：
    v1 只做语法检查，将来可以扩展为 pytest / 回归测试。
    """
    ran_tests: bool = False
    passed: bool = False

    syntax_ok: bool = False
    test_command: Optional[str] = None  # 将来可记录 pytest 命令
    logs: str = ""

    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None


class PatchEvalSummary(BaseModel):
    """
    Patch 在“业务指标上的评估结果”：
    - 比如通过 ExperimentOrchestrator 跑出来的 A/B 结果。
    """
    evaluated: bool = False
    metric: str = "score"

    baseline_score: Optional[float] = None
    patch_score: Optional[float] = None
    improvement: Optional[float] = None

    experiment_id: Optional[str] = None
    notes: str = ""


class PatchRecord(BaseModel):
    """
    一条完整的“自编程补丁”记录：
    - 元信息 + 简单的 text_replace patch（v1）
    """
    patch_id: str

    kind: PatchKind = PatchKind.code
    target_file: str                 # 相对仓库根目录的路径
    description: str

    created_at: datetime = Field(default_factory=datetime.utcnow)
    created_by: str = "self_programming"

    # v1 的 patch 形式：简单的文本替换
    apply_mode: str = "text_replace"  # 预留扩展 file_overwrite / diff 等
    search: str                       # 要查找的片段
    replace: str                      # 替换后的片段

    status: PatchStatus = PatchStatus.proposed
    risk_score: float = 0.0
    allow_auto_apply: bool = False     # 是否允许自动上线（默认不允许）

    test_summary: PatchTestSummary = Field(default_factory=PatchTestSummary)
    eval_summary: PatchEvalSummary = Field(default_factory=PatchEvalSummary)

    meta: Dict[str, Any] = Field(default_factory=dict)


class PatchDraft(BaseModel):
  draft_id: str
  task_id: str
  summary: str
  files_touched: List[str]
  design_notes: str
  suggested_signatures: List[str]
  status: str  # "proposed" | "accepted" | "rejected"
