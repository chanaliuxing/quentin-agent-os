import json

from quentin.models.router import ModelRouter, ModelInfo


def test_model_router_consumes_optimizer_rules(tmp_path) -> None:
    (tmp_path / "config").mkdir(parents=True, exist_ok=True)
    rules = {
        "speed::generic": {
            "mode": "speed",
            "task_type": "generic",
            "model": "m2",
            "provider": "ollama",
            "metric": "score",
            "score": 1.0,
            "success_rate": 1.0,
            "avg_latency_ms": 1.0,
            "avg_model_score": 1.0,
        }
    }
    (tmp_path / "config" / "model_router_rules.json").write_text(json.dumps(rules), encoding="utf-8")

    router = ModelRouter(
        models={
            "m1": ModelInfo(name="m1", kind="ollama"),
            "m2": ModelInfo(name="m2", kind="ollama"),
        },
        rules_path=tmp_path / "config" / "model_router_rules.json",
    )

    assert router.choose_model(task_type="generic", preference="speed") == "m2"

