import json
import os
from typing import List, Optional, Tuple

from .collector import StaticEvidenceCollector
from .scorer import CapabilityScorer
from .templates import RequirementStatus, Evidence
from .ast_index import ASTIndex
from .tests_runner import TestEvidenceCollector
from .runtime_collector import RuntimeEvidenceCollector


class BlueprintAuditor:
    """
    Evidence-based auditor (P0):
    - Loads spec requirements
    - Uses static code evidence (AST, file existence, placeholders) + legacy capabilities snapshot
    - Scores to four states: implemented / partial / unknown / gap
    """

    def __init__(self, project_root: str):
        self.project_root = project_root
        self.ast_index = ASTIndex(project_root)
        self.collector = StaticEvidenceCollector(project_root, self.ast_index)
        self.scorer = CapabilityScorer()

    def audit_spec(
        self,
        spec_path: str,
        capability_snapshot_path: Optional[str] = None,
        run_tests: bool = False,
        runtime_events_dir: Optional[str] = None,
    ) -> Tuple[List[RequirementStatus], List[str], List[str]]:
        """
        Returns (results, warnings, errors).
        """
        results: List[RequirementStatus] = []
        warnings: List[str] = []
        errors: List[str] = []
        test_runner = TestEvidenceCollector() if run_tests else None
        runtime_collector = RuntimeEvidenceCollector(runtime_events_dir) if runtime_events_dir else None

        # 1) Load spec
        if not os.path.exists(spec_path):
            errors.append("SPEC_NOT_FOUND")
            return results, warnings, errors
        try:
            with open(spec_path, "r", encoding="utf-8") as f:
                spec_data = json.load(f)
                requirements = spec_data.get("requirements", [])
        except Exception as e:
            errors.append(f"SPEC_PARSE_ERROR: {e}")
            return results, warnings, errors
        for req in requirements:
            if not req.get("id") or not req.get("title"):
                warnings.append(f"REQ_INVALID: missing id/title for requirement: {req}")
            mh = req.get("module_hint")
            if mh and (".." in mh or mh.startswith("/")):
                warnings.append(f"REQ_INVALID: module_hint must be relative (no '..' or absolute): {mh}")
            if not req.get("symbols_expected"):
                warnings.append(f"REQ_WEAK: symbols_expected empty for requirement {req.get('id')}")

        # 2) Legacy capability snapshot
        implemented_ids = set()
        if capability_snapshot_path and os.path.exists(capability_snapshot_path):
            try:
                with open(capability_snapshot_path, "r", encoding="utf-8") as f:
                    cap_data = json.load(f)
                    for item in cap_data.get("capabilities", []):
                        if item.get("implemented") or item.get("status") in ("done", "ok", "implemented"):
                            cid = item.get("id") or item.get("capability_id")
                            if cid:
                                implemented_ids.add(cid)
                    implemented_ids.update(cap_data.get("implemented_ids", []))
                    implemented_ids.update(cap_data.get("implemented", {}).keys())
            except Exception as e:
                warnings.append(f"CAPABILITIES_PARSE_ERROR: {e}")

        # sort requirements by id for stable output
        requirements = sorted(requirements, key=lambda r: r.get("id", ""))

        # 3) Per requirement
        for req in requirements:
            evidences: List[Evidence] = []
            missing_items: List[str] = []

            if req.get("id") in implemented_ids:
                evidences.append(Evidence("config", "legacy_implemented", 0.2, "Marked as implemented in snapshot"))

            ev, missing = self.collector.collect(req)
            evidences.extend(ev)
            missing_items.extend(missing)

            tests_expected = req.get("tests_expected") or []
            if run_tests and tests_expected and test_runner:
                evidences.extend(test_runner.run(tests_expected))

            if runtime_collector:
                evidences.extend(runtime_collector.collect(req))

            status, confidence = self.scorer.evaluate(evidences)

            results.append(
                RequirementStatus(
                    req_id=req.get("id", ""),
                    title=req.get("title", req.get("id", "")),
                    status=status,
                    confidence=confidence,
                    evidence_chain=evidences,
                    missing_items=missing_items,
                )
            )

        return results, warnings, errors

    def save_report(self, results: List[RequirementStatus], output_path: str, warnings: Optional[List[str]] = None, errors: Optional[List[str]] = None) -> None:
        report_data = {
            "summary": {
                "total": len(results),
                "implemented": len([r for r in results if r.status == "implemented"]),
                "partial": len([r for r in results if r.status == "partial"]),
                "unknown": len([r for r in results if r.status == "unknown"]),
                "gap": len([r for r in results if r.status == "gap"]),
                "warnings": warnings or [],
                "errors": errors or [],
            },
            "details": [r.to_dict() for r in results],
        }
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(report_data, f, ensure_ascii=False, indent=2)
        print(f"Audit report saved to: {output_path}")
