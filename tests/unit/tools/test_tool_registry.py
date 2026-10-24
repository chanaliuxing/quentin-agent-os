from meta_agent.memory.fabric import MemoryFabric
from meta_agent.memory.store_sqlite import SqliteMemoryStore
from meta_agent.memory.tool_knowledge import ToolKnowledge
from meta_agent.memory.types import MemoryTier
from meta_agent.tools.bootstrap import bootstrap_registry
from meta_agent.tools.governance import ToolCouncilGate, guarded_update_lifecycle
from meta_agent.tools.knowledge_sync import record_tool_usage, sync_registry_to_memory
from meta_agent.tools.registry import RiskLevel, ToolGovernance, ToolLifecycle, ToolRegistration, ToolRegistry


def test_bootstrap_registry_dedupes_and_merges_memory_and_registry_index() -> None:
    registry_index = [
        {
            "server_id": "server-a",
            "tools": [
                {
                    "name": "echo",
                    "description": "Echo text",
                    "signature": "echo(text: str)",
                    "risk_level": "low",
                }
            ],
        }
    ]

    memory_tool = ToolKnowledge(
        tool_id="server-a/echo",
        server="server-a",
        signature="echo(text: str)",
        description="Echo tool from memory",
    ).to_memory_record(MemoryTier.LTS)

    def memory_search(query: str, tiers=None, kind=None, limit: int = 200):
        return [memory_tool]

    registry = bootstrap_registry(registry_index=registry_index, memory_search=memory_search)
    tools = registry.list()

    # Deduped by tool_id
    assert len([t for t in tools if t.tool_id == "server-a/echo"]) == 1
    reg = registry.get("server-a/echo")
    assert reg is not None
    assert reg.governance.lifecycle == ToolLifecycle.EXPERIMENTAL


def test_guarded_update_lifecycle_blocks_high_risk_trusted_upgrade() -> None:
    registry = ToolRegistry()
    registration = ToolRegistration(
        tool_id="dangerous/write",
        server="fs",
        description="Writes to filesystem",
        signature="write(path: str, content: str)",
        governance=ToolGovernance(risk_level=RiskLevel.HIGH),
    )
    registry.register(registration)

    gate = ToolCouncilGate()
    ok = guarded_update_lifecycle(registry, "dangerous/write", ToolLifecycle.TRUSTED, gate)
    assert ok is False
    assert registry.get("dangerous/write").governance.lifecycle == ToolLifecycle.EXPERIMENTAL

    ok = guarded_update_lifecycle(registry, "dangerous/write", ToolLifecycle.DEPRECATED, gate)
    assert ok is True
    assert registry.get("dangerous/write").governance.lifecycle == ToolLifecycle.DEPRECATED


def test_sync_registry_to_memory(tmp_path) -> None:
    registry = ToolRegistry()
    registry.register(
        ToolRegistration(
            tool_id="fs/write",
            server="fs",
            description="Write file",
            signature="write(path: str, content: str)",
        )
    )

    store = SqliteMemoryStore(db_path=tmp_path / "mem.db")
    fabric = MemoryFabric(store=store)

    written = sync_registry_to_memory(registry, fabric)
    assert written == 1

    records = store.search("", kind="tool_knowledge", limit=5)
    assert records
    assert records[0].id.startswith("tool_knowledge::")


def test_record_tool_usage(tmp_path) -> None:
    registry = ToolRegistry()
    registry.register(
        ToolRegistration(
            tool_id="http/get",
            server="http",
            description="HTTP GET",
            signature="get(url: str)",
        )
    )
    registry.record_invocation("http/get", success=True, latency_ms=50)

    store = SqliteMemoryStore(db_path=tmp_path / "mem.db")
    fabric = MemoryFabric(store=store)

    record_tool_usage(
        registry,
        fabric,
        "http/get",
        arguments={"url": "https://example.com"},
        output={"status": 200},
        error=None,
        success=True,
    )

    recs = store.search("", kind="tool_knowledge", limit=2)
    assert recs
    meta = recs[0].metadata
    assert meta["tool_id"] == "http/get"
    assert meta["examples"][0]["input"]["url"] == "https://example.com"
    assert "success=True" in recs[0].text
