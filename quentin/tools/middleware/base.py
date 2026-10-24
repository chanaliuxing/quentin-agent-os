from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Protocol, Sequence, Tuple

from quentin.tools.schemas import ToolCallResult


class ToolCallContextLike(Protocol):
    metadata: Optional[Dict[str, Any]]


@dataclass(frozen=True)
class BeforeOutcome:
    params: Dict[str, Any]
    blocked: bool = False
    reason: str = ""
    ctx_metadata_delta: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AfterOutcome:
    result: ToolCallResult
    ctx_metadata_delta: Dict[str, Any] = field(default_factory=dict)


class ToolMiddleware(Protocol):
    id: str
    priority: int

    def before(self, *, tool_name: str, params: Dict[str, Any], ctx: ToolCallContextLike) -> BeforeOutcome: ...

    def after(self, *, tool_name: str, params: Dict[str, Any], result: ToolCallResult, ctx: ToolCallContextLike) -> AfterOutcome: ...


def _merge_ctx_metadata(ctx: ToolCallContextLike, delta: Dict[str, Any]) -> None:
    if not delta:
        return
    if ctx.metadata is None:
        ctx.metadata = {}
    # Keep a trace of middleware effects without overwriting user metadata.
    mw = ctx.metadata.get("tool_middleware")
    if not isinstance(mw, dict):
        mw = {}
        ctx.metadata["tool_middleware"] = mw
    for k, v in delta.items():
        if k not in mw:
            mw[k] = v


class ToolMiddlewareChain:
    def __init__(self, middlewares: Sequence[ToolMiddleware]) -> None:
        self._middlewares = list(middlewares)

    @property
    def middlewares(self) -> List[ToolMiddleware]:
        return list(self._middlewares)

    @staticmethod
    def order(middlewares: Sequence[ToolMiddleware]) -> List[ToolMiddleware]:
        items = list(middlewares)
        items.sort(key=lambda m: (-int(getattr(m, "priority", 0) or 0), str(getattr(m, "id", ""))))
        return items

    def run_before(self, *, tool_name: str, params: Dict[str, Any], ctx: ToolCallContextLike) -> Tuple[Dict[str, Any], ToolCallContextLike]:
        cur = dict(params or {})
        for mw in self._middlewares:
            out = mw.before(tool_name=tool_name, params=cur, ctx=ctx)
            _merge_ctx_metadata(ctx, dict(out.ctx_metadata_delta or {}))
            if out.blocked:
                raise PermissionError(out.reason or "tool blocked by middleware")
            cur = dict(out.params or cur)
        return cur, ctx

    def run_after(self, *, tool_name: str, params: Dict[str, Any], result: ToolCallResult, ctx: ToolCallContextLike) -> ToolCallResult:
        cur = result
        # unwind in reverse order (LIFO) for symmetry
        for mw in reversed(self._middlewares):
            out = mw.after(tool_name=tool_name, params=params, result=cur, ctx=ctx)
            _merge_ctx_metadata(ctx, dict(out.ctx_metadata_delta or {}))
            cur = out.result
        return cur
