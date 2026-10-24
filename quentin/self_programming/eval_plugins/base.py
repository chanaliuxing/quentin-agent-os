from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable
from quentin.self_programming.skill_evaluator import PatchReport

@runtime_checkable
class EvaluatorPlugin(Protocol):
    """
    Interface for pluggable evaluators (P3-B).
    """
    @property
    def id(self) -> str: ...

    @property
    def priority(self) -> int: ...

    def evaluate(self, patch: Any, repo_root: Path) -> PatchReport:
        """
        Run evaluation on a patch proposal.
        """
        ...


class EvaluatorRegistry:
    """
    Registry for evaluator plugins.
    """
    def __init__(self) -> None:
        self._plugins: Dict[str, EvaluatorPlugin] = {}

    def register(self, plugin: EvaluatorPlugin) -> None:
        self._plugins[plugin.id] = plugin

    def list_plugins(self) -> List[EvaluatorPlugin]:
        return sorted(self._plugins.values(), key=lambda p: -p.priority)

    def run_all(self, patch: Any, repo_root: Path) -> List[PatchReport]:
        """
        Run all registered evaluators and collect reports.
        """
        reports = []
        for p in self.list_plugins():
            try:
                reports.append(p.evaluate(patch, repo_root))
            except Exception as e:
                from quentin.self_programming.skill_evaluator import PatchStatus
                reports.append(PatchReport(
                    patch_id=getattr(patch, "id", "unknown"),
                    status=PatchStatus.FAIL,
                    metrics={"error": str(e)},
                    summary=f"Evaluator {p.id} failed: {e}"
                ))
        return reports

# Global registry
_registry = EvaluatorRegistry()

def get_evaluator_registry() -> EvaluatorRegistry:
    return _registry
