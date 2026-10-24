from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict, Optional, Protocol, Tuple

from quentin.cognitive.perception.schemas import AttentionPack, SituationAssessment


class AttentionFilter(Protocol):
    def build_attention(self, *, ctx: Dict[str, Any], situation: SituationAssessment) -> AttentionPack: ...


def _json_len(obj: Any) -> int:
    try:
        return len(json.dumps(obj, ensure_ascii=False, default=str))
    except Exception:
        try:
            return len(str(obj))
        except Exception:
            return 0


def _truncate_str(val: Any, limit: int) -> str:
    s = str(val or "")
    if limit <= 0:
        return ""
    if len(s) <= limit:
        return s
    return s[: max(0, limit - 3)] + "..."


@dataclass
class HeuristicAttentionFilter:
    """
    v0 attention gating: keep a small, planner-useful subset and cap large blobs.
    """

    target_ratio: float = 0.15
    max_value_chars: int = 4000
    keep_keys: Tuple[str, ...] = (
        "historical_attempts",
        "candidate_files",
        "forbidden_actions",
        "previous_plan_steps",
        "procedural_memories",
        "gist_memories",
        "system_event_prompt",
        "self_awareness",
        "self_awareness_note",
        "strict_reasons",
        "domain",
        "environment",
    )

    def build_attention(self, *, ctx: Dict[str, Any], situation: SituationAssessment) -> AttentionPack:
        original_len = max(1, _json_len(ctx))
        selected: Dict[str, Any] = {}

        # Always include situation assessment (small and high-signal for planner)
        selected["situation"] = situation.to_dict()

        for k in self.keep_keys:
            if k not in ctx:
                continue
            v = ctx.get(k)
            if isinstance(v, str):
                selected[k] = _truncate_str(v, self.max_value_chars)
            else:
                # Cap by stringification length if huge
                if _json_len(v) > self.max_value_chars:
                    selected[k] = _truncate_str(v, self.max_value_chars)
                else:
                    selected[k] = v

        # Optional: keep a tiny env snapshot hint but never feed full tree by default.
        if "current_environment_tree" in ctx:
            selected["current_environment_tree_preview"] = _truncate_str(ctx.get("current_environment_tree"), 2000)

        selected_len = _json_len(selected)
        reduction_ratio = max(0.0, min(1.0, 1.0 - (selected_len / float(original_len))))
        debug_refs = {
            "original_ctx_bytes": int(original_len),
            "selected_ctx_bytes": int(selected_len),
            "target_ratio": float(self.target_ratio),
        }
        return AttentionPack(selected_context=selected, reduction_ratio=reduction_ratio, debug_refs=debug_refs)

