from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Protocol

from quentin.cognitive.perception.schemas import ExpectedState, PredictionError


class ExpectationEngine(Protocol):
    def build_expected(self, *, situation_id: str, tool_name: str, step: Dict[str, Any], ctx: Dict[str, Any]) -> ExpectedState: ...
    def compute_error(self, *, expected: ExpectedState, observed: Dict[str, Any], ctx: Dict[str, Any]) -> Optional[PredictionError]: ...


@dataclass
class TemplateExpectationEngine:
    """
    v0 expectation engine: template-light and conservative.

    This implementation is intentionally minimal:
    - expected markers are mostly generic success markers
    - prediction_error is derived from tool call result shape
    """

    def build_expected(self, *, situation_id: str, tool_name: str, step: Dict[str, Any], ctx: Dict[str, Any]) -> ExpectedState:
        _ = step, ctx
        markers: List[str] = [f"tool_call_success:{tool_name}"]
        return ExpectedState(situation_id=situation_id or "unknown", markers=markers, template_id=None, fallback_skills=[])

    def compute_error(self, *, expected: ExpectedState, observed: Dict[str, Any], ctx: Dict[str, Any]) -> Optional[PredictionError]:
        _ = ctx
        # observed is expected to be a ToolCallResult-like dict from ToolManager
        success = None
        if isinstance(observed, dict):
            if "success" in observed:
                success = bool(observed.get("success"))
            elif isinstance(observed.get("output"), dict) and observed.get("output", {}).get("status") == "ok":
                success = True

        if success is True:
            return None
        return PredictionError(
            error_type="tool_call_failed",
            severity="medium",
            missing_markers=list(expected.markers or []),
            observed_markers=[],
            details={"hint": "tool call returned success=false or missing success flag"},
        )

