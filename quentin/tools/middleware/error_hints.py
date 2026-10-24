from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict

from quentin.tools.middleware.base import AfterOutcome, BeforeOutcome
from quentin.tools.schemas import ToolCallResult


@dataclass(frozen=True)
class ErrorHintsMiddleware:
    """
    Heuristic "gentle traps" for tool errors (P1-C).

    This middleware only annotates ToolCallResult; it does not bypass SafetyKernel.
    """

    id: str = "error_hints"
    priority: int = 10

    def before(self, *, tool_name: str, params: Dict[str, Any], ctx: Any) -> BeforeOutcome:
        return BeforeOutcome(params=dict(params or {}), blocked=False, reason="", ctx_metadata_delta={})

    def after(self, *, tool_name: str, params: Dict[str, Any], result: ToolCallResult, ctx: Any) -> AfterOutcome:
        out = result.output if isinstance(result.output, dict) else {}
        if not isinstance(out, dict):
            out = {}

        # Normalize common "dict result" shape into ToolCallResult fields.
        status = str(out.get("status") or "").strip().lower()
        if status == "error" and result.success:
            result.success = False

        if not result.success:
            if result.error is None and isinstance(out.get("error"), str):
                result.error = str(out.get("error") or "").strip() or result.error

            hint = out.get("hint")
            if isinstance(hint, str) and hint.strip():
                result.meta.setdefault("hint", hint.strip())
            next_actions = out.get("next_actions")
            if isinstance(next_actions, list):
                cleaned = [str(x).strip() for x in next_actions if str(x).strip()]
                if cleaned:
                    result.meta.setdefault("next_actions", cleaned[:12])

            # Heuristics for common error patterns.
            err_s = str(result.error or "") or str(out.get("error") or "")
            if "Search string not found" in err_s or "Multiple occurrences" in err_s:
                result.meta.setdefault(
                    "hint",
                    "For fs.search_replace: read the file first and copy an exact unique snippet, then retry.",
                )
            if "Interactive command" in err_s or "Interactive TTY programs" in err_s:
                result.meta.setdefault(
                    "hint",
                    "Avoid interactive TTY tools (nano/vim/less/man). Use fs.* tools or non-interactive shell commands.",
                )
            
            if "No such file or directory" in err_s or "FileNotFoundError" in err_s:
                result.meta.setdefault(
                    "hint",
                    "Use 'ls' or 'find' to discover the actual file paths before assuming they exist.",
                )
            
            if "Permission denied" in err_s:
                result.meta.setdefault(
                    "hint",
                    "You lack permissions for this path. Use 'pwd' to check your current working directory and stay within project scope.",
                )

            if "git" in tool_name.lower() and "rebase" in err_s:
                result.meta.setdefault(
                    "hint",
                    "Interactive rebase is not supported. Use 'git merge' or simple 'git commit' instead.",
                )

        return AfterOutcome(result=result, ctx_metadata_delta={})

