from __future__ import annotations

from quentin.models.routing_policies.multi_agent_policy import MultiAgentRoutingPolicy
from quentin.routing.model_router import ModelInfo, ModelRouter, ModelUsageStats


def test_multi_agent_routing_policy_can_select_model() -> None:
    router = ModelRouter(
        repo_root=".",
        models={
            "m1": ModelInfo(name="m1", kind="openai", cost_per_1k_tokens=0.1, latency_hint_ms=100),
            "m2": ModelInfo(name="m2", kind="openai", cost_per_1k_tokens=1.0, latency_hint_ms=200),
        },
    )

    # Bias stats so multi-agent votes prefer m1 (cheaper + faster).
    router.stats["m1"] = ModelUsageStats(calls=10, total_latency_ms=1000, total_cost=1.0, total_tokens=1000)
    router.stats["m2"] = ModelUsageStats(calls=10, total_latency_ms=4000, total_cost=10.0, total_tokens=1000)

    policy = MultiAgentRoutingPolicy(router=router)
    info = policy.route(mode="core", task_type="generic", metadata={})
    assert info is not None
    assert info.name == "m1"

