from __future__ import annotations
import os
from pathlib import Path
from typing import Dict, Any
from quentin.tools.middleware.base import ToolMiddleware, BeforeOutcome, AfterOutcome, ToolCallContextLike
from quentin.tools.schemas import ToolCallResult

class SmartFilesystemMiddleware(ToolMiddleware):
    id = "smart_fs"
    priority = 10

    def __init__(self, repo_root: str):
        self.repo_root = Path(repo_root).resolve()

    def before(self, *, tool_name: str, params: Dict[str, Any], ctx: ToolCallContextLike) -> BeforeOutcome:
        if tool_name in ("fs.write_file", "fs_write_file"):
            p_str = params.get("path")
            if p_str:
                try:
                    target = (self.repo_root / p_str).resolve()
                    if target.exists() and target.is_dir():
                        return BeforeOutcome(
                            params=params,
                            blocked=True,
                            reason=f"Path '{p_str}' is already a directory. Cannot write file here.",
                        )
                    if not target.parent.exists():
                        target.parent.mkdir(parents=True, exist_ok=True)
                except Exception:
                    pass
        
        if tool_name in ("mkdir", "fs_mkdir", "fs.mkdir"):
            p_str = params.get("path")
            if p_str:
                # Surgery: Prevent mkdir on file paths (common halluncination)
                if p_str.endswith(".py") or p_str.endswith(".yaml") or p_str.endswith(".yml") or p_str.endswith(".md"):
                    return BeforeOutcome(
                        params=params,
                        blocked=True,
                        reason=f"Path '{p_str}' appears to be a file (ends in '.py'/'.yaml'/'.md'). 'mkdir' is ONLY for creating directories. Use 'fs.write_file' to create files.",
                    )
                try:
                    target = (self.repo_root / p_str).resolve()
                    if target.exists() and not target.is_dir():
                        return BeforeOutcome(
                            params=params,
                            blocked=True,
                            reason=f"Path '{p_str}' exists and is a file. Cannot create directory here.",
                        )
                except Exception:
                    pass

        return BeforeOutcome(params=params)

    def after(self, *, tool_name: str, params: Dict[str, Any], result: ToolCallResult, ctx: ToolCallContextLike) -> AfterOutcome:
        if tool_name in ("fs.read_file", "fs_read_file") and result.success:
            output = result.output or {}
            content = output.get("content") or output.get("result")
            if isinstance(content, str) and len(content) > 20000:
                h, t = content[:5000], content[-2000:]
                msg = f"\n... [SmartFS: Truncated {len(content)} chars] ...\n"
                truncated = h + msg + t
                new_output = dict(output)
                if "content" in new_output: new_output["content"] = truncated
                if "result" in new_output: new_output["result"] = truncated
                
                new_result = ToolCallResult(
                    tool_name=result.tool_name,
                    success=result.success,
                    output=new_output,
                    error=result.error,
                    meta=result.meta
                )
                return AfterOutcome(result=new_result)
        return AfterOutcome(result=result)
