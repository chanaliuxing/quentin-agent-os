# meta_agent/patches/safe_applier.py
from __future__ import annotations
from quentin.utils.time import now_iso, now_utc
from typing import Optional
from pathlib import Path
from datetime import datetime
import shutil

from meta_agent.patches.models import PatchProposal
from meta_agent.patches.applier import PatchApplier
from meta_agent.safety.checker import PatchSafetyChecker
from meta_agent.safety.result import SafetyCheckResult
from meta_agent.patches.diff_stats import compute_unified_diff_stats
from quentin.traces.core import JsonlTraceRecorder, new_trace_event, TraceEventType


trace_recorder = JsonlTraceRecorder() # Use default repo root


class SafePatchApplier:
    """
    在真正写文件前，先跑安全检查。
    同时负责自动备份和回滚。
    """

    def __init__(
        self,
        base_applier: Optional[PatchApplier] = None,
        repo_root: str | Path = ".",
        safety_kernel: Optional[object] = None,
        domain: str = "core",
        environment: str = "sandbox",
        risk_level: str = "high",
    ):
        self.base_applier = base_applier or PatchApplier()
        self.repo_root = Path(repo_root)
        self.checker = PatchSafetyChecker(repo_root=repo_root)
        self.safety_kernel = safety_kernel
        self.domain = domain
        self.environment = environment
        self.risk_level = risk_level

    def apply_patch(self, patch: PatchProposal) -> SafetyCheckResult:
        """
        返回 SafetyCheckResult，让调用方决定是否继续后续动作。
        如果 allow_apply=False，base_applier 不会执行。
        """
        if not patch.diff_stats and patch.get_unified_diff():
            patch.diff_stats = compute_unified_diff_stats(patch.get_unified_diff(), targets=list(patch.target_files or []))

        result = self.checker.check(patch)

        trace_recorder.record_event(new_trace_event(
            trace_id=patch.id,
            event_type=TraceEventType.SELF_PROGRAMMING,
            payload={
                "action": "patch_safety_checked",
                "patch_id": patch.id,
                "allow_apply": result.allow_apply,
                "requires_human_review": result.requires_human_review,
                "reasons": result.reasons,
                "meta": result.meta,
            }
        ))

        if not result.allow_apply:
            # 直接拦截，不写磁盘
            trace_recorder.record_event(new_trace_event(
                trace_id=patch.id,
                event_type=TraceEventType.SELF_PROGRAMMING,
                payload={
                    "action": "patch_blocked_by_safety",
                    "patch_id": patch.id,
                    "reasons": result.reasons,
                }
            ))
            return result

        # --- PathGuard (non-bypass) ---
        try:
            from quentin.kernel.path_guard import PathGuard
            from quentin.self_programming.auto_updatable import ensure_auto_updatable

            pg = PathGuard(repo_root=self.repo_root)
            for target_file in list(patch.target_files or []):
                pg.ensure_allowed_path(str(target_file))
                ensure_auto_updatable(repo_root=self.repo_root, rel_path=str(target_file))
        except Exception as e:
            trace_recorder.record_event(
                new_trace_event(
                    trace_id=patch.id,
                    event_type=TraceEventType.SELF_PROGRAMMING,
                    payload={
                        "action": "patch_blocked_by_path_guard",
                        "patch_id": patch.id,
                        "reason": str(e),
                    },
                )
            )
            return SafetyCheckResult(
                allow_apply=False,
                requires_human_review=True,
                reasons=[f"PathGuard denied patch target: {e}"],
            )

        # --- SafetyKernel Guard (non-bypass for code_patch) ---
        if self.safety_kernel is not None:
            try:
                from quentin.kernel.policy import ActionRequest
                from quentin.kernel.taxonomy import ACTION_CODE_PATCH

                action = ActionRequest(
                    action_id=patch.id,
                    actor="safe_patch_applier",
                    action_type=ACTION_CODE_PATCH,
                    domain=self.domain,
                    environment=self.environment,
                    risk_level=self.risk_level,
                    estimated_cost_tokens=0,
                    estimated_cost_usd=0.0,
                    description=patch.intent or "code_patch",
                    metadata={
                        "patch_id": patch.id,
                        "target_files": list(patch.target_files or []),
                    },
                )
                guard = self.safety_kernel.guard_action(action)
                if not guard.allow:
                    trace_recorder.record_event(
                        new_trace_event(
                            trace_id=patch.id,
                            event_type=TraceEventType.SELF_PROGRAMMING,
                            payload={
                                "action": "patch_blocked_by_safety_kernel",
                                "patch_id": patch.id,
                                "reason": guard.reason,
                            },
                        )
                    )
                    return SafetyCheckResult(
                        allow_apply=False,
                        requires_human_review=True,
                        reasons=[f"SafetyKernel denied code_patch: {guard.reason}"],
                    )
            except Exception as e:
                return SafetyCheckResult(
                    allow_apply=False,
                    requires_human_review=True,
                    reasons=[f"SafetyKernel error: {e}"],
                )

        # --- Backup Logic ---
        # 遍历涉及的文件进行备份
        backup_files = {}
        for target_file in patch.target_files:
            abs_path = (self.repo_root / target_file).resolve()
            if abs_path.exists():
                timestamp = now_utc().strftime("%Y%m%d%H%M%S")
                backup_path = abs_path.with_suffix(abs_path.suffix + f".bak.{timestamp}")
                try:
                    shutil.copy2(abs_path, backup_path)
                    backup_files[str(abs_path)] = str(backup_path)
                except Exception as e:
                    # 备份失败则阻止应用
                    return SafetyCheckResult(
                        allow_apply=False, 
                        requires_human_review=True, 
                        reasons=[f"Backup failed for {target_file}: {e}"]
                    )
        
        # Store backup info in metadata
        patch.metadata["backups"] = backup_files
        try:
            self.base_applier.apply_patch(patch)
        except Exception as e:
             # 应用失败，尝试回滚（如果部分文件已修改）
             # 这里简单起见，仅返回失败
             return SafetyCheckResult(
                 allow_apply=False,
                 requires_human_review=True,
                 reasons=[f"Apply failed: {e}"]
             )

        trace_recorder.record_event(new_trace_event(
            trace_id=patch.id,
            event_type=TraceEventType.SELF_PROGRAMMING,
            payload={
                "action": "patch_applied_with_safety",
                "patch_id": patch.id,
                "meta": result.meta,
                "backups": backup_files
            }
        ))

        return result

    def revert(self, action_id: str, *, patch_store_path: str = "data/patches.json") -> bool:
        """
        Minimal revert entrypoint required by blueprint:
        `revert(action_id)` where `action_id` is the code_patch action_id.

        In this implementation we use `patch.id == action_id` for correlation.
        """
        try:
            from meta_agent.patches.store import PatchStore

            store = PatchStore(path=patch_store_path)
            patch = store.get_patch(action_id)
            if not patch:
                return False
            return self.rollback(patch)
        except Exception:
            return False

    def rollback(self, patch: PatchProposal) -> bool:
        """
        根据 patch.metadata 中的备份信息进行回滚。
        """
        backups = patch.metadata.get("backups", {})
        if not backups:
            return False

        success = True
        for target_path, backup_path in backups.items():
            try:
                shutil.copy2(backup_path, target_path)
                print(f"Rolled back {target_path} from {backup_path}")
            except Exception as e:
                print(f"Failed to rollback {target_path}: {e}")
                success = False
        
        return success
