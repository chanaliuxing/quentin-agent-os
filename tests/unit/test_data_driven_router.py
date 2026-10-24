import pytest

from quentin.llm.data_driven_router import DataDrivenModelRouter, RoutingWeights
from quentin.llm.datastore import ModelPerformanceDataStore


class _FakeClient:
    async def complete(self, prompt: str):
        return "ok"


def test_router_prefers_lower_cost_when_quality_equal(tmp_path):
    store = ModelPerformanceDataStore(tmp_path / "router.db")
    store.record_performance("cheap", "core", True, latency_sec=1.0, cost=0.1)
    store.record_performance("expensive", "core", True, latency_sec=1.0, cost=1.0)

    router = DataDrivenModelRouter(
        datastore=store,
        llm_clients={"cheap": _FakeClient(), "expensive": _FakeClient()},
        epsilon=0.0,
        model_priors={},
    )

    assert router.choose_model("core") == "cheap"


def test_router_weight_override_prefers_quality(tmp_path):
    store = ModelPerformanceDataStore(tmp_path / "router2.db")
    store.record_performance("cheap", "core", False, latency_sec=1.0, cost=0.1)
    store.record_performance("premium", "core", True, latency_sec=1.0, cost=1.0)
    # boost premium success rate
    store.record_performance("premium", "core", True, latency_sec=1.0, cost=1.0)

    router = DataDrivenModelRouter(
        datastore=store,
        llm_clients={"cheap": _FakeClient(), "premium": _FakeClient()},
        epsilon=0.0,
        weights=RoutingWeights(success=2.0, latency=-0.1, cost=-0.05),
    )

    assert router.choose_model("core") == "premium"
