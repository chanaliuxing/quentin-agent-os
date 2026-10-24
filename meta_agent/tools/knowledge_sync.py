# meta_agent/tools/knowledge_sync.py
from __future__ import annotations
from typing import Iterable, Optional, Dict, Any
import uuid

from meta_agent.memory.fabric import MemoryFabric
from meta_agent.memory.tool_knowledge import ToolKnowledge
from meta_agent.memory.types import MemoryTier
from meta_agent.tools.registry import ToolRegistry
from meta_agent.config.tool_settings import tool_settings


def _truncate(obj: Any, max_len: Optional[int] = None) -> Any:
    if max_len is None:
        max_len = tool_settings.usage_truncate_len
    try:
        s = str(obj)
    except Exception:
        return obj
    if len(s) <= max_len:
        return obj
    return s[: max_len - 3] + "..."


def _stable_id(tool_id: str) -> str:
    return f"tool_knowledge::{uuid.uuid5(uuid.NAMESPACE_URL, tool_id)}"


def sync_registry_to_memory(
    registry: ToolRegistry,
    memory_fabric: MemoryFabric,
    *,
    tier: MemoryTier = MemoryTier.LTS,
    use_stable_ids: bool = True,
) -> int:
    """
    Write tool metadata into Memory Fabric as TOOL_KNOWLEDGE records.
    Returns the number of records written.
    """
    written = 0
    for reg in registry.list():
        record_id = _stable_id(reg.tool_id) if use_stable_ids else None
        existing_examples = []
        if record_id:
            existing = memory_fabric.store.get(record_id)
            if existing and isinstance(existing.metadata, dict):
                existing_examples = existing.metadata.get("examples") or []
        tk = ToolKnowledge(
            tool_id=reg.tool_id,
            server=reg.server,
            transport=reg.transport,
            uri=reg.uri,
            signature=reg.signature,
            description=reg.description,
            examples=reg.examples or existing_examples,
            metrics={
                "call_count": reg.metrics.call_count,
                "success_rate": reg.metrics.success_rate,
                "avg_latency_ms": reg.metrics.avg_latency_ms,
                "last_used_at": reg.metrics.last_used_at,
            },
            governance={
                "state": reg.governance.lifecycle.value,
                "risk_level": reg.governance.risk_level.value,
                "domain_scope": list(reg.governance.domain_scope),
                "council_score": reg.governance.council_score,
            },
            notes=f"transport={reg.transport}; uri={reg.uri}" if reg.uri else f"transport={reg.transport}",
        )
        rec = tk.to_memory_record(tier=tier, record_id=record_id)
        memory_fabric.store.upsert(rec)
        written += 1
    return written


def record_tool_usage(
    registry: ToolRegistry,
    memory_fabric: MemoryFabric,
    tool_id: str,
    *,
    arguments: Dict[str, Any],
    output: Any,
    error: Optional[str],
    success: bool,
    summarize: bool = True,
    tier: MemoryTier = MemoryTier.LTS,
) -> None:
    """
    Persist a usage example into TOOL_KNOWLEDGE for the given tool_id.
    """
    reg = registry.get(tool_id)
    if not reg:
        return
    example = {
        "input": _truncate(arguments),
        "output": _truncate(output) if success else None,
        "error": _truncate(error) if error else None,
        "success": success,
    }
    summary_note = None
    if summarize:
        summary_note = f"success={success}; last_error={error}" if error else f"success={success}"

    tk = ToolKnowledge(
        tool_id=reg.tool_id,
        server=reg.server,
        transport=reg.transport,
        uri=reg.uri,
        signature=reg.signature,
        description=reg.description,
        examples=[example],
        metrics={
            "call_count": reg.metrics.call_count,
            "success_rate": reg.metrics.success_rate,
            "avg_latency_ms": reg.metrics.avg_latency_ms,
            "last_used_at": reg.metrics.last_used_at,
        },
        governance={
            "state": reg.governance.lifecycle.value,
            "risk_level": reg.governance.risk_level.value,
            "domain_scope": list(reg.governance.domain_scope),
            "council_score": reg.governance.council_score,
        },
        notes=summary_note or (f"transport={reg.transport}; uri={reg.uri}" if reg.uri else f"transport={reg.transport}"),
    )
    record_id = _stable_id(reg.tool_id)
    rec = tk.to_memory_record(tier=tier, record_id=record_id)
    memory_fabric.store.upsert(rec)
