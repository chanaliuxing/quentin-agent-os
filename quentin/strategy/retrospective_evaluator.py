from __future__ import annotations
from typing import Dict, Any, List

class RetrospectiveEvaluator:
    """
    P10-B: Strategy Retrospective Evaluator
    Performs cross-cycle analysis of strategic outcomes.
    """
    def evaluate_period(self, roadmap_data: Dict[str, Any], metric_trends: Dict[str, List[float]]) -> Dict[str, Any]:
        """
        Analyze what worked and what regressed in the last quarter.
        """
        completed = roadmap_data.get("completed_milestones", 0)
        total = roadmap_data.get("total_milestones", 1)
        
        success_rate = completed / total
        
        # Trend analysis
        perf_trend = "improving" if sum(metric_trends.get("success_rate", [])) / len(metric_trends.get("success_rate", [1])) > 0.9 else "stable"
        
        return {
            "period_summary": f"Milestone completion at {success_rate:.1%}. Performance is {perf_trend}.",
            "strategic_pivot_recommended": success_rate < 0.5
        }
