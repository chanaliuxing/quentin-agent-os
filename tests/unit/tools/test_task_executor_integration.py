from meta_agent.memory.fabric import MemoryFabric
from meta_agent.memory.store_sqlite import SqliteMemoryStore
from meta_agent.runtime.task_executor import TaskExecutor
from meta_agent.self_programming.mcp_integration.invoker import ToolInvocationResult
from meta_agent.tools.registry import ToolRegistration, ToolRegistry, ToolLifecycle
from meta_agent.tools.lifecycle import ToolLifecycleManager
from meta_agent.runtime.council_runtime import CouncilRuntime
from meta_agent.tools.governance import CouncilBackedToolGate


class FakeInvoker:
    def __init__(self, output=None, success=True):
        self.output = output or {"ok": True}
        self.success = success

    def invoke(self, server, tool_name, arguments):
        return ToolInvocationResult(success=self.success, output=self.output, latency_ms=5.0, error=None)


def test_task_executor_records_tool_usage(tmp_path):
    store = SqliteMemoryStore(db_path=tmp_path / "mem.db")
    fabric = MemoryFabric(store=store)

    registry = ToolRegistry()
    registry.register(
        ToolRegistration(
            tool_id="stub/echo",
            server="stub",
            description="Echo",
            signature="echo(text: str)",
            uri="./stub",
        )
    )

    invoker = FakeInvoker(output={"echo": "hi"})
    executor = TaskExecutor(
        tool_registry=registry,
        tool_invoker=invoker,
        memory_fabric=fabric,
        sync_tool_knowledge=True,
    )

    plan = {"steps": [{"type": "call_tool", "tool_id": "stub/echo", "args": {"text": "hi"}}]}
    res = executor.execute_plan(task={"id": "t1", "description": "call echo"}, plan=plan)

    assert res["success"] is True
    records = store.search("", kind="tool_knowledge", limit=5)
    assert records
    meta = records[0].metadata
    assert meta["tool_id"] == "stub/echo"
    assert meta["examples"][0]["input"]["text"] == "hi"


class FakeCouncil(CouncilRuntime):
    async def ask_json(self, role, question, context, json_schema_hint):
        return {"decision": "approve", "rationale": "ok"}

    async def deliberate(self, task):
        class R:
            raw_planner = "p"
            raw_critic = "c"
            raw_judge = "j"
            final_json = {"decision": "approve", "rationale": "ok"}

        return R()


def test_lifecycle_manager_records_decision(tmp_path):
    store = SqliteMemoryStore(db_path=tmp_path / "mem.db")
    fabric = MemoryFabric(store=store)
    registry = ToolRegistry()
    registry.register(
        ToolRegistration(
            tool_id="stub/echo",
            server="stub",
            description="Echo",
            signature="echo(text: str)",
        )
    )
    council = FakeCouncil()
    gate = CouncilBackedToolGate(council=council)
    manager = ToolLifecycleManager(registry=registry, gate=gate, memory_fabric=fabric)

    ok = manager.upgrade_to_trusted("stub/echo")
    assert ok is True
    records = store.search("", kind="tool_lifecycle_decision", limit=2)
    assert records
    meta = records[0].metadata
    assert meta["tool_id"] == "stub/echo"
    assert meta["target_state"] == ToolLifecycle.TRUSTED.value
