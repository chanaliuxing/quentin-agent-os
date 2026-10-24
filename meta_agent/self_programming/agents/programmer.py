from __future__ import annotations

from pathlib import Path
from typing import Optional

from meta_agent.self_programming.schema import ProgrammingTask, DevPlan, CodePatchSet
from meta_agent.self_programming.tools.base import CodeToolRegistry


class ProgrammerAgent:
    """
    Minimal `ProgrammerAgent` implementation.

    This module is required by `meta_agent.self_programming.engine` but was missing in the repo.
    For now it acts as a placeholder so imports and basic wiring work; the V2 engine is the
    preferred path for real self-programming flows.
    """

    def __init__(self, *, repo_root: str = ".", tools: Optional[CodeToolRegistry] = None) -> None:
        self.repo_root = repo_root
        self.tools = tools or CodeToolRegistry()
        self.tool_priority = (
            "gemini_cli",
            "codex_cli",
            "claude_code_cli",
            "external_cli",
            "local_llm",
        )

    def implement(self, task: ProgrammingTask, dev_plan: DevPlan) -> CodePatchSet:
        names = self.tools.list_tools()
        tool_name = next((name for name in self.tool_priority if name in names), None)
        if not tool_name:
            tool_name = names[0] if names else None

        if not tool_name:
            return CodePatchSet(task_id=task.task_id, files=[], summary="no tools registered")

        tool = self.tools.get(tool_name)
        modifications = []

        for item in dev_plan.work_items or []:
            file_path = str(item.get("file_path") or "").strip()
            if not file_path:
                continue
            goal = str(item.get("goal") or "").strip()
            notes = str(item.get("notes") or "").strip()

            abs_path = Path(self.repo_root) / file_path
            if abs_path.exists():
                try:
                    content = abs_path.read_text(encoding="utf-8", errors="ignore")
                except Exception:
                    content = ""
            else:
                content = ""

            instructions = "\n".join(
                [
                    task.description,
                    f"Work item goal: {goal}" if goal else "",
                    f"Notes: {notes}" if notes else "",
                    "Acceptance criteria:",
                    *[f"- {c}" for c in (task.acceptance_criteria or [])],
                ]
            ).strip()

            try:
                mods = tool.generate_code_changes(
                    task=task,
                    file_path=file_path,
                    file_content=content,
                    instructions=instructions,
                )
                modifications.extend(mods)
            except Exception:
                continue

        summary = f"generated {len(modifications)} modifications via {tool_name}"
        return CodePatchSet(task_id=task.task_id, files=modifications, summary=summary)
