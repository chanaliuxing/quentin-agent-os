from __future__ import annotations
from typing import List
import subprocess
import textwrap
import re
import os
import json

from meta_agent.self_programming.schema import FileModification, ProgrammingTask
from meta_agent.self_programming.tools.base import CodeToolBase


class ExternalCLITool(CodeToolBase):
    """
    把 gemini-cli / codex-cli 之类的工具包装成 CodeTool。
    假设 CLI 支持通过 stdin 传 prompt，stdout 返回代码块。
    """

    def __init__(self, name: str, cli_cmd: str, enabled: bool | None = None):
        self.name = name
        self.cli_cmd = cli_cmd
        # Enable only if explicitly requested via flag/env to avoid surprises.
        env_flag = os.getenv("ENABLE_EXTERNAL_CLI_TOOL", "false").lower() in {"1", "true", "yes"}
        self._enabled = enabled if enabled is not None else env_flag

    def _run_cli(self, prompt: str) -> str:
        try:
            proc = subprocess.run(
                [self.cli_cmd],
                input=prompt,
                text=True,
                capture_output=True,
                check=True,
            )
            return proc.stdout
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"CLI tool {self.cli_cmd} failed: {e.stderr}") from e

    @staticmethod
    def _parse_patch_blocks(raw: str, file_path: str) -> List[FileModification]:
        mods: List[FileModification] = []
        pattern = re.compile(r"<<<< SEARCH\n(.*?)\n====\n(.*?)\n>>>>", re.DOTALL)
        for match in pattern.finditer(raw.strip()):
            orig = match.group(1).strip()
            repl = match.group(2).strip()
            mods.append(
                FileModification(
                    file_path=file_path,
                    action="modify",
                    original_snippet=orig,
                    new_content=repl,
                )
            )
        return mods

    def generate_code_changes(
        self,
        task: ProgrammingTask,
        file_path: str,
        file_content: str,
        instructions: str,
    ) -> List[FileModification]:
        if not self._enabled:
            raise RuntimeError("ExternalCLITool disabled. Set ENABLE_EXTERNAL_CLI_TOOL=true to enable.")
        prompt = textwrap.dedent(f"""
        TASK: {task.description}
        FILE: {file_path}

        CURRENT CONTENT:
        ```python
        {file_content}
        ```

        INSTRUCTION:
        {instructions}

        Please output patch in the format:

        <<<< SEARCH
        ...
        ====
        ...
        >>>>
        """)
        raw = self._run_cli(prompt)
        mods = self._parse_patch_blocks(raw, file_path)
        if not mods:
            raise RuntimeError("External CLITool returned no parsable patches.")
        return mods

    def generate_tests(
        self,
        task: ProgrammingTask,
        context: str,
    ) -> List[FileModification]:
        """
        Generate a minimal, deterministic smoke-test module for the task.

        The goal is to leave a runnable placeholder that captures the task context without
        depending on an external CLI or LLM. If external test generation is needed, it
        should be implemented behind a separate feature flag.
        """
        safe_task_id = re.sub(r"[^0-9A-Za-z_]+", "_", task.task_id).strip("_") or "task"
        file_path = f"tests/generated/test_{safe_task_id}.py"

        context_preview = "\n".join((context or task.context_summary or "").splitlines()[:20])
        desc_literal = json.dumps(task.description)
        context_literal = json.dumps(context_preview)

        test_body = textwrap.dedent(
            f"""\
            \"\"\"Auto-generated smoke tests for task {task.task_id}.
            Replace the skipped test with real assertions once the change is stable.
            \"\"\"

            import pytest


            @pytest.mark.skip(reason="auto-generated placeholder; replace with real assertions")
            def test_smoke_generated() -> None:
                assert {desc_literal}
                assert {context_literal} is not None
            """
        )

        return [
            FileModification(
                file_path=file_path,
                action="create",
                original_snippet=None,
                new_content=test_body,
            )
        ]
