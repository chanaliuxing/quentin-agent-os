from __future__ import annotations

from pathlib import Path
from typing import Optional
import shutil
import logging

from quentin.kernel.safety import SafetyKernel
from quentin.self_programming.legacy_selfprog.models import Patch
from quentin.self_programming.legacy_selfprog.registry import FileBackedPatchRegistry
from quentin.utils.time import now_iso

logger = logging.getLogger(__name__)


class PatchApplier:
    """
    Legacy patch applier that overwrites entire file content with `patch.patch_text`.
    Kept for compatibility with older CLI flows.
    """

    def __init__(
        self,
        *,
        repo_root: str | Path = ".",
        registry: Optional[FileBackedPatchRegistry] = None,
        safety_kernel: Optional[SafetyKernel] = None,
        backup_dir: str | Path = "data/patch_backups",
    ) -> None:
        self.repo_root = Path(repo_root).resolve()
        self.registry = registry or FileBackedPatchRegistry()
        self.safety_kernel = safety_kernel or SafetyKernel(repo_root=self.repo_root)
        self.backup_dir = self.repo_root / backup_dir
        self.backup_dir.mkdir(parents=True, exist_ok=True)

    def apply_patch(
        self,
        patch_id: str,
        environment: str = "staging",
        *,
        min_score: float = 0.7,
    ) -> Optional[Patch]:
        patch = self.registry.get_patch(patch_id)
        if not patch:
            logger.warning("PatchApplier.apply_patch: patch not found: %s", patch_id)
            return None

        policy = self.safety_kernel.check_self_programming_target(patch.target_path)
        if policy.decision == "deny":
            patch.status = "rejected"
            patch.gate_decision = patch.gate_decision or "reject"
            patch.gate_reason = (patch.gate_reason or "") + f" | safety_kernel: {policy.reason}"
            patch.updated_at = now_iso()
            self.registry.upsert_patch(patch)
            return patch

        if patch.eval_report is not None:
            if not patch.eval_report.ok or patch.eval_report.score < min_score:
                return patch

        target_file = (self.repo_root / patch.target_path).resolve()
        target_file.parent.mkdir(parents=True, exist_ok=True)

        if target_file.exists():
            backup_path = self._backup_file(patch, target_file)
            patch.backup_path = str(backup_path) if backup_path else None

        target_file.write_text(patch.patch_text or "", encoding="utf-8")

        now = now_iso()
        patch.applied_at = now
        patch.applied_environment = environment
        patch.status = "applied"
        patch.updated_at = now
        patch.metadata.setdefault("apply_history", []).append(
            {"applied_at": now, "environment": environment, "backup_path": patch.backup_path}
        )
        self.registry.upsert_patch(patch)
        return patch

    def rollback_patch(self, patch_id: str) -> Optional[Patch]:
        patch = self.registry.get_patch(patch_id)
        if not patch or not patch.backup_path:
            return patch
        backup_file = Path(patch.backup_path)
        target_file = (self.repo_root / patch.target_path).resolve()
        if not backup_file.exists():
            return patch
        target_file.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(backup_file, target_file)
        now = now_iso()
        patch.status = "rolled_back"
        patch.updated_at = now
        patch.metadata.setdefault("rollback_history", []).append({"rolled_back_at": now, "backup_path": patch.backup_path})
        self.registry.upsert_patch(patch)
        return patch

    def _backup_file(self, patch: Patch, target_file: Path) -> Optional[Path]:
        try:
            backup_name = f"{patch.patch_id}.orig"
            backup_path = self.backup_dir / backup_name
            shutil.copy2(target_file, backup_path)
            return backup_path
        except Exception:
            logger.exception("PatchApplier._backup_file: failed to backup %s", target_file)
            return None
