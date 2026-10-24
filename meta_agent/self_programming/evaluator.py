from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, Optional

from meta_agent.self_programming.schema import CodePatchSet, TestReport
from meta_agent.self_programming.quality_evaluator import CodeQualityEvaluator, QualityMetrics


def _compute_test_pass_rate(test_report: Optional[TestReport]) -> Optional[float]:
    if not test_report or not test_report.results:
        return None
    total = len(test_report.results)
    if total == 0:
        return None
    passed = sum(1 for r in test_report.results if str(r.get("status")) == "passed")
    return passed / total


def _normalize_metrics(metrics: QualityMetrics) -> Dict[str, Any]:
    return asdict(metrics)


def evaluate_patch_set(
    patch_set: CodePatchSet,
    *,
    repo_root: str | Path,
    test_report: Optional[TestReport] = None,
    evaluator: Optional[CodeQualityEvaluator] = None,
) -> Dict[str, Any]:
    """
    Evaluate code quality for a patch set and return metrics suitable for MetricsStore.
    """
    quality_evaluator = evaluator or CodeQualityEvaluator()
    repo_root_path = Path(repo_root)

    file_metrics: Dict[str, QualityMetrics] = {}
    python_files = [f for f in patch_set.files if f.action != "delete" and f.file_path.endswith(".py")]

    for mod in python_files:
        path = repo_root_path / mod.file_path
        if path.exists():
            metrics = quality_evaluator.evaluate_file(path)
        else:
            metrics = quality_evaluator.evaluate_code(mod.new_content, file_path=mod.file_path)
        file_metrics[mod.file_path] = metrics

    test_pass_rate = _compute_test_pass_rate(test_report)

    if file_metrics:
        complexity_avg = sum(m.complexity_score for m in file_metrics.values()) / len(file_metrics)
        style_avg = sum(m.style_score for m in file_metrics.values()) / len(file_metrics)
        syntax_ratio = sum(1 for m in file_metrics.values() if m.syntax_valid) / len(file_metrics)
        overall_score = quality_evaluator._calculate_overall_score(
            syntax_score=syntax_ratio,
            complexity_score=complexity_avg,
            style_score=style_avg,
            test_pass_rate=test_pass_rate,
        )
    else:
        complexity_avg = 0.0
        style_avg = 0.0
        syntax_ratio = 0.0
        overall_score = 0.0

    return {
        "overall_score": overall_score,
        "test_pass_rate": test_pass_rate,
        "file_count": len(file_metrics),
        "syntax_ratio": syntax_ratio,
        "complexity_avg": complexity_avg,
        "style_avg": style_avg,
        "files": {path: _normalize_metrics(m) for path, m in file_metrics.items()},
        "notes": "no_python_files" if not file_metrics else "",
    }
