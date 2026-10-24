# scripts/test_council_patch_governance.py
import json

from meta_agent.runtime import council


def main():
    # 随便构造一点 patch_report / metrics 用来测试
    patch_report = {
        "patch_id": "demo-001",
        "target_module": "memory.fabric",
        "pass_rate_before": 0.72,
        "pass_rate_after": 0.78,
        "regression_cases": [],
    }
    immune = {
        "has_critical_risks": False,
        "notes": "No security violations detected on sandbox tests.",
    }
    metrics = {
        "task_success_rate_7d": 0.81,
        "error_rate_7d": 0.05,
    }

    schema_hint = """
    输出 JSON 形如：
    {
      "decision": "accept" | "reject" | "needs_human_review",
      "risk_level": "low" | "medium" | "high",
      "reason": "简短中文理由（不超过 3 句）",
      "notes": "可选的补充说明，可以为空字符串"
    }
    """

    ctx = {
        "patch_report": patch_report,
        "immune": immune,
        "metrics": metrics,
    }

    res = council.ask_json(
        role="patch_governance",
        question="请审查这个 patch 是否可以在 sandbox 自动应用？",
        context=ctx,
        json_schema_hint=schema_hint,
    )

    print(json.dumps(res, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()