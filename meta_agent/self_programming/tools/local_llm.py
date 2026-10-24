from __future__ import annotations
from typing import List
import json
import textwrap
import httpx
import re
import os
from dotenv import load_dotenv

from meta_agent.self_programming.schema import FileModification, ProgrammingTask
from meta_agent.self_programming.tools.base import CodeToolBase

load_dotenv()


def _parse_llm_patch_output(raw_output: str, file_path: str) -> List[FileModification]:
    """
    Parses the LLM output in the format:
    <<<< SEARCH
    ...
    ====
    ...
    >>>>
    """
    mods = []
    # Be more robust to extra text or whitespace from the LLM
    clean_output = raw_output.strip()
    
    # Try to extract only the last patch block if there's extra text
    search_block_match = re.search(r"(<<<< SEARCH(.|\n)*>>>>)", clean_output, re.DOTALL)
    if search_block_match:
        clean_output = search_block_match.group(1)

    search_block_match = re.search(r"(<<<< SEARCH(.|\n)*>>>>)", clean_output, re.DOTALL)
    if search_block_match:
        clean_output = search_block_match.group(1)
    print(f"[{__name__}] Cleaned LLM output:\n---\n{clean_output}\n---")

    # Regex to find all SEARCH/====/REPLACE blocks
    pattern = re.compile(r"<<<< SEARCH\n(.*?)\n====\n(.*?)\n>>>>", re.DOTALL)
    matches = pattern.finditer(clean_output)

    for match in matches:
        original_snippet = match.group(1).strip()
        new_content = match.group(2).strip()
        mods.append(FileModification(
            file_path=file_path,
            action="modify",
            original_snippet=original_snippet,
            new_content=new_content,
        ))

    print(f"[{__name__}] Found {len(mods)} modifications in LLM output.")
    return mods


class LocalLLMTool(CodeToolBase):
    """
    使用本地 qwen/deepseek 模型的 CodeTool。
    这里留出一个 call_local_llm(prompt: str) 的占位，你可以接 Ollama / vllm / 自己的 HTTP 服务。
    """

    def __init__(self, model_name: str = os.getenv("LLM_MODEL"), api_url: str = os.getenv("LLM_BASE_URL", "http://localhost:11434/api/generate")):
        if not model_name:
            # Try once more from environ directly to be sure
            model_name = os.environ.get("LLM_MODEL")
        if not model_name:
            raise ValueError("Environment variable LLM_MODEL is not set.")
        self.name = "local_llm"
        self.model_name = model_name
        self.api_url = api_url
        self.use_stub = os.getenv("LOCAL_LLM_STUB", "false").lower() in {"1", "true", "yes"}

    def _call_local_llm(self, prompt: str) -> str:
        """
        Connects to a local Ollama-compatible API or returns a stubbed response when enabled.
        """
        if self.use_stub:
            return self._stub_response(prompt)

        try:
            with httpx.Client(timeout=300.0) as client:  # Increased timeout to 300 seconds
                payload = {
                    "model": self.model_name,
                    "prompt": prompt,
                    "stream": False,
                }
                response = client.post(
                    self.api_url,
                    json=payload,
                )
                # Debug prints as suggested
                print(f"Debug (LocalLLMTool): Request Method: {response.request.method}")
                # print(f"Debug (LocalLLMTool): Request Body: {response.request.body}")  # Skip body debug
                print(f"Debug (LocalLLMTool): Request Headers: {response.request.headers}")

                response.raise_for_status()
                # Assuming the API returns a JSON with a "response" field
                return response.json().get("response", "")
        except httpx.RequestError as e:
            raise RuntimeError(f"Failed to connect to local LLM at {self.api_url}: {e}")
        except Exception as e:
            raise RuntimeError(f"An error occurred while calling local LLM: {e}")

    def _stub_response(self, prompt: str) -> str:
        """
        Provide deterministic patches for demo scenarios when LOCAL_LLM_STUB is enabled.
        """
        file_paths = re.findall(r"^\s*FILE\s+PATH:\s*\n\s*(\S+)", prompt, re.MULTILINE)
        if not file_paths:
            return ""
        # The prompt contains an EXAMPLE with its own FILE PATH. Use the last one.
        file_path = str(file_paths[-1]).strip()

        if "demo.py" in file_path:
            return """
<<<< SEARCH
def foo(x: int) -> int:
    return x + 1
====
def foo_v2(x: int) -> int:
    return x + 1
>>>>
"""
        if "tests/test_demo.py" in file_path:
            return """
<<<< SEARCH
from demo import foo
====
from demo import foo_v2
>>>>
<<<< SEARCH
    assert foo(1) == 2
====
    assert foo_v2(1) == 2
>>>>
"""
        return ""

    def generate_code_changes(
        self,
        task: ProgrammingTask,
        file_path: str,
        file_content: str,
        instructions: str,
    ) -> List[FileModification]:
        system_prompt = textwrap.dedent('''
        You are an expert Python code refactoring assistant.
        Your goal is to perform code modifications precisely.
        You must output ONLY a patch in the specified format.
        Do not add any explanations or comments outside the patch blocks.

        --- EXAMPLE ---
        TASK:
        Perform the following refactoring steps:
        1. Rename the function 'calculate_sum' to 'add_numbers'.
        2. Add a docstring to the 'add_numbers' function.
        3. Update the call to the function in `main()`.
        Ensure the functionality remains exactly the same.

        FILE PATH:
        math_utils.py

        CURRENT FILE CONTENT:
        ```python
        def calculate_sum(a, b):
            # This function adds two numbers
            return a + b

        def main():
            print(calculate_sum(1, 2))

        if __name__ == "__main__":
            main()
        ```

        INSTRUCTION:
        In the file `math_utils.py`, perform the following steps for refactoring:
        1. Rename the function 'calculate_sum' to 'add_numbers'.
        2. Add a docstring to the new 'add_numbers' function.
        3. Update the call to 'calculate_sum' to 'add_numbers' in the `main()` function.
        Ensure that the code's functionality and all other aspects remain unchanged.

        Correct Output:
        <<<< SEARCH
        def calculate_sum(a, b):
            # This function adds two numbers
            return a + b
        ====
        def add_numbers(a, b):
            """
            This function adds two numbers and returns their sum.
            """
            return a + b
        >>>>
        <<<< SEARCH
            print(calculate_sum(1, 2))
        ====
            print(add_numbers(1, 2))
        >>>>
        --- END OF EXAMPLE ---

        IMPORTANT RULES:
        1.  **PRESERVE ORIGINAL FUNCTIONALITY:** The modified code must behave exactly like the original code, unless explicitly instructed otherwise.
        2.  **EXACT MATCH FOR SEARCH:** The SEARCH block must be an *exact, character-for-character* match of the code found in the `CURRENT FILE CONTENT`. This includes all comments, whitespace, and line breaks from the original code. No deviations are allowed.
        3.  **CORRECT INDENTATION FOR REPLACE:** Ensure that all code in the REPLACE block has correct and complete Python indentation.
        4.  **COMPLETE CODE BLOCKS:** Both SEARCH and REPLACE blocks must contain complete, valid Python code blocks (e.g., entire functions, classes, or logical statements). Do not provide partial lines.
        5.  **MULTIPLE PATCHES:** If multiple independent sections need changes, output multiple `<<<< SEARCH...>>>>` blocks one after another.
        6.  Do not output any text outside the `<<<< SEARCH...====...>>>>` blocks.
        ''').strip()

        prompt = textwrap.dedent(f"""
        {system_prompt}

        TASK:
        {task.description}

        FILE PATH:
        {file_path}

        CURRENT FILE CONTENT:
        ```
        {file_content}
        ```

        INSTRUCTION:
        {instructions}
        """)

        print("--- PROMPT ---")
        print(prompt)
        print("----------------")
        raw = self._call_local_llm(prompt)
        print("--- RAW LLM OUTPUT ---")
        print(raw)
        print("----------------------")
        return _parse_llm_patch_output(raw, file_path)

    def generate_tests(
        self,
        task: ProgrammingTask,
        context: str,
    ) -> List[FileModification]:
        """
        Generate a minimal, deterministic smoke-test module for the task.

        The goal is to leave a runnable placeholder that captures the task
        context without depending on an LLM.
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


            def test_task_metadata_present() -> None:
                assert {desc_literal}
                assert {context_literal} is not None


            @pytest.mark.skip(reason="Replace with real checks for {task.task_id}")
            def test_placeholder_for_real_logic() -> None:
                assert True
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
