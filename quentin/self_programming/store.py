# quentin/self_programming/store.py
from __future__ import annotations

from typing import Any, Dict, List, Optional
from pathlib import Path
import json
import logging

from quentin.self_programming.schema import PatchCandidate, PatchReport

logger = logging.getLogger(__name__)


class PatchStore:
    """
    v1: Patch 候选和评估报告的文件存储。
    """

    def __init__(self, *, repo_root: str | Path = ".") -> None:
        self.repo_root = Path(repo_root).resolve()
        self.base_dir = self.repo_root / "data" / "patches"
        self.base_dir.mkdir(parents=True, exist_ok=True)

        self.cand_dir = self.base_dir / "candidates"
        self.cand_dir.mkdir(parents=True, exist_ok=True)

        self.report_dir = self.base_dir / "reports"
        self.report_dir.mkdir(parents=True, exist_ok=True)

    # ----- Candidate ----- #
    def save_candidate(self, cand: PatchCandidate) -> None:
        path = self.cand_dir / f"{cand.patch_id}.json"
        try:
            path.write_text(
                json.dumps(cand.to_dict(), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception:
            logger.exception("PatchStore: failed to save candidate %s", path)

    def load_candidate(self, patch_id: str) -> Optional[PatchCandidate]:
        path = self.cand_dir / f"{patch_id}.json"
        if not path.exists():
            return None
        try:
            obj = json.loads(path.read_text(encoding="utf-8"))
            from quentin.self_programming.schema import PatchTargetRef, PatchCandidate

            target = PatchTargetRef(**obj["target"])
            return PatchCandidate(
                patch_id=obj["patch_id"],
                target=target,
                description=obj.get("description", ""),
                patch_diff=obj.get("patch_diff", ""),
                created_at=obj.get("created_at", ""),
                created_by=obj.get("created_by", "self_programming_engine"),
                origin=obj.get("origin", {}),
                status=obj.get("status", "pending_tests"),
                notes=obj.get("notes", ""),
            )
        except Exception:
            logger.exception("PatchStore: failed to load candidate %s", path)
            return None

    def list_candidates(self, status: Optional[str] = None, limit: int = 100) -> List[PatchCandidate]:
        cands: List[PatchCandidate] = []
        for path in self.cand_dir.glob("*.json"):
            c = self.load_candidate(path.stem)
            if c is None:
                continue
            if status is not None and c.status != status:
                continue
            cands.append(c)
            if len(cands) >= limit:
                break
        return cands

    # ----- Report ----- #
    def save_report(self, report: PatchReport) -> None:
        path = self.report_dir / f"{report.patch_id}.json"
        try:
            path.write_text(
                json.dumps(report.to_dict(), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception:
            logger.exception("PatchStore: failed to save report %s", path)

    def load_report(self, patch_id: str) -> Optional[PatchReport]:
        path = self.report_dir / f"{patch_id}.json"
        if not path.exists():
            return None
        try:
            obj = json.loads(path.read_text(encoding="utf-8"))
            from quentin.self_programming.schema import PatchReport, PatchTestResult

            tests = [PatchTestResult(**t) for t in obj.get("tests", [])]
            return PatchReport(
                patch_id=obj["patch_id"],
                status=obj.get("status", "failed"),
                created_at=obj.get("created_at", ""),
                tests=tests,
                coverage=float(obj.get("coverage", 0.0)),
                risk_score=float(obj.get("risk_score", 1.0)),
                metrics_delta=obj.get("metrics_delta", {}),
                error=obj.get("error"),
                notes=obj.get("notes", ""),
                origin=obj.get("origin", {}),
            )
        except Exception:
            logger.exception("PatchStore: failed to load report %s", path)
            return None
