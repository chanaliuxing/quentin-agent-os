from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict

from quentin.tools.middleware.base import BeforeOutcome, AfterOutcome, ToolMiddlewareChain
from quentin.tools.schemas import ToolCallResult


@dataclass
class _Ctx:
    metadata: Dict[str, Any] | None = None


class _MwA:
    id = "a"
    priority = 10

    def before(self, *, tool_name: str, params: Dict[str, Any], ctx: _Ctx) -> BeforeOutcome:
        p = dict(params)
        p["order"] = p.get("order", "") + "A"
        return BeforeOutcome(params=p, ctx_metadata_delta={"a_before": True})

    def after(self, *, tool_name: str, params: Dict[str, Any], result: ToolCallResult, ctx: _Ctx) -> AfterOutcome:
        result.meta["after_order"] = result.meta.get("after_order", "") + "A"
        return AfterOutcome(result=result, ctx_metadata_delta={"a_after": True})


class _MwB:
    id = "b"
    priority = 5

    def before(self, *, tool_name: str, params: Dict[str, Any], ctx: _Ctx) -> BeforeOutcome:
        p = dict(params)
        p["order"] = p.get("order", "") + "B"
        return BeforeOutcome(params=p, ctx_metadata_delta={"b_before": True})

    def after(self, *, tool_name: str, params: Dict[str, Any], result: ToolCallResult, ctx: _Ctx) -> AfterOutcome:
        result.meta["after_order"] = result.meta.get("after_order", "") + "B"
        return AfterOutcome(result=result, ctx_metadata_delta={"b_after": True})


def test_tool_middleware_chain_before_order_and_after_reverse() -> None:
    ctx = _Ctx(metadata={})
    chain = ToolMiddlewareChain([_MwA(), _MwB()])

    params, _ = chain.run_before(tool_name="x", params={}, ctx=ctx)
    assert params["order"] == "AB"

    res = ToolCallResult(tool_name="x", success=True, output={}, error=None, meta={})
    res2 = chain.run_after(tool_name="x", params=params, result=res, ctx=ctx)
    assert res2.meta["after_order"] == "BA"
    assert isinstance(ctx.metadata, dict)
    assert "tool_middleware" in ctx.metadata

