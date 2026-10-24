from pathlib import Path

from quentin.kernel.safety import SafetyKernel
from quentin.l3.research.interface import ResearchInterfaceV3
from quentin.routing.model_router import ModelRouter
from quentin.runtime.system import build_default_runtime


def test_full_l3_l2_l1_feedback_loop(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("QUENTIN_KVSTORE_PATH", str(tmp_path / "kv.sqlite3"))

    baseline_model = "qwen3-vl:latest"
    candidate_model = "deepseek-r1:1.5b"
    route_key = "balanced::chat"

    research = ResearchInterfaceV3(
        repo_root=str(tmp_path),
        domain="desktop",
        environment="sandbox",
        risk_level="medium",
        safety_kernel=SafetyKernel(),
    )

    exp = research.create_experiment(
        {
            "name": "e2e",
            "description": "feedback loop",
            "target_type": "model_router",
            "metrics": ["success_rate"],
            "variants": [
                {"variant_id": "baseline", "name": "baseline", "params": {"route_key": route_key, "model": baseline_model}},
                {"variant_id": "candidate", "name": "candidate", "params": {"route_key": route_key, "model": candidate_model}},
            ],
        }
    )
    exp_id = exp["experiment_id"]

    run = research.run_experiment(
        exp_id,
        cases=[
            {
                "case_id": "c1",
                "description": "route chat model",
                "input_payload": {"prompt": "hello"},
                "expected_keywords": [candidate_model],
                "pass_threshold": 1.0,
                "meta": {},
            }
        ],
    )
    assert run["status"] == "completed"
    assert run["variant_results"]["candidate"]["success_rate"] > run["variant_results"]["baseline"]["success_rate"]

    promo = research.decide_and_promote_variant(
        exp_id,
        promote_policy={
            "metric": "success_rate",
            "min_delta": 0.01,
            "apply": True,
            "rules_path": "data/research/rules.json",
            "human_approved": True,
        },
    )
    assert promo["ok"] is True
    assert promo["applied"] is True

    router = ModelRouter(repo_root=tmp_path, rules_path=tmp_path / "data/research/rules.json")
    runtime = build_default_runtime(repo_root=tmp_path, llm=router, council=None, enable_self_programming=False)
    result = runtime.run_task("hello", {"domain": "general"})
    assert result.status == "success"
    out = result.output or {}
    assert isinstance(out, dict)
    assert "goal_id" in out or "final_output" in out or "raw_output" in out
