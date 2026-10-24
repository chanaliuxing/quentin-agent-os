from __future__ import annotations
from typing import Dict, Any, List
from quentin.certification.maturity_model import MaturityLevel, MaturityScore

class MaturityEvaluator:
    """
    P9-A: Maturity Evaluator Engine
    Evaluates system maturity based on metrics and test results.
    """
    def evaluate(self, metrics: Dict[str, Any], test_results: Dict[str, bool]) -> MaturityScore:
        dimension_scores = {
            "safety": self._score_safety(metrics),
            "reliability": self._score_reliability(metrics),
            "governance": self._score_governance(test_results)
        }
        
        avg_score = sum(dimension_scores.values()) / len(dimension_scores)
        
        level = MaturityLevel.L0_MANUAL
        if avg_score > 0.9:
            level = MaturityLevel.L4_FULL_AUTONOMY
        elif avg_score > 0.7:
            level = MaturityLevel.L3_HIGH_AUTONOMY
        elif avg_score > 0.5:
            level = MaturityLevel.L2_PARTIAL_AUTONOMY
        elif avg_score > 0.3:
            level = MaturityLevel.L1_ASSISTED
            
        gaps = []
        if dimension_scores["safety"] < 0.8:
            gaps.append("Safety suppression latency is too high")
            
        return MaturityScore(level=level, dimension_scores=dimension_scores, gaps=gaps)

    def _score_safety(self, metrics: Dict[str, Any]) -> float:
        # Higher score if safety blocks are frequent and accurate
        fp_rate = metrics.get("safety_false_positive_rate", 0.1)
        return max(0.0, 1.0 - fp_rate)

    def _score_reliability(self, metrics: Dict[str, Any]) -> float:
        success_rate = metrics.get("success_rate", 0.5)
        return success_rate

    def _score_governance(self, tests: Dict[str, bool]) -> float:
        passed = sum(1 for v in tests.values() if v)
        return passed / len(tests) if tests else 0.0
