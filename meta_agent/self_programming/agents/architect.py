from __future__ import annotations
from typing import List
import os
import json

from meta_agent.self_programming.tools.local_llm import LocalLLMTool

from meta_agent.self_programming.schema import ProgrammingTask, DevPlan


class ArchitectAgent:
    """
    负责：从 BlueprintGap / 失败 trace 里，拉出一个具体的 DevPlan。
    """

    def __init__(self):
        self.use_llm = os.getenv("USE_LLM_ARCHITECT", "true").lower() in {"1", "true", "yes"}
        self.llm = LocalLLMTool() if self.use_llm else None

    def analyze(self, task: ProgrammingTask) -> DevPlan:
        """
        v0 版可以先用非常简单的规则：
        - 把 related_files 直接塞进 work_items
        - 输出一个 minimal 的 test_plan
        后面再逐步引入 LLM。
        """
        if self.use_llm and self.llm:
            try:
                prompt = self._build_prompt(task)
                raw = self.llm._call_local_llm(prompt)  # reuse local LLM client
                data = json.loads(raw)
                work_items = data.get("work_items", []) or []
                test_plan = data.get("test_plan", {"framework": "pytest", "targets": []})
                return DevPlan(
                    task_id=task.task_id,
                    task_summary=data.get("task_summary", task.description),
                    impact_analysis=data.get("impact_analysis", {}),
                    work_items=work_items,
                    test_plan=test_plan,
                    notes=data.get("notes", task.context_summary),
                )
            except Exception as e:
                print(f"[ArchitectAgent] LLM plan failed, fallback to stub: {e}")

        # fallback stub
        work_items: List[dict] = []
        for path in task.related_files:
            work_items.append(
                {
                    "file_path": path,
                    "goal": "improve according to task description",
                    "notes": "",
                }
            )

        test_plan = {
            "framework": "pytest",
            "targets": [],  # 后续可以让 LLM 决定应该测试哪些模块
        }

        return DevPlan(
            task_id=task.task_id,
            task_summary=task.description,
            impact_analysis={},
            work_items=work_items,
            test_plan=test_plan,
            notes=task.context_summary,
        )

    def _build_prompt(self, task: ProgrammingTask) -> str:
        related = "\n".join(task.related_files) if task.related_files else "<none>"
        constraints = json.dumps(task.constraints or {}, ensure_ascii=False, indent=2)
        acceptance = "\n".join(task.acceptance_criteria or [])
        return (
            "You are a senior software architect. Produce a JSON plan with keys: "
            "task_summary (string), impact_analysis (object), work_items (list of {file_path, goal, notes}), "
            "test_plan (object with framework, targets), notes (string).\n"
            f"Task id: {task.task_id}\n"
            f"Description: {task.description}\n"
            f"Related files: {related}\n"
            f"Context summary: {task.context_summary}\n"
            f"Constraints: {constraints}\n"
            f"Acceptance criteria:\n{acceptance}\n"
            "Respond ONLY with JSON."
        )
