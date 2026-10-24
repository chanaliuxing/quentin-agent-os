from __future__ import annotations

from quentin.memory.fabric import MemoryFabric
from quentin.memory.tool_knowledge import stable_tool_knowledge_id
from quentin.tools.usage.tool_knowledge_sink import ToolKnowledgeUsageSink


def test_tool_knowledge_sink_writes_and_updates_stats(tmp_path) -> None:
    fabric = MemoryFabric(repo_root=tmp_path, db_path=":memory:")
    sink = ToolKnowledgeUsageSink(memory_fabric=fabric)

    sink.record(
        tool_name="fs.read_file",
        arguments={"path": "README.md"},
        result={"status": "ok", "result": "x"},
        success=True,
        latency_ms=10,
        tool_spec=None,
    )
    rec_id = stable_tool_knowledge_id("fs.read_file")
    rec = fabric.store.get(rec_id)
    assert rec is not None
    assert rec.kind == "tool_knowledge"
    assert rec.metadata["tool_name"] == "fs.read_file"
    assert rec.metadata["stats"]["call_count"] == 1

    sink.record(
        tool_name="fs.read_file",
        arguments={"path": "README.md"},
        result={"status": "ok", "result": "y"},
        success=True,
        latency_ms=20,
        tool_spec=None,
    )
    rec2 = fabric.store.get(rec_id)
    assert rec2 is not None
    assert rec2.metadata["stats"]["call_count"] == 2
    assert float(rec2.metadata["stats"]["success_rate"]) == 1.0


def test_stable_tool_knowledge_id_is_deterministic() -> None:
    assert stable_tool_knowledge_id("x") == stable_tool_knowledge_id("x")


def test_tool_knowledge_sink_records_failure_and_degrades_success_rate(tmp_path) -> None:
    fabric = MemoryFabric(repo_root=tmp_path, db_path=":memory:")
    sink = ToolKnowledgeUsageSink(memory_fabric=fabric)
    rec_id = stable_tool_knowledge_id("mcp.demo.tool")

    sink.record(
        tool_name="mcp.demo.tool",
        arguments={"x": 1},
        result={"status": "ok", "result": {"ok": True}},
        success=True,
        latency_ms=10,
        tool_spec=None,
    )
    sink.record(
        tool_name="mcp.demo.tool",
        arguments={"x": 2},
        result={"status": "error", "error": "timeout"},
        success=False,
        latency_ms=30,
        tool_spec=None,
    )

    rec = fabric.store.get(rec_id)
    assert rec is not None
    stats = rec.metadata["stats"]
    assert stats["call_count"] == 2
    assert stats["success_count"] == 1
    assert stats["failure_count"] == 1
    assert float(stats["success_rate"]) == 0.5
    assert stats["last_success"] is False
    assert float(stats["avg_latency_ms"]) == 15.0
    assert rec.metadata["examples"][-1]["error"] == "timeout"
