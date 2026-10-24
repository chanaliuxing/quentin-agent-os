from __future__ import annotations

import json
import logging
from typing import Any, Dict, Optional

from quentin.cognitive.self_awareness import SelfAwarenessEngine
from quentin.cognitive.attempt_response_parser import parse_model_response_text

logger = logging.getLogger(__name__)


async def run_executor(
    loop: Any,
    *,
    task: Any,
    goal: Any,
    plan_summary: str,
    progressive_pressure: bool = False,
    self_awareness: Optional[Any] = None,
) -> Dict[str, Any]:
    """Execute a planner payload through the standardized async executor."""
    try:
        try:
            plan_data = json.loads(plan_summary)
            if isinstance(plan_data, dict) and isinstance(plan_data.get("steps"), list):
                # PlannerResult.raw_output schema: {"steps":[{step_id,description,skill_id,notes,...}], ...}
                # Keep planner payload as-is; inferring tool args here is usually unsafe.
                plan_obj: Any = plan_data
            else:
                raise ValueError("plan_summary is not a valid plan payload")
        except Exception:
            # Fallback: treat the whole summary as a single step.
            plan_obj = {"steps": [{"step_id": "s1", "description": str(plan_summary or "").strip()}]}

        from quentin.runtime.system_events import system_events

        pending_events = system_events.consume_pending()

        exec_context = loop._build_executor_prompt_context(
            task=task,
            goal=goal,
            progressive_pressure=progressive_pressure,
        ) | {
            "task_id": task.task_id,
            "domain": task.domain,
            "trace_id": getattr(task, "task_id", None),
            "trace_recorder": getattr(loop, "trace_recorder", None),
            "cancel_token": task.metadata.get("cancel_token"),
            "progressive_pressure": progressive_pressure,
            "self_awareness": (self_awareness.to_dict() if self_awareness else {}),
            "self_awareness_note": (
                SelfAwarenessEngine.to_prompt_hint(self_awareness) if self_awareness else ""
            ),
        }
        if pending_events:
            exec_context.setdefault("recent_system_events", []).extend(pending_events)

        res = await loop.executor.execute_plan(goal=goal, plan=plan_obj, context=exec_context)

        from quentin.utils.json import make_jsonable

        final_output = ""
        if isinstance(res, dict):
            steps = res.get("steps", [])
            if steps and isinstance(steps[-1], dict):
                last_res = steps[-1].get("result") or steps[-1].get("output")
                if isinstance(last_res, dict):
                    final_output = (
                        last_res.get("result")
                        or last_res.get("summary")
                        or last_res.get("output")
                        or str(last_res)
                    )
                else:
                    final_output = str(last_res)
            if not final_output:
                final_output = res.get("final_output") or res.get("raw_output") or ""
        parsed_resp = parse_model_response_text(str(final_output or ""))
        final_output = str(parsed_resp.final or "").strip()
        if isinstance(res, dict):
            res.setdefault("model_response_parse", parsed_resp.to_dict())
            if parsed_resp.repetition_detected:
                res["error"] = "model_repetition_detected"
                res["repetition_detected"] = True

        actions_list = []
        for s in res.get("steps", []):
            if isinstance(s, dict) and s.get("summary"):
                actions_list.append(s["summary"])
            elif isinstance(s, dict) and s.get("description"):
                actions_list.append(s["description"])

        summary_text = (
            "\n".join(actions_list)
            if actions_list
            else json.dumps(make_jsonable(res.get("steps", [])), ensure_ascii=False)
        )
        if parsed_resp.repetition_detected:
            summary_text = (summary_text + "\n[guard] repetition_detected").strip()

        return {
            "final_output": final_output,
            "actions_summary": summary_text,
            "raw": res,
            "is_system_error": False,
            "direct_response_sent": bool(res.get("direct_response_sent", False)),
        }
    except Exception as e:
        logger.exception("CognitiveLoop: executor crashed")
        return {
            "final_output": "",
            "actions_summary": f"executor_crash: {e}",
            "raw": {"error": str(e)},
            "is_system_error": True,
        }
