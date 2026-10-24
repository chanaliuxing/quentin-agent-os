# quentin/self_programming/patches.py
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Dict, Any, List, Literal, Optional
from quentin.utils.time import now_iso

logger = logging.getLogger(__name__)

PatchStatus = Literal["proposed", "evaluated", "accepted", "rejected", "applied", "superseded"]
PatchType = Literal["diff", "file_replace", "snippet", "other"]


@dataclass
class PatchTestCaseResult:
    name: str
    status: str
    duration_sec: Optional[float] = None
    error_message: Optional[str] = None
    extra: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class PatchTestReport:
    report_id: str
    patch_id: str
    created_at: str
    success: bool
    total_cases: int
    passed: int
    failed: int
    errored: int
    skipped: int
    runtime_sec: Optional[float] = None
    static_analysis: Dict[str, Any] = field(default_factory=dict)
    cases: List[PatchTestCaseResult] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "report_id": self.report_id,
            "patch_id": self.patch_id,
            "created_at": self.created_at,
            "success": self.success,
            "total_cases": self.total_cases,
            "passed": self.passed,
            "failed": self.failed,
            "errored": self.errored,
            "skipped": self.skipped,
            "runtime_sec": self.runtime_sec,
            "static_analysis": self.static_analysis,
            "cases": [c.to_dict() for c in self.cases],
        }


@dataclass
class CodePatch:
    """
    自编程引擎生成的“补丁”抽象，暂时只是结构定义：

    - patch_id       : 唯一 ID
    - task_id        : 来源的 ImprovementTask ID（如 "bp::memory_fabric::mf.storage"）
    - capability     : 对应 capability_id（如 "memory_fabric"）
    - requirement_id : 对应 requirement_id（如 "mf.storage"）

    - target_module  : 目标 Python 模块名（如 "quentin.memory.store"）
    - target_file    : 目标文件相对路径（如 "quentin/memory/store.py"）

    - patch_type     : "diff" / "file_replace" / "snippet" / ...
    - patch_content  : 补丁内容（可以是 unified diff / 新文件源码 / 片段）

    - created_by     : 谁生成的（如 "MultiAICouncil"）
    - created_at     : ISO 时间
    - updated_at     : ISO 时间
    - status         : 当前状态（proposed / evaluated / accepted / ...）

    - metadata       : 额外信息（比如参与的模型、会议记录等）
    - eval_summary   : 测试/评估结果摘要（由 EvalHarness 填充）
    """
    patch_id: str
    task_id: str
    capability: str
    requirement_id: str

    target_module: str
    target_file: str

    patch_type: PatchType
    patch_content: str

    created_by: str = "unknown"
    created_at: str = field(default_factory=lambda: now_iso())
    updated_at: str = field(default_factory=lambda: now_iso())
    status: PatchStatus = "proposed"

    metadata: Dict[str, Any] = field(default_factory=dict)
    eval_summary: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CodePatch":
        return cls(
            patch_id=data["patch_id"],
            task_id=data["task_id"],
            capability=data.get("capability", ""),
            requirement_id=data.get("requirement_id", ""),
            target_module=data.get("target_module", ""),
            target_file=data.get("target_file", ""),
            patch_type=data.get("patch_type", "other"),
            patch_content=data.get("patch_content", ""),
            created_by=data.get("created_by", "unknown"),
            created_at=data.get("created_at", ""),
            updated_at=data.get("updated_at", ""),
            status=data.get("status", "proposed"),
            metadata=data.get("metadata", {}) or {},
            eval_summary=data.get("eval_summary", {}) or {},
        )


class FileBackedPatchStore:
    """
    最简单的 Patch 存储：一个 JSON 文件 {patch_id: CodePatchDict}
    """

    def __init__(self, path: str | Path = "data/code_patches.json") -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._loaded = False

    def _load(self) -> None:
        if self._loaded:
            return
        if self.path.exists():
            try:
                raw = json.loads(self.path.read_text(encoding="utf-8") or "{}")
                self._cache = raw
            except Exception:
                logger.exception("Failed to load patches from %s", self.path)
                self._cache = {}
        else:
            self._cache = {}
        self._loaded = True

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(self._cache, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    # ---------- CRUD ----------

    def get(self, patch_id: str) -> Optional[CodePatch]:
        self._load()
        d = self._cache.get(patch_id)
        return CodePatch.from_dict(d) if d else None

    def upsert(self, patch: CodePatch) -> None:
        self._load()
        patch.updated_at = now_iso()
        self._cache[patch.patch_id] = patch.to_dict()
        self._save()

    def delete(self, patch_id: str) -> None:
        self._load()
        if patch_id in self._cache:
            del self._cache[patch_id]
            self._save()

    def list_all(self) -> List[CodePatch]:
        self._load()
        return [CodePatch.from_dict(d) for d in self._cache.values()]

    def list_by_status(self, status: PatchStatus) -> List[CodePatch]:
        return [p for p in self.list_all() if p.status == status]
