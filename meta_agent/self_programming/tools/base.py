from __future__ import annotations
from abc import ABC, abstractmethod
from typing import List

from meta_agent.self_programming.schema import FileModification, ProgrammingTask


class CodeToolBase(ABC):
    name: str

    @abstractmethod
    def generate_code_changes(
        self,
        task: ProgrammingTask,
        file_path: str,
        file_content: str,
        instructions: str,
    ) -> List[FileModification]:
        """
        根据任务 + 当前文件内容 + 指令，生成针对这个文件的修改。
        """
        ...

    @abstractmethod
    def generate_tests(
        self,
        task: ProgrammingTask,
        context: str,
    ) -> List[FileModification]:
        """
        生成/修改测试文件。
        """
        ...


class CodeToolRegistry:
    """
    简单的工具注册表，SelfProgrammingEngine / Agents 从这里拿工具。
    DEPRECATED: V1 registry is kept for backward compatibility; prefer coder_router and CodeGenerationRequest in engine_v2.
    """

    def __init__(self):
        import warnings
        warnings.warn(
            "CodeToolRegistry (V1) is deprecated; use coder_router with CodeGenerationRequest/Result (engine_v2).",
            DeprecationWarning,
            stacklevel=2,
        )
        self._tools: dict[str, CodeToolBase] = {}

    def register(self, tool: CodeToolBase):
        self._tools[tool.name] = tool

    def get(self, name: str) -> CodeToolBase:
        return self._tools[name]

    def list_tools(self):
        return list(self._tools.keys())
