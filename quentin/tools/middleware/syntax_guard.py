from __future__ import annotations
import ast
from typing import Dict, Any
from quentin.tools.middleware.base import ToolMiddleware, BeforeOutcome, AfterOutcome, ToolCallContextLike
from quentin.tools.schemas import ToolCallResult

class SyntaxGuardMiddleware(ToolMiddleware):
    id = "syntax_guard"
    priority = 40

    def before(self, *, tool_name: str, params: Dict[str, Any], ctx: ToolCallContextLike) -> BeforeOutcome:
        if tool_name in ("fs.write_file", "fs_write_file"):
            p_str = params.get("path", "")
            c = params.get("content", "")
            if p_str.endswith(".py") and c:
                try:
                    ast.parse(c)
                except SyntaxError as e:
                    msg = f"Syntax Error on line {e.lineno}: {e.msg}"
                    return BeforeOutcome(params=params, blocked=True, reason=msg)
        return BeforeOutcome(params=params)

    def after(self, *, tool_name: str, params: Dict[str, Any], result: ToolCallResult, ctx: ToolCallContextLike) -> AfterOutcome:
        return AfterOutcome(result=result)
