# quentin/self_programming/skill_evaluator.py
from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
from typing import Union

from meta_agent.patches.models import PatchProposal, BlueprintPatchProposal
from pathlib import Path
import os
import subprocess
import time

class PatchStatus(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    NEEDS_REVIEW = "needs_review"

@dataclass
class PatchReport:
    """ Report from evaluating a patch. """
    patch_id: str
    status: PatchStatus
    metrics: dict
    summary: str = ""

class PatchEvaluator:
    """ Base class for evaluating different kinds of patches. """
    def __init__(self, use_plugins: bool = True):
        self._use_plugins = use_plugins
        if use_plugins and os.getenv("QUENTIN_EVAL_PLUGINS_ENABLED") == "1":
            from quentin.self_programming.eval_plugins import bootstrap_evaluators
            bootstrap_evaluators()

    def evaluate(self, patch: Union[PatchProposal, BlueprintPatchProposal]) -> PatchReport:
        if self._use_plugins and os.getenv("QUENTIN_EVAL_PLUGINS_ENABLED") == "1":
            from quentin.self_programming.eval_plugins import get_evaluator_registry
            registry = get_evaluator_registry()
            reports = registry.run_all(patch, Path("."))
            if reports:
                # Merge logic could be complex; for now, pick the most significant
                # or just return the first one if it's not a generic pass.
                for r in reports:
                    if r.status != PatchStatus.PASS:
                        return r
                return reports[0]

        if isinstance(patch, BlueprintPatchProposal):
            return self._evaluate_blueprint_patch(patch)
        elif isinstance(patch, PatchProposal):
            return self._evaluate_code_patch(patch)
        else:
            raise TypeError(f"Unsupported patch type: {type(patch)}")

    def _evaluate_code_patch(self, patch: PatchProposal) -> PatchReport:
        raise RuntimeError("PatchEvaluator is abstract; use a concrete evaluator implementation.")

    def _evaluate_blueprint_patch(self, patch: BlueprintPatchProposal) -> PatchReport:
        """
        Performs logical consistency and conflict detection for blueprint patches.
        """
        issues = []
        ops = getattr(patch, "operations", None) or []
        if not ops:
            issues.append("no_operations")
        for op in ops:
            if not getattr(op, "op_type", None) or not getattr(op, "target_clause_id", None):
                issues.append("invalid_operation")
                break

        if issues:
            return PatchReport(
                patch_id=patch.id,
                status=PatchStatus.NEEDS_REVIEW,
                metrics={"consistency_check": 0.0, "issues": issues},
                summary=f"Blueprint patch requires review: {', '.join(issues)}",
            )

        return PatchReport(
            patch_id=patch.id,
            status=PatchStatus.PASS,
            metrics={"consistency_check": 1.0},
            summary="Blueprint patch passed basic consistency checks.",
        )

class SkillPatchEvaluator(PatchEvaluator):
    """ Evaluates patches related to skill implementations. """
    def __init__(self):
        super().__init__(use_plugins=False)

    def _evaluate_code_patch(self, patch: PatchProposal) -> PatchReport:
        """
        Runs tests and other checks for a skill code patch.
        """
        run_tests = os.environ.get("QUENTIN_SELF_PROG_EVAL_RUN_TESTS", "").strip().lower() in ("1", "true", "yes", "on")
        test_cmd = os.environ.get("QUENTIN_SELF_PROG_EVAL_TEST_CMD", "pytest -q")
        timeout_sec = int(os.environ.get("QUENTIN_SELF_PROG_EVAL_TEST_TIMEOUT_SEC", "300"))

        if not run_tests:
            return PatchReport(
                patch_id=patch.id,
                status=PatchStatus.NEEDS_REVIEW,
                metrics={"tests_ran": 0, "reason": "tests_disabled"},
                summary="Patch evaluation requires human review (tests disabled by default).",
            )

        start = time.perf_counter()
        try:
            proc = subprocess.run(
                test_cmd,
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=timeout_sec,
                check=False,
            )
        except Exception as e:  # noqa: BLE001
            return PatchReport(
                patch_id=patch.id,
                status=PatchStatus.FAIL,
                metrics={"tests_ran": 1, "error": repr(e)},
                summary="Patch evaluation failed to run tests.",
            )

        dur = time.perf_counter() - start
        ok = proc.returncode == 0
        return PatchReport(
            patch_id=patch.id,
            status=PatchStatus.PASS if ok else PatchStatus.FAIL,
            metrics={
                "tests_ran": 1,
                "ok": ok,
                "returncode": proc.returncode,
                "duration_sec": dur,
                "stdout_preview": proc.stdout.decode("utf-8", errors="ignore")[:2000],
                "stderr_preview": proc.stderr.decode("utf-8", errors="ignore")[:2000],
                "cmd": test_cmd,
            },
            summary="All tests passed." if ok else "Some tests failed.",
        )
