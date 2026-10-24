import json
from quentin.explainability.report_schema import AuditReport

def main():
    # Mock data for report generation
    report = AuditReport(
        report_id="audit-2026-Q1",
        period_start="2026-01-01",
        period_end="2026-03-31",
        total_events=150,
        risk_summary={"high": 5, "medium": 20, "low": 125},
        violations=[{"id": "v1", "policy": "no_root_access"}]
    )
    
    print(report.to_json())

if __name__ == "__main__":
    main()
