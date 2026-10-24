from __future__ import annotations
from typing import Dict, Any
from quentin.tools.middleware.base import ToolMiddleware, BeforeOutcome, AfterOutcome, ToolCallContextLike
from quentin.tools.schemas import ToolCallResult

class ShellSafetyMiddleware(ToolMiddleware):
    id = "shell_safety"
    priority = 20

    def before(self, *, tool_name: str, params: Dict[str, Any], ctx: ToolCallContextLike) -> BeforeOutcome:
        return BeforeOutcome(params=params)

    def after(self, *, tool_name: str, params: Dict[str, Any], result: ToolCallResult, ctx: ToolCallContextLike) -> AfterOutcome:
        if tool_name.startswith("shell.") and result.success and isinstance(result.output, dict):
            output = result.output
            stdout = output.get("stdout") or output.get("result")
            new_output = None
            
            if isinstance(stdout, str) and len(stdout) > 10000:
                new_output = dict(output)
                truncated = self._truncate(stdout)
                if "stdout" in new_output: new_output["stdout"] = truncated
                if "result" in new_output: new_output["result"] = truncated
            
            stderr = output.get("stderr")
            if isinstance(stderr, str) and len(stderr) > 5000:
                if new_output is None: new_output = dict(output)
                new_output["stderr"] = self._truncate(stderr, limit=5000)
            
            if new_output is not None:
                new_result = ToolCallResult(
                    tool_name=result.tool_name,
                    success=result.success,
                    output=new_output,
                    error=result.error,
                    meta=result.meta
                )
                return AfterOutcome(result=new_result)
                
        return AfterOutcome(result=result)

    def _truncate(self, text: str, limit: int = 10000) -> str:
        h, t = text[: limit // 2], text[-(limit // 2):]
        msg = f"\n... [ShellSafety: Truncated {len(text)}] ...\n"
        return h + msg + t
