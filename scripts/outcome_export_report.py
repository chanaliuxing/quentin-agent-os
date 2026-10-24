import json
import os
from quentin.analytics.outcome_metrics import OutcomeMetrics
from quentin.analytics.roi_estimator import ROIEstimator

def main():
    estimator = ROIEstimator()
    
    # Mock data for Q1
    m1 = OutcomeMetrics(domain="core", activity_count=1000, success_rate=0.98, time_saved_hours=200, cost_reduction_usd=500, risk_suppression_count=50)
    m2 = OutcomeMetrics(domain="web", activity_count=500, success_rate=0.95, time_saved_hours=50, cost_reduction_usd=100, risk_suppression_count=10)
    
    report = {
        "summary": "Organizational ROI Report",
        "details": [
            estimator.estimate_roi(m1),
            estimator.estimate_roi(m2)
        ]
    }
    
    log_dir = "logs/outcome"
    os.makedirs(log_dir, exist_ok=True)
    with open(f"{log_dir}/roi_report_q1.json", "w") as f:
        json.dump(report, f, indent=2)
        
    print(f"Outcome Report generated in {log_dir}/roi_report_q1.json")

if __name__ == "__main__":
    main()
