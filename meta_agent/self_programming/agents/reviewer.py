from __future__ import annotations
from typing import List
import os
import json

from meta_agent.self_programming.tools.local_llm import LocalLLMTool

from meta_agent.self_programming.schema import (
    ProgrammingTask,
    CodePatchSet,
    TestReport,
    ReviewDecision,
)


class ReviewerAgent:
    """
    代码审查员：
    v0 可以先用简单规则：
    - 测试没过：reject
    - 测试过：approve
    future 再接 LLM 做细致审查。
    """

    def __init__(self):
        self.use_llm = os.getenv("USE_LLM_REVIEWER", "false").lower() in {"1", "true", "yes"}
        self.llm = LocalLLMTool() if self.use_llm else None

    def review(
        self,
        task: ProgrammingTask,
        patch_set: CodePatchSet,
        test_report: TestReport,
    ) -> ReviewDecision:
        print(f"[ReviewerAgent] Received test_report.overall_status: {test_report.overall_status}")
        patch_count = len(patch_set.files)

        if self.use_llm and self.llm:
            try:
                prompt = self._build_prompt(task, patch_set, test_report)
                raw = self.llm._call_local_llm(prompt)
                data = json.loads(raw)
                return ReviewDecision(
                    task_id=task.task_id,
                    status=data.get("status", "reject"),
                    severity=data.get("severity", "medium"),
                    issues=data.get("issues", []),
                    summary=data.get("summary", ""),
                    follow_up_actions=data.get("follow_up_actions", []),
                )
            except Exception as e:
                print(f"[ReviewerAgent] LLM review failed, fallback to rule: {e}")

        if test_report.overall_status != "passed":
            return ReviewDecision(
                task_id=task.task_id,
                status="reject",
                severity="high",
                issues=[{"type": "test_failed", "description": "pytest failed"}],
                summary=f"Tests failed, patch rejected (patches={patch_count})",
                follow_up_actions=["fix failing tests or patch"],
            )

        return ReviewDecision(
            task_id=task.task_id,
            status="approve",
            severity="low",
            issues=[],
            summary=f"Tests passed, patch approved (rule-based v0, patches={patch_count})",
            follow_up_actions=[],
        )

    def _build_prompt(self, task: ProgrammingTask, patch_set: CodePatchSet, test_report: TestReport) -> str:
        patch_count = len(patch_set.files)
        patch_summary = patch_set.summary
        test_status = test_report.overall_status
        raw_tests = (test_report.raw_output or "")[:4000]
        return (
            "You are a code reviewer. Return JSON with keys: "
            "status ('approve'|'request_changes'|'reject'), severity ('low'|'medium'|'high'), "
            "issues (list of {type, location?, description, suggestion}), summary, follow_up_actions (list).\n"
            f"Task: {task.task_id}\nDescription: {task.description}\n"
            f"Patch count: {patch_count}\nPatch summary: {patch_summary}\n"
            f"Test overall_status: {test_status}\nRaw test output (truncated):\n{raw_tests}\n"
            "Be concise."
        )
