from __future__ import annotations

from pathlib import Path
from quentin.self_programming.eval_plugins.base import (
    EvaluatorPlugin,
    EvaluatorRegistry,
    get_evaluator_registry,
)
from quentin.self_programming.eval_plugins.skill_tests import SkillTestsEvaluatorPlugin

_bootstrapped = False

def bootstrap_evaluators(registry: EvaluatorRegistry = None) -> EvaluatorRegistry:
    global _bootstrapped
    if _bootstrapped:
        return registry or get_evaluator_registry()
        
    if registry is None:
        registry = get_evaluator_registry()
    
    _bootstrapped = True
    registry.register(SkillTestsEvaluatorPlugin())
    return registry

__all__ = [
    "EvaluatorPlugin",
    "EvaluatorRegistry",
    "get_evaluator_registry",
    "bootstrap_evaluators",
]
