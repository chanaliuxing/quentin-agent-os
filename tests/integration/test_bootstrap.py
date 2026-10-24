import pytest
from pathlib import Path
from quentin.config.settings import Settings
from quentin.bootstrap.container import Container
from quentin.infra.storage.kv_store import KVStore
from quentin.memory.fabric import MemoryFabric
from quentin.cognitive.loop import CognitiveLoop
from meta_agent.self_programming.engine_v2 import SelfProgrammingEngineV2
from quentin.observability.service import ObservabilityService


class TestBootstrap:
    @pytest.fixture
    def settings(self):
        # Create a dummy Settings object
        s = Settings()
        return s

    @pytest.fixture
    def container(self, settings):
        return Container(settings=settings)

    def test_container_initializes_core_components(self, container):
        assert container.tracer is not None
        assert container.kv_store is not None
        assert isinstance(container.kv_store, KVStore)
        assert container.safety_kernel is not None
        assert container.memory_fabric is not None
        assert isinstance(container.memory_fabric, MemoryFabric)
        assert container.model_router is not None
        assert container.cognitive_loop is not None
        assert isinstance(container.cognitive_loop, CognitiveLoop)
        assert container.immune_loop is not None
        assert container.executor is not None
        assert container.tool_manager is not None
        assert container.sleep_loop is not None
        assert container.observability_service is not None
        assert isinstance(container.observability_service, ObservabilityService)

        # Check self_programming engine specifically
        assert container.self_programming_engine is not None
        assert isinstance(container.self_programming_engine, SelfProgrammingEngineV2)

    def test_container_provides_singletons(self, container):
        # Request the same component multiple times and check if it's the same instance
        tracer1 = container.tracer
        tracer2 = container.tracer
        assert tracer1 is tracer2

        kv_store1 = container.kv_store
        kv_store2 = container.kv_store
        assert kv_store1 is kv_store2

        loop1 = container.cognitive_loop
        loop2 = container.cognitive_loop
        assert loop1 is loop2
