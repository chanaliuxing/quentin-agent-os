# meta_agent/tools/coder/base.py
from __future__ import annotations
from dataclasses import dataclass
from typing import List, Optional
from abc import ABC, abstractmethod


@dataclass
class CodeGenerationRequest:
    goal: str                        # 想干嘛
    context_files: List[str]         # 相关文件路径
    instructions: str                # 对 coder 的详细 prompt
    preferred_language: str = "python"
    request_tests: bool = False      # Add a flag to request tests


@dataclass
class CodeGenerationResult:
    success: bool
    code: str
    reasoning: Optional[str] = None
    raw_output: Optional[str] = None
    test_code: Optional[str] = None  # Add a field for generated test code



class CoderBackend(ABC):
    name: str = "base"

    @abstractmethod
    def generate(self, req: CodeGenerationRequest) -> CodeGenerationResult:
        raise RuntimeError("CoderBackend is abstract; use a concrete backend (e.g. codex_cli).")
