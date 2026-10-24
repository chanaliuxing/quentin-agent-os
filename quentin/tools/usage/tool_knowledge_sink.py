from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional
import time

from quentin.memory.models import MemoryTier
from quentin.memory.tool_knowledge import ToolKnowledgeEntry, stable_tool_knowledge_id
from quentin.utils.time import now_utc_iso


def _safe_get(d: Any, key: str, default: Any = None) -> Any:
    try:
        if isinstance(d, dict):
            return d.get(key, default)
    except Exception:
        return default
    return default


@dataclass
class ToolKnowledgeUsageSink:
    """
    Best-effort writeback sink:
    - stores per-tool usage stats to MemoryFabric as kind=tool_knowledge
    - keeps a stable id so repeated calls update one record
    """

    memory_fabric: Any
    tier: MemoryTier = MemoryTier.LTS
    max_examples: int = 5

    def record(
        self,
        *,
        tool_name: str,
        arguments: Dict[str, Any],
        result: Any,
        success: bool,
        latency_ms: Optional[int],
        tool_spec: Optional[Any] = None,
    ) -> None:
        if not tool_name:
            return
        store = getattr(self.memory_fabric, "store", None)
        if store is None:
            return

        record_id = stable_tool_knowledge_id(tool_name)
        existing = None
        try:
            existing = store.get(record_id)
        except Exception:
            existing = None

        # Build / merge stats
        stats = {}
        examples = []
        signature = ""
        description = ""
        risk_level = "medium"
        governance_state = "experimental"
        tags = ["tool", "tool_knowledge"]

        if tool_spec is not None:
            try:
                description = str(getattr(tool_spec, "description", "") or "")
                risk_level = str(getattr(tool_spec, "risk_level", "") or risk_level)
                lifecycle = getattr(tool_spec, "lifecycle", None)
                if lifecycle:
                    tags.append(f"lifecycle:{lifecycle}")
                meta = getattr(tool_spec, "meta", None) or {}
                if isinstance(meta, dict):
                    signature = str(meta.get("signature") or meta.get("tool_signature") or signature)
                    governance_state = str(meta.get("governance_state") or governance_state)
            except Exception:
                pass

        if existing is not None:
            md = getattr(existing, "metadata", None) or {}
            stats = dict(_safe_get(md, "stats", {}) or {})
            examples = list(_safe_get(md, "examples", []) or [])
            signature = signature or str(_safe_get(md, "signature", "") or "")
            description = description or str(_safe_get(md, "description", "") or "")
            risk_level = risk_level or str(_safe_get(md, "risk_level", "medium") or "medium")
            governance_state = governance_state or str(_safe_get(md, "governance_state", "experimental") or "experimental")
        else:
            # Seed examples from tool metadata if present (e.g. schema-synthesized on registration).
            if tool_spec is not None:
                try:
                    md = getattr(tool_spec, "meta", None) or {}
                    if isinstance(md, dict) and isinstance(md.get("examples"), list) and md.get("examples"):
                        examples = list(md.get("examples") or [])
                except Exception:
                    pass

        call_count = int(stats.get("call_count") or 0) + 1
        success_count = int(stats.get("success_count") or 0) + (1 if success else 0)
        failure_count = int(stats.get("failure_count") or 0) + (0 if success else 1)
        total_latency_ms = int(stats.get("total_latency_ms") or 0) + (int(latency_ms or 0))
        avg_latency_ms = (total_latency_ms / call_count) if call_count > 0 else None

        stats.update(
            {
                "call_count": call_count,
                "success_count": success_count,
                "failure_count": failure_count,
                "success_rate": (success_count / call_count) if call_count > 0 else 0.0,
                "avg_latency_ms": avg_latency_ms,
                "last_used_at": now_utc_iso(),
                "last_success": bool(success),
            }
        )

        # Append a small example
        try:
            example = {
                "input": arguments,
                "success": bool(success),
                "latency_ms": int(latency_ms or 0),
            }
            if not success:
                # Keep only a small error summary
                err = None
                if hasattr(result, "error"):
                    err = getattr(result, "error", None)
                if isinstance(result, dict):
                    err = err or result.get("error")
                example["error"] = str(err or "error")
            examples.append(example)
            if len(examples) > int(self.max_examples):
                examples = examples[-int(self.max_examples) :]
        except Exception:
            pass

        entry = ToolKnowledgeEntry(
            tool_name=tool_name,
            signature=signature or tool_name,
            description=description or "",
            examples=examples,
            stats=stats,
            risk_level=risk_level or "medium",
            tags=tags,
            governance_state=governance_state or "experimental",
            notes=None,
        )
        rec = entry.to_memory_record(tier=self.tier)
        try:
            if existing is None:
                store.add(rec)
            else:
                # Preserve created_at; update mutable fields.
                rec.created_at = getattr(existing, "created_at", rec.created_at)
                store.update(rec)
        except Exception:
            return
