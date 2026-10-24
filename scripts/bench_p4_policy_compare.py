import json
import os
from typing import Dict, Any

def compare_policies(baseline: Dict[str, Any], candidate: Dict[str, Any]) -> Dict[str, Any]:
    """
    Compare baseline and candidate metrics to identify improvements and regressions.
    """
    report = {
        "baseline": baseline,
        "candidate": candidate,
        "improvements": {},
        "regressions": {},
        "summary": "No significant changes"
    }
    
    metrics = ["cost", "latency_p95", "success_rate", "quality_score"]
    for m in metrics:
        b_val = baseline.get(m, 0)
        c_val = candidate.get(m, 0)
        
        if b_val == 0 and c_val == 0:
            continue
            
        diff = c_val - b_val
        percent_diff = (diff / b_val * 100) if b_val != 0 else 0
        
        if m in ["cost", "latency_p95"]:
            if diff < 0:
                report["improvements"][m] = {"diff": diff, "percent": percent_diff}
            elif diff > 0:
                report["regressions"][m] = {"diff": diff, "percent": percent_diff}
        else: # success_rate, quality_score
            if diff > 0:
                report["improvements"][m] = {"diff": diff, "percent": percent_diff}
            elif diff < 0:
                report["regressions"][m] = {"diff": diff, "percent": percent_diff}
    
    if report["improvements"] and not report["regressions"]:
        report["summary"] = "Net positive improvement without regressions."
    elif report["regressions"]:
        report["summary"] = f"Regressions detected in {list(report['regressions'].keys())}."
                
    return report

if __name__ == "__main__":
    # Mock data for demonstration of the benchmarking framework
    baseline_metrics = {"cost": 1.2, "latency_p95": 4500, "success_rate": 0.96, "quality_score": 0.85}
    candidate_metrics = {"cost": 0.8, "latency_p95": 3800, "success_rate": 0.97, "quality_score": 0.84}
    
    report = compare_policies(baseline_metrics, candidate_metrics)
    
    log_dir = "logs/bench/p4"
    os.makedirs(log_dir, exist_ok=True)
    report_path = os.path.join(log_dir, "comparison_report.json")
    
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2)
        
    print(f"Benchmarking report generated at {report_path}")
    print(f"Summary: {report['summary']}")
