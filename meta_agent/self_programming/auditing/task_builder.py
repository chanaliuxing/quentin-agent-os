import json
from typing import List, Dict, Any
from pathlib import Path

from .templates import RequirementStatus


class RemediationTaskBuilder:
    """
    Build remediation tasks from audit report and delta.
    Pure rules, no LLM.
    """

    def __init__(self, max_tasks: int = 20):
        self.max_tasks = max_tasks

    def build(self, audit_results: List[RequirementStatus], delta: Dict[str, Any] | None = None) -> Dict[str, Any]:
        delta_map = {c.get("id"): c for c in (delta.get("status_changed", []) if delta else [])}
        tasks: List[Dict[str, Any]] = []

        # prioritize: regressions -> gap -> unknown -> partial
        status_rank = {"regression": 0, "gap": 1, "unknown": 2, "partial": 3}

        candidates: List[Dict[str, Any]] = []
        for r in audit_results:
            r_status = r.status
            reg = delta_map.get(r.req_id)
            is_regression = reg and reg.get("from") == "implemented" and reg.get("to") in ("gap", "partial")
            rank_status = "regression" if is_regression else r_status
            candidates.append({"req": r, "rank_status": rank_status})

        candidates.sort(key=lambda x: (status_rank.get(x["rank_status"], 99), x["req"].confidence, x["req"].req_id))

        for item in candidates[: self.max_tasks]:
            r = item["req"]
            task_type = self._infer_task_type(r)
            tasks.append(
                {
                    "req_id": r.req_id,
                    "title": r.title,
                    "status": r.status,
                    "confidence": r.confidence,
                    "task_type": task_type,
                    "module_hint": self._extract_module_hint(r),
                    "missing_items": r.missing_items,
                    "recommendation": self._recommend_action(task_type, r),
                }
            )

        return {"tasks": tasks}

    def _extract_module_hint(self, r: RequirementStatus) -> str:
        # module_hint is not stored directly; evidence may carry it in missing_items
        for mi in r.missing_items:
            if mi.startswith("missing_file:"):
                return mi.split("missing_file:", 1)[1]
        return ""

    def _infer_task_type(self, r: RequirementStatus) -> str:
        if any(mi.startswith("missing_file") for mi in r.missing_items):
            return "FIX_MODULE_HINT"
        if any(mi.startswith("missing_method") or mi.startswith("missing_function") for mi in r.missing_items):
            return "ADD_SYMBOL_STUB"
        if any(mi.startswith("missing_class") for mi in r.missing_items):
            return "ADD_SYMBOL_STUB"
        if any(ev.key == "placeholder_detected" for ev in r.evidence_chain):
            return "REPLACE_PLACEHOLDER"
        return "ADD_STRONG_EVIDENCE"

    def _recommend_action(self, task_type: str, r: RequirementStatus) -> str:
        if task_type == "FIX_MODULE_HINT":
            return "Fix module_hint or create the missing file."
        if task_type == "ADD_SYMBOL_STUB":
            return "Implement missing classes/methods/functions; add minimal runnable stubs if needed."
        if task_type == "REPLACE_PLACEHOLDER":
            return "Replace placeholder markers (pass/NotImplemented/...) with minimal working logic and add tests."
        return "Add strong evidence (tests_expected or runtime_signals) and flesh out implementation."
