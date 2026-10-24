import pytest


@pytest.mark.asyncio
async def test_model_router_async_apis_accept_sync_backend_call(tmp_path):
    from quentin.routing.model_router import ModelRouter, ModelInfo

    calls = {"n": 0}

    def backend_call(model_id, messages, meta):
        calls["n"] += 1
        assert isinstance(messages, list)
        assert isinstance(meta, dict)
        return "ok-sync-backend"

    router = ModelRouter(repo_root=tmp_path, backend_call=backend_call)
    router.register_model(ModelInfo(name="dummy-model", kind="openai"))

    out1 = await router.call_best_model(task_type="chat", prompt="hi", preferred_model="dummy-model")
    assert out1 == "ok-sync-backend"

    out2 = await router.choose_and_call(route_info={"domain": "core"}, messages=[{"role": "user", "content": "hi"}])
    assert out2 == "ok-sync-backend"
    assert calls["n"] >= 2

