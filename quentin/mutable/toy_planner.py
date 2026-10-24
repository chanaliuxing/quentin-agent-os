"""
A naive toy planner used to demonstrate self-programming.

AUTO_UPDATABLE: true

问题：
- plan 里总是返回一个只有 "noop" 的步骤，没什么用。
- 有时会无视 task goal。
自编程引擎的目标是让它：
- 至少把 goal 写入 description 里
- 支持简单的 "substeps" 拆解
"""

from typing import Dict, Any, List
import uuid


def toy_make_plan(goal: str, context: Dict[str, Any] | None = None) -> List[Dict[str, Any]]:
    """
    Very naive planner: always return one noop step.
    """
    return [
        {
            "step_id": f"toy_{uuid.uuid4().hex}",
            "description": f"do something about: {goal}",  # 体现 goal
            "tool": "noop",
            "params": {},
        }
    ]


async def plan_toy_task(task: Dict[str, Any]) -> Dict[str, Any]:
    """
    Simple async planner used by tests:
    - raises RuntimeError when goal contains 'CRASH'
    - otherwise returns at least 3 steps reflecting the goal
    """
    goal = (task or {}).get("goal", "")
    if "CRASH" in goal.upper():
        raise RuntimeError("CRASH goal triggered by design")

    steps: List[Dict[str, Any]] = []
    for idx in range(3):
        steps.append(
            {
                "step_id": f"toy_{idx+1}",
                "description": f"{goal} - step {idx+1}",
                "tool": "noop",
                "params": {},
            }
        )
    return {"steps": steps}
