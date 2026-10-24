from __future__ import annotations

from pathlib import Path
from typing import Any
from quentin.self_programming.eval_plugins.base import EvaluatorPlugin
from quentin.self_programming.skill_evaluator import SkillPatchEvaluator, PatchReport

class SkillTestsEvaluatorPlugin(EvaluatorPlugin):
    """
    Evaluator plugin that runs pytest verification (legacy SkillPatchEvaluator wrapper).
    """
    def __init__(self, priority: int = 100):
        self._priority = priority
        self._inner = SkillPatchEvaluator()

    @property
    def id(self) -> str:
        return "skill_tests"

    @property
    def priority(self) -> int:
        return self._priority

    def evaluate(self, patch: Any, repo_root: Path) -> PatchReport:
        # Note: SkillPatchEvaluator reads env vars for config
        return self._inner.evaluate(patch)
