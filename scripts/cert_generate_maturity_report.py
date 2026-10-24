import json
import os
from quentin.certification.maturity_evaluator import MaturityEvaluator

def main():
    evaluator = MaturityEvaluator()
    
    # Mock data
    metrics = {"safety_false_positive_rate": 0.02, "success_rate": 0.95}
    tests = {"p5_security_audit": True, "p7_org_governance": True, "p8_safe_halt": True}
    
    score = evaluator.evaluate(metrics, tests)
    
    report = {
        "level": score.level.name,
        "dimensions": score.dimension_scores,
        "gaps": score.gaps
    }
    
    log_dir = "logs/certification/maturity"
    os.makedirs(log_dir, exist_ok=True)
    with open(f"{log_dir}/maturity_report.json", "w") as f:
        json.dump(report, f, indent=2)
        
    print(f"Maturity Report generated: {report['level']}")

if __name__ == "__main__":
    main()
