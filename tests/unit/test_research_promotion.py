from pathlib import Path

from quentin.kernel.safety import SafetyKernel
from quentin.l3.research.interface import ResearchInterfaceV3
from quentin.l3.research.experiment_orchestrator import RunRecord
from quentin.routing.model_router import ModelRouter


def test_decide_and_promote_writes_model_router_rules(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("QUENTIN_KVSTORE_PATH", str(tmp_path / "kv.sqlite3"))

    iface = ResearchInterfaceV3(
        repo_root=str(tmp_path),
        domain="desktop",
        environment="sandbox",
        risk_level="medium",
        safety_kernel=SafetyKernel(),
    )

    exp = iface.create_experiment(
        {
            "name": "router_promo",
            "description": "test promotion",
            "target_type": "model_router",
            "metrics": ["success_rate"],
            "variants": [
                {
                    "variant_id": "baseline",
                    "name": "baseline",
                    "params": {"route_key": "balanced::chat", "model": "qwen3-vl:latest"},
                },
                {
                    "variant_id": "candidate",
                    "name": "candidate",
                    "params": {"route_key": "balanced::chat", "model": "deepseek-r1:1.5b"},
                },
            ],
        }
    )
    exp_id = exp["experiment_id"]

    # Inject a completed run result (avoid relying on evaluators).
    # Create a run record id and persist it into orchestrator store.
    run_id = "run_test"
    rr = RunRecord(
        run_id=run_id,
        experiment_id=exp_id,
        status="completed",
        variant_results={
            "baseline": {"success_rate": 0.4, "avg_cost_tokens": 10.0},
            "candidate": {"success_rate": 0.7, "avg_cost_tokens": 10.0},
        },
        cases=[],
    )
    # Use orchestrator internals for storage.
    import asyncio

    asyncio.run(iface.orchestrator._save_run(rr))  # type: ignore[attr-defined]

    res = iface.decide_and_promote_variant(
        exp_id,
        promote_policy={
            "metric": "success_rate",
            "min_delta": 0.01,
            "apply": True,
            "rules_path": "rules.json",
            "human_approved": True,
        },
    )
    assert res["ok"] is True
    assert res["applied"] is True

    router = ModelRouter(repo_root=tmp_path, rules_path=tmp_path / "rules.json")
    chosen = router.choose_model(task_type="chat", preference="balanced")
    assert chosen == "deepseek-r1:1.5b"
