from __future__ import annotations

from dataclasses import dataclass, asdict, field
from typing import Any, Dict, Optional
from quentin.utils.time import now_iso


@dataclass
class PatchEvalReport:
    """
    Static evaluation result for a patch (no execution).
    """

    ok: bool
    score: float
    risk_level: str
    issues: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Patch:
    """
    Legacy v1 patch representation.
    """

    patch_id: str
    target_path: str
    target_symbol: Optional[str] = None
    change_type: str = "refactor"
    intent: str = ""
    patch_text: str = ""
    tests: str = ""
    created_by: str = "selfprog"
    created_at: str = field(default_factory=lambda: now_iso())
    updated_at: str = field(default_factory=lambda: now_iso())
    status: str = "proposed"
    risk_level: str = "unknown"
    eval_report: Optional[PatchEvalReport] = None
    gate_decision: Optional[str] = None
    gate_reason: Optional[str] = None
    applied_at: Optional[str] = None
    applied_environment: Optional[str] = None
    backup_path: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        if self.eval_report is not None:
            d["eval_report"] = self.eval_report.to_dict()
        return d

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Patch":
        eval_data = d.get("eval_report")
        if eval_data:
            eval_report = PatchEvalReport(
                ok=bool(eval_data.get("ok", False)),
                score=float(eval_data.get("score", 0.0)),
                risk_level=str(eval_data.get("risk_level", "unknown")),
                issues=list(eval_data.get("issues", []) or []),
                warnings=list(eval_data.get("warnings", []) or []),
            )
        else:
            eval_report = None

        return cls(
            patch_id=str(d["patch_id"]),
            target_path=str(d.get("target_path", "")),
            target_symbol=d.get("target_symbol"),
            change_type=str(d.get("change_type", "refactor")),
            intent=str(d.get("intent", "")),
            patch_text=str(d.get("patch_text", "")),
            tests=str(d.get("tests", "")),
            created_by=str(d.get("created_by", "selfprog")),
            created_at=d.get("created_at"),
            updated_at=d.get("updated_at"),
            status=str(d.get("status", "proposed")),
            risk_level=str(d.get("risk_level", "unknown")),
            eval_report=eval_report,
            gate_decision=d.get("gate_decision"),
            gate_reason=d.get("gate_reason"),
            applied_at=d.get("applied_at"),
            applied_environment=d.get("applied_environment"),
            backup_path=d.get("backup_path"),
            metadata=d.get("metadata", {}) or {},
        )
