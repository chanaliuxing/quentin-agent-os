# meta_agent/immune/planner.py
from __future__ import annotations
from typing import List, Dict, Any
import json

from meta_agent.immune.models import (
    ImmuneCase,
    ImmuneAction,
    ImmuneActionKind,
)
from meta_agent.runtime.council import council
from meta_agent.llm.ollama_client import ChatMessage
from meta_agent.tracing import JsonlTraceRecorder

trace_recorder = JsonlTraceRecorder(repo_root=".")

def _heuristic_plan(cases: List[ImmuneCase]) -> List[ImmuneAction]:
    actions: List[ImmuneAction] = []

    for c in cases:
        # ERROR_SPIKE：先暂停自动自改 + 请求人工介入
        if c.kind.name == "ERROR_SPIKE":
            actions.append(
                ImmuneAction(
                    kind=ImmuneActionKind.PAUSE_AUTOPATCH,
                    case_id=c.id,
                    target_type="system",
                    target_id=None,
                    reason="Overall error spike; pause autopatch for safety.",
                )
            )
            actions.append(
                ImmuneAction(
                    kind=ImmuneActionKind.REQUEST_HUMAN_REVIEW,
                    case_id=c.id,
                    target_type="system",
                    target_id=None,
                    reason="Overall error spike; require human review of recent patches/skills.",
                )
            )

        # DOMAIN_REGRESSION：降低此 domain 相关任务的节奏（先抽象成 REDUCE_TASK_BUDGET）
        elif c.kind.name == "DOMAIN_REGRESSION":
            domain = c.details.get("domain", "unknown")
            actions.append(
                ImmuneAction(
                    kind=ImmuneActionKind.REDUCE_TASK_BUDGET,
                    case_id=c.id,
                    target_type="task",
                    target_id=f"{domain}::*",
                    params={"reduce_factor": 0.5},
                    reason=f"Domain regression for {domain}; reduce orchestrator budget.",
                )
            )
            actions.append(
                ImmuneAction(
                    kind=ImmuneActionKind.REQUEST_HUMAN_REVIEW,
                    case_id=c.id,
                    target_type="domain",
                    target_id=domain,
                    reason=f"Domain {domain} has high fail rate; ask human to inspect skills/patches.",
                )
            )

        # PATCH_FAILURE_STORM：暂停 autopatch + 标记近期 patch 需要人工审查
        elif c.kind.name == "PATCH_FAILURE_STORM":
            actions.append(
                ImmuneAction(
                    kind=ImmuneActionKind.PAUSE_AUTOPATCH,
                    case_id=c.id,
                    target_type="system",
                    reason="Patch failure storm; pause autopatch.",
                )
            )
            actions.append(
                ImmuneAction(
                    kind=ImmuneActionKind.REQUEST_HUMAN_REVIEW,
                    case_id=c.id,
                    target_type="system",
                    reason="Many patches failing evaluation; human should check self-programming logic.",
                )
            )

        # EXPERIMENT_INSTABILITY：同样偏向请求人工复核
        elif c.kind.name == "EXPERIMENT_INSTABILITY":
            actions.append(
                ImmuneAction(
                    kind=ImmuneActionKind.REQUEST_HUMAN_REVIEW,
                    case_id=c.id,
                    target_type="system",
                    reason="Experiments unstable; no patches passed, ask human to tune configs.",
                )
            )

        else:
            # 默认给个 no_op，留给 council 决定要不要做点事
            actions.append(
                ImmuneAction(
                    kind=ImmuneActionKind.NO_OP,
                    case_id=c.id,
                    target_type="system",
                    reason=f"No heuristic action for case kind={c.kind.value}",
                )
            )

    return actions

def _refine_actions_via_council(
    cases: List[ImmuneCase],
    draft_actions: List[ImmuneAction],
) -> List[ImmuneAction]:
    """
    用多模型 council 来整体看一眼这些 case + draft_actions，
    看是否要调整 / 增减动作。
    """
    payload = {
        "cases": [c.__dict__ for c in cases],
        "draft_actions": [a.__dict__ for a in draft_actions],
    }

    system_prompt = """You are the immune system controller of a self-improving AI agent.

You receive:
- A list of diagnosed 'immune cases' (anomalies, regressions, spikes).
- A set of heuristic draft actions (pause autopatch, reduce task budgets, request review, etc.).

Your job:
- Review the draft actions globally.
- Remove clearly redundant or useless actions.
- Add missing actions if necessary (but keep it conservative).
- Make sure actions are safe and not overreacting.

You MUST respond with JSON ONLY:
{
  "actions": [
    {
      "kind": "NO_OP | DISABLE_SKILL | DOWNGRADE_SKILL | BLACKLIST_PATCH | PAUSE_AUTOPATCH | REDUCE_TASK_BUDGET | PAUSE_TASK | REQUEST_HUMAN_REVIEW",
      "case_id": "string",
      "target_type": "skill | patch | task | system | domain",
      "target_id": "string or null",
      "params": {...},
      "reason": "string"
    }
  ]
}
No extra keys, no commentary outside JSON.
"""

    user_content = json.dumps(payload, ensure_ascii=False, indent=2)

    raw = council.client.chat(
        model=council.config.planner_model,
        messages=[
            ChatMessage(role="system", content=system_prompt),
            ChatMessage(role="user", content=user_content),
        ],
        temperature=council.config.temperature_planner,
    )

    try:
        data = council.client.extract_json(raw)
    except Exception:
        # 如果解析失败，就用原始 draft_actions
        trace_recorder.log_event(
            event_type="immune_planner_council_parse_error",
            payload={"raw": raw},
        )
        return draft_actions

    refined: List[ImmuneAction] = []
    for a in data.get("actions", []):
        try:
            refined.append(
                ImmuneAction(
                    kind=ImmuneActionKind(a.get("kind", "NO_OP")),
                    case_id=a.get("case_id", ""),
                    target_type=a.get("target_type", "system"),
                    target_id=a.get("target_id"),
                    params=a.get("params") or {},
                    reason=a.get("reason", ""),
                )
            )
        except Exception:
            continue

    if not refined:
        return draft_actions

    return refined

def plan_immune_actions(cases: List[ImmuneCase]) -> List[ImmuneAction]:
    if not cases:
        return []

    draft = _heuristic_plan(cases)
    trace_recorder.log_event(
        event_type="immune_plan_draft",
        payload={
            "num_cases": len(cases),
            "num_actions": len(draft),
        },
    )

    refined = _refine_actions_via_council(cases, draft)
    trace_recorder.log_event(
        event_type="immune_plan_refined",
        payload={
            "num_cases": len(cases),
            "num_actions_refined": len(refined),
        },
    )
    return refined
