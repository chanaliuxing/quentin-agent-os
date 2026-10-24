from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional

import json

from quentin.governance.patch_council import PatchGovernanceCouncil, PatchDecision
from quentin.utils.time import now_iso, now_utc


@dataclass
class BatchPatchGovernResult:
    """
    一次批量治理的总结果。
    """
    total_reports: int
    processed: int
    skipped: int
    decisions: List[PatchDecision]
    started_at: str
    finished_at: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_reports": self.total_reports,
            "processed": self.processed,
            "skipped": self.skipped,
            "decisions": [d.to_dict() for d in self.decisions],
            "started_at": self.started_at,
            "finished_at": self.finished_at,
        }


class BatchPatchGovernor:
    """
    扫描 data/patches/reports 下所有 PatchReport，
    对尚未决策的 proposal 执行治理决策（可选 auto_apply）。
    """

    def __init__(
        self,
        *,
        repo_root: str | Path,
        patch_council: PatchGovernanceCouncil,
    ) -> None:
        self.repo_root = Path(repo_root).resolve()
        self.patch_council = patch_council

        self._reports_dir = self.repo_root / "data" / "patches" / "reports"
        self._decisions_dir = self.repo_root / "data" / "governance" / "patch_decisions"
        self._batch_runs_dir = self.repo_root / "data" / "governance" / "batch_runs"
        self._batch_runs_dir.mkdir(parents=True, exist_ok=True)

    # --------------------------------------------------
    # 对外：批量治理
    # --------------------------------------------------
    def auto_govern_all(
        self,
        *,
        metrics: Dict[str, Any],
        immune_snapshot: Optional[Dict[str, Any]] = None,
        auto_apply: bool = False,
        only_recommended: Optional[List[str]] = None,
        max_patches: Optional[int] = None,
    ) -> BatchPatchGovernResult:
        """
        参数：
          - metrics / immune_snapshot: 来自 MetricsAggregator + ImmuneLoop
          - auto_apply: 是否允许对通过检查的 patch 自动在 sandbox apply
          - only_recommended: 只治理哪些 PatchReport 的 recommended_action
                例: ["accept"] 则只治理建议接受的 patch
          - max_patches: 最多处理多少个 patch

        返回：
          - BatchPatchGovernResult
        """
        start_ts = now_iso()

        reports = self._list_patch_reports()
        total_reports = len(reports)

        decisions: List[PatchDecision] = []
        processed = 0
        skipped = 0

        for report_path in reports:
            proposal_id = report_path.stem  # 默认报告名是 <proposal_id>.json

            # 1) 已有决策则跳过
            if self._has_existing_decision(proposal_id):
                skipped += 1
                continue

            # 2) 如果指定 only_recommended，则检查 PatchReport 里里的推荐动作，不匹配就跳过
            if only_recommended is not None:
                try:
                    with report_path.open("r", encoding="utf-8") as f:
                        rp = json.load(f)
                    rec = rp.get("recommended_action")
                    if rec not in only_recommended:
                        skipped += 1
                        continue
                except Exception:
                    # 报告坏了/解析失败，安全起见也跳过
                    skipped += 1
                    continue

            # 3) 调用理事会治理 + 可选自动 apply
            decision = self.patch_council.govern_patch(
                proposal_id=proposal_id,
                metrics=metrics,
                immune_snapshot=immune_snapshot,
                auto_apply=auto_apply,
            )
            decisions.append(decision)
            processed += 1

            if max_patches is not None and processed >= max_patches:
                break

        finished_ts = now_iso()
        result = BatchPatchGovernResult(
            total_reports=total_reports,
            processed=processed,
            skipped=skipped,
            decisions=decisions,
            started_at=start_ts,
            finished_at=finished_ts,
        )

        # 落盘一次 batch run 记录
        self._persist_batch_result(result)
        return result

    # --------------------------------------------------
    # 内部：列出所有 PatchReport
    # --------------------------------------------------
    def _list_patch_reports(self) -> List[Path]:
        if not self._reports_dir.exists():
            return []
        return sorted(self._reports_dir.glob("*.json"))

    # --------------------------------------------------
    # 内部：判断某 proposal 是否已有治理决策
    # --------------------------------------------------
    def _has_existing_decision(self, proposal_id: str) -> bool:
        if not self._decisions_dir.exists():
            return False
        # 规则：任何以 <proposal_id>_ 开头的决策文件都视为已有决策
        matches = list(self._decisions_dir.glob(f"{proposal_id}_*.json"))
        return len(matches) > 0

    # --------------------------------------------------
    # 内部：保存本次 batch run 结果
    # --------------------------------------------------
    def _persist_batch_result(self, result: BatchPatchGovernResult) -> None:
        ts = now_utc().strftime("%Y%m%dT%H%M%S")
        path = self._batch_runs_dir / f"batch_govern_{ts}.json"
        tmp = path.with_suffix(".tmp")

        with tmp.open("w", encoding="utf-8") as f:
            json.dump(result.to_dict(), f, ensure_ascii=False, indent=2)

        tmp.replace(path)
