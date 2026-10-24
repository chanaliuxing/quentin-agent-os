from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, Optional

import json

from quentin.self_programming.schema import (
    PatchProposal,
    PatchTarget,
    PatchTestPlan,
)
from quentin.traces.core import TraceRecorder, TraceEventType, new_trace_event
from quentin.runtime.session_write_lock import acquire_session_write_lock
from quentin.infra.unified_diff import PatchApplyError, apply_unified_diff_to_text
from quentin.utils.time import now_iso, now_utc


@dataclass
class PatchApplyLog:
    """
    记录一次 Patch 应用的元信息，用于审计和回滚。
    """
    proposal_id: str
    target_path: str             # 相对于 repo_root
    backup_path: str             # 备份文件路径（相对于 repo_root）
    applied_at: str
    dry_run: bool
    status: str                  # "applied" | "dry_run" | "failed"
    message: str
    meta: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _now_iso() -> str:
    return now_iso()


class PatchApplier:
    """
    负责 Patch 的安全应用和回滚。

    关键点：
      - 只允许修改 repo_root/mutable/** 下的文件
      - 应用前必备份原文件到 data/patches/backups/
      - 默认 dry_run = True，只在 --apply 显式指定时才真的写文件
    """

    def __init__(self, repo_root: str | Path, trace_recorder: TraceRecorder, evolve_in_sandbox: bool = False) -> None:
        self.repo_root = Path(repo_root).resolve()
        self.trace_recorder = trace_recorder
        self.evolve_in_sandbox = evolve_in_sandbox

        self._patches_dir = self.repo_root / "data" / "patches"
        self._proposals_dir = self._patches_dir / "proposals"
        self._backups_dir = self._patches_dir / "backups"
        self._applied_dir = self._patches_dir / "applied"

        self._proposals_dir.mkdir(parents=True, exist_ok=True)
        self._backups_dir.mkdir(parents=True, exist_ok=True)
        self._applied_dir.mkdir(parents=True, exist_ok=True)

    # ----------------------------
    # 对外：按 proposal_id 应用 patch
    # ----------------------------
    def apply_by_id(self, proposal_id: str, *, dry_run: bool = True) -> PatchApplyLog:
        # Force dry_run if operating in sandbox mode
        actual_dry_run = dry_run or self.evolve_in_sandbox
        
        proposal = self._load_proposal_by_id(proposal_id)
        if proposal is None:
            log = PatchApplyLog(
                proposal_id=proposal_id,
                target_path="",
                backup_path="",
                applied_at=_now_iso(),
                dry_run=actual_dry_run, # Use actual_dry_run here
                status="failed",
                message=f"Proposal {proposal_id} not found.",
                meta={},
            )
            self._record_apply_log(log)
            return log

        return self.apply_proposal(proposal, dry_run=actual_dry_run)

    # ----------------------------
    # 对外：直接用 PatchProposal 应用
    # ----------------------------
    def apply_proposal(self, proposal: PatchProposal, *, dry_run: bool = True) -> PatchApplyLog:
        # Force dry_run if operating in sandbox mode
        actual_dry_run = dry_run or self.evolve_in_sandbox

        target_rel = Path(proposal.target.path)
        target_abs = self.repo_root / target_rel

        # 安全检查：必须在 mutable/ 下
        if not str(target_rel).startswith("mutable/"):
            msg = f"Refuse to patch non-mutable path: {target_rel}"
            log = PatchApplyLog(
                proposal_id=proposal.proposal_id,
                target_path=str(target_rel),
                backup_path="",
                applied_at=_now_iso(),
                dry_run=actual_dry_run, # Use actual_dry_run here
                status="failed",
                message=msg,
                meta={"reason": "outside_mutable_dir"},
            )
            self._record_apply_log(log)
            return log

        # 读取原内容（不存在时视为空文件）
        try:
            original_content = target_abs.read_text(encoding="utf-8") if target_abs.exists() else ""
        except Exception as e:
            msg = f"Failed to read target file: {e!r}"
            log = PatchApplyLog(
                proposal_id=proposal.proposal_id,
                target_path=str(target_rel),
                backup_path="",
                applied_at=_now_iso(),
                dry_run=actual_dry_run, # Use actual_dry_run here
                status="failed",
                message=msg,
                meta={},
            )
            self._record_apply_log(log)
            return log

        # 生成新内容（当前版本：简单策略）
        if proposal.patch_type == "full_file":
            new_content = proposal.patch_content
        elif proposal.patch_type == "snippet":
            # 非破坏性：先不替换，直接在文件末尾追加“候选实现”，由人/后续逻辑来整合
            new_content = (
                original_content
                + "\n\n"
                + "# ===== Candidate patch snippet (proposal: "
                + proposal.proposal_id
                + ") =====\n"
                + proposal.patch_content
                + "\n# ===== End of candidate patch snippet =====\n"
            )
        elif proposal.patch_type == "unified_diff":
            try:
                new_content = apply_unified_diff_to_text(original_content, proposal.patch_content)
            except PatchApplyError as e:
                msg = f"unified_diff application failed: {e}"
                log = PatchApplyLog(
                    proposal_id=proposal.proposal_id,
                    target_path=str(target_rel),
                    backup_path="",
                    applied_at=_now_iso(),
                    dry_run=actual_dry_run,
                    status="failed",
                    message=msg,
                    meta={"reason": "unified_diff_apply_failed"},
                )
                self._record_apply_log(log)
                return log
        else:
            msg = f"Unknown patch_type: {proposal.patch_type}"
            log = PatchApplyLog(
                proposal_id=proposal.proposal_id,
                target_path=str(target_rel),
                backup_path="",
                applied_at=_now_iso(),
                dry_run=actual_dry_run, # Use actual_dry_run here
                status="failed",
                message=msg,
                meta={},
            )
            self._record_apply_log(log)
            return log

        # 如果是 dry_run，只返回 log，不写文件
        if actual_dry_run:
            msg = "Dry run only. No file was modified."
            log = PatchApplyLog(
                proposal_id=proposal.proposal_id,
                target_path=str(target_rel),
                backup_path="",
                applied_at=_now_iso(),
                dry_run=True,
                status="dry_run",
                message=msg,
                meta={"new_content_preview": new_content[:400]},
            )
            self._record_apply_log(log)
            return log

        # 真正写入：先备份，再写文件
        backup_rel, backup_abs = self._backup_file(target_rel, original_content)

        try:
            target_abs.parent.mkdir(parents=True, exist_ok=True)
            target_abs.write_text(new_content, encoding="utf-8")
        except Exception as e:
            msg = f"Failed to write patched file: {e!r}"
            log = PatchApplyLog(
                proposal_id=proposal.proposal_id,
                target_path=str(target_rel),
                backup_path=str(backup_rel),
                applied_at=_now_iso(),
                dry_run=False,
                status="failed",
                message=msg,
                meta={},
            )
            self._record_apply_log(log)
            return log

        msg = "Patch applied successfully."
        log = PatchApplyLog(
            proposal_id=proposal.proposal_id,
            target_path=str(target_rel),
            backup_path=str(backup_rel),
            applied_at=_now_iso(),
            dry_run=False,
            status="applied",
            message=msg,
            meta={},
        )
        self._record_apply_log(log)
        return log

    # ----------------------------
    # 回滚：按 proposal_id
    # ----------------------------
    def rollback_by_proposal(self, proposal_id: str) -> PatchApplyLog:
        """
        根据 proposal_id 查找最近一次 apply 日志，然后用对应备份回滚。
        """
        log_path = self._applied_dir / f"{proposal_id}.jsonl"
        if not log_path.exists():
            log = PatchApplyLog(
                proposal_id=proposal_id,
                target_path="",
                backup_path="",
                applied_at=_now_iso(),
                dry_run=self.evolve_in_sandbox, # Use self.evolve_in_sandbox here
                status="failed",
                message="No apply log found for this proposal.",
                meta={},
            )
            self._record_apply_log(log)
            return log

        # 使用最后一行作为最近一次 apply
        last_line = None
        with log_path.open("r", encoding="utf-8") as f:
            for line in f:
                last_line = line.strip()
        if not last_line:
            log = PatchApplyLog(
                proposal_id=proposal_id,
                target_path="",
                backup_path="",
                applied_at=_now_iso(),
                dry_run=self.evolve_in_sandbox, # Use self.evolve_in_sandbox here
                status="failed",
                message="Apply log file is empty.",
                meta={},
            )
            self._record_apply_log(log)
            return log

        data = json.loads(last_line)
        target_rel = Path(data["target_path"])
        backup_rel = Path(data["backup_path"])

        target_abs = self.repo_root / target_rel
        backup_abs = self.repo_root / backup_rel

        if not backup_abs.exists():
            log = PatchApplyLog(
                proposal_id=proposal_id,
                target_path=str(target_rel),
                backup_path=str(backup_rel),
                applied_at=_now_iso(),
                dry_run=self.evolve_in_sandbox, # Use self.evolve_in_sandbox here
                status="failed",
                message="Backup file not found.",
                meta={},
            )
            self._record_apply_log(log)
            return log

        # 如果是 sandbox 模式，回滚也只是 dry_run
        if self.evolve_in_sandbox:
             log = PatchApplyLog(
                 proposal_id=proposal_id,
                 target_path=str(target_rel),
                 backup_path=str(backup_rel),
                 applied_at=_now_iso(),
                 dry_run=True,
                 status="dry_run",
                 message="Rollback dry run due to sandbox mode.",
                 meta={"rollback": True},
             )
             self._record_apply_log(log)
             return log

        # 回滚：用备份覆盖当前文件
        try:
            content = backup_abs.read_text(encoding="utf-8")
            target_abs.parent.mkdir(parents=True, exist_ok=True)
            target_abs.write_text(content, encoding="utf-8")
        except Exception as e:
            log = PatchApplyLog(
                proposal_id=proposal_id,
                target_path=str(target_rel),
                backup_path=str(backup_rel),
                applied_at=_now_iso(),
                dry_run=self.evolve_in_sandbox, # Use self.evolve_in_sandbox here
                status="failed",
                message=f"Failed to rollback: {e!r}",
                meta={},
            )
            self._record_apply_log(log)
            return log

        log = PatchApplyLog(
            proposal_id=proposal.proposal_id if 'proposal' in locals() and proposal else proposal_id, # Use proposal_id from arg as proposal might not be loaded
            target_path=str(target_rel),
            backup_path=str(backup_rel),
            applied_at=_now_iso(),
            dry_run=False,
            status="applied",
            message="Rollback succeeded.",
            meta={"rollback": True},
        )
        self._record_apply_log(log)
        return log

    # ----------------------------
    # 内部：读 Proposal
    # ----------------------------
    def _load_proposal_by_id(self, proposal_id: str) -> Optional[PatchProposal]:
        path = self._proposals_dir / f"{proposal_id}.json"
        if not path.exists():
            return None
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)

        # 手动重建 dataclass
        target = PatchTarget(**data["target"])
        test_plan = PatchTestPlan(
            **data.get("test_plan", {}),
        )
        proposal = PatchProposal(
            proposal_id=data["proposal_id"],
            created_at=data["created_at"],
            created_by=data["created_by"],
            target=target,
            rationale=data["rationale"],
            patch_type=data["patch_type"],
            patch_content=data["patch_content"],
            test_plan=test_plan,
            meta=data.get("meta", {}),
        )
        return proposal

    # ----------------------------
    # 内部：备份和日志
    # ----------------------------
    def _backup_file(self, target_rel: Path, original_content: str) -> tuple[Path, Path]:
        ts = now_utc().strftime("%Y%m%dT%H%M%S")
        backup_rel = Path("data") / "patches" / "backups" / f"{target_rel.as_posix().replace('/', '_')}.{ts}.bak"
        backup_abs = self.repo_root / backup_rel
        backup_abs.parent.mkdir(parents=True, exist_ok=True)
        backup_abs.write_text(original_content, encoding="utf-8")
        return backup_rel, backup_abs

    def _record_apply_log(self, log: PatchApplyLog) -> None:
        """
        写入：
          - data/patches/applied/{proposal_id}.jsonl
          - TraceEvent (SELF_PROGRAMMING)
        """
        # JSONL (append-only)
        path = self._applied_dir / f"{log.proposal_id}.jsonl"
        lock = acquire_session_write_lock(session_file=path)
        try:
            with path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(log.to_dict(), ensure_ascii=False) + "\n")
        finally:
            lock["release"]()

        # Trace
        self.trace_recorder.record_event(
            new_trace_event(
                trace_id="self-programming",
                event_type=TraceEventType.SELF_PROGRAMMING,
                payload={
                    "patch_apply_log": log.to_dict(),
                },
            )
        )
