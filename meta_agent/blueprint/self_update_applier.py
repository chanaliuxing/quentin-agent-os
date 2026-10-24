# meta_agent/blueprint/self_update_applier.py
from __future__ import annotations
from quentin.utils.time import now_iso, now_utc
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from pathlib import Path
import json
import shutil
import yaml
import datetime as dt

from meta_agent.blueprint.patch_models import (
    BlueprintPatchProposal,
    BlueprintPatchOperation,
)


@dataclass
class BlueprintApplyResult:
    is_blocked: bool
    reasons: List[str] = field(default_factory=list)
    modified_clause_ids: List[str] = field(default_factory=list)


class BlueprintPatchApplier:
    """
    把 BlueprintPatchProposal 实际应用到 blueprint_v2.yml（或 .json）。
    当前只实现简单的字段修改，复杂的如 split/merge/add/remove 可后续按需补充。
    """

    def __init__(self, blueprint_path: str | Path) -> None:
        self.blueprint_path = Path(blueprint_path)

    def apply_proposal(self, proposal: BlueprintPatchProposal) -> BlueprintApplyResult:
        if not self.blueprint_path.exists():
            return BlueprintApplyResult(is_blocked=True, reasons=[f"blueprint file not found: {self.blueprint_path}"])

        bp = self._load_blueprint()
        modified_ids: List[str] = []
        reasons: List[str] = []

        for op in proposal.operations:
            # In a more robust version, we would track clauses by ID in a dict
            target_clause = self._find_clause(bp, op.target_clause_id)
            
            if op.op_type == "add_clause":
                if not self._apply_add_clause(bp, op):
                    reasons.append(f"failed_to_apply_op({op.op_type})")
                continue # Special handling for add

            if target_clause is None:
                reasons.append(f"failed_to_find_clause({op.target_clause_id})")
                continue

            if self._apply_single_operation(target_clause, op):
                modified_ids.append(op.target_clause_id)
            else:
                reasons.append(f"failed_to_apply_op({op.op_type} on {op.target_clause_id})")
        
        if reasons:
            # For now, we proceed even if some ops fail, but log the reasons.
            pass

        self._backup_current_file()
        self._save_blueprint(bp)

        return BlueprintApplyResult(is_blocked=False, reasons=reasons, modified_clause_ids=list(set(modified_ids)))

    def _load_blueprint(self) -> Dict[str, Any]:
        text = self.blueprint_path.read_text(encoding="utf-8")
        return yaml.safe_load(text)

    def _save_blueprint(self, bp: Dict[str, Any]) -> None:
        text = yaml.safe_dump(bp, allow_unicode=True, sort_keys=False)
        self.blueprint_path.write_text(text, encoding="utf-8")

    def _backup_current_file(self) -> None:
        backup_dir = self.blueprint_path.parent / "backups"
        backup_dir.mkdir(parents=True, exist_ok=True)
        backup_path = backup_dir / f"{self.blueprint_path.name}.{now_utc().strftime('%Y%m%d%H%M%S')}.bak"
        shutil.copy2(self.blueprint_path, backup_path)

    def _find_clause(self, bp: Dict[str, Any], clause_id: str) -> Optional[Dict[str, Any]]:
        for section in bp.get("sections", []):
            for clause in section.get("clauses", []):
                if clause.get("id") == clause_id:
                    return clause
        return None

    def _apply_single_operation(self, clause: Dict[str, Any], op: BlueprintPatchOperation) -> bool:
        try:
            if op.op_type == "update_priority":
                clause["priority"] = int(op.new_value)
            elif op.op_type == "update_status":
                clause["status"] = str(op.new_value)
            elif op.op_type == "edit_description":
                clause["rationale"] = str(op.new_value) # Assuming description maps to rationale
            elif op.op_type == "edit_acceptance_criteria":
                clause["acceptance_criteria"] = list(op.new_value)
            elif op.op_type == "deprecate_clause":
                clause["status"] = "deprecated"
            elif op.op_type in ("split_clause", "merge_clauses", "remove_clause"):
                return False # Not implemented
            else:
                return False
        except (ValueError, TypeError):
            return False
        return True

    def _apply_add_clause(self, bp: Dict[str, Any], op: BlueprintPatchOperation) -> bool:
        new_clause = op.extra.get("clause")
        if not isinstance(new_clause, dict): return False
        
        # Find a section to add to, or default to the first one.
        # A real implementation might specify the target section in `op.extra`.
        if "sections" not in bp or not bp["sections"]:
            bp["sections"] = [{"title": "Default Section", "clauses": []}]
        
        bp["sections"][0].setdefault("clauses", []).append(new_clause)
        return True
