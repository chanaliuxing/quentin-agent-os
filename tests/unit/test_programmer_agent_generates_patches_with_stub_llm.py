import os

from meta_agent.self_programming.agents.programmer import ProgrammerAgent
from meta_agent.self_programming.schema import DevPlan, FileModification, ProgrammingTask
from meta_agent.self_programming.tools.base import CodeToolBase, CodeToolRegistry
from meta_agent.self_programming.tools.local_llm import LocalLLMTool


def test_programmer_agent_generates_patches_with_stub_llm(monkeypatch) -> None:
    monkeypatch.setenv("LOCAL_LLM_STUB", "1")

    tools = CodeToolRegistry()
    tools.register(LocalLLMTool())

    agent = ProgrammerAgent(repo_root=".", tools=tools)
    task = ProgrammingTask(
        task_id="t1",
        origin="refactor",
        description="Rename foo to foo_v2",
        repo_root=".",
        related_files=["demo.py"],
        context_summary="",
        constraints={},
        acceptance_criteria=["code compiles"],
        environment="sandbox",
    )
    dev_plan = DevPlan(
        task_id="t1",
        task_summary="",
        impact_analysis={},
        work_items=[{"file_path": "demo.py", "goal": "rename foo to foo_v2", "notes": ""}],
        test_plan={"framework": "pytest", "targets": []},
        notes="",
    )

    patch_set = agent.implement(task, dev_plan)
    assert patch_set.files, patch_set.summary


class _StubTool(CodeToolBase):
    def __init__(self, name: str, marker: str):
        self.name = name
        self.marker = marker
        self.calls = 0

    def generate_code_changes(self, task, file_path, file_content, instructions):
        self.calls += 1
        return [
            FileModification(
                file_path=file_path,
                action="modify",
                original_snippet="",
                new_content=self.marker,
            )
        ]

    def generate_tests(self, task, context):
        return []


def test_programmer_agent_prefers_gemini_cli_over_local_llm() -> None:
    tools = CodeToolRegistry()
    local = _StubTool("local_llm", "local")
    gemini = _StubTool("gemini_cli", "gemini")
    tools.register(local)
    tools.register(gemini)

    agent = ProgrammerAgent(repo_root=".", tools=tools)
    task = ProgrammingTask(
        task_id="t2",
        origin="refactor",
        description="Test priority",
        repo_root=".",
        related_files=["demo.py"],
        context_summary="",
        constraints={},
        acceptance_criteria=[],
        environment="sandbox",
    )
    dev_plan = DevPlan(
        task_id="t2",
        task_summary="",
        impact_analysis={},
        work_items=[{"file_path": "demo.py", "goal": "change", "notes": ""}],
        test_plan={"framework": "pytest", "targets": []},
        notes="",
    )

    patch_set = agent.implement(task, dev_plan)
    assert patch_set.files
    assert patch_set.files[0].new_content == "gemini"
    assert gemini.calls == 1
    assert local.calls == 0
