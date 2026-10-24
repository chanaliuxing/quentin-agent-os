from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict, Optional

PhaseName = str  # planning | executing | reflecting
CorrectionIntensity = str  # low | medium | high | critical


@dataclass
class PhasePayload:
    phase: PhaseName
    state_machine: str = "cognitive_attempt_v1"
    template_id: str = "generic_v1"
    attempt_stage: str = "initial"  # initial | retry | stuck
    correction_intensity: CorrectionIntensity = "medium"
    correction_focus: str = ""
    reason: str = ""
    directives: list[str] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.directives is None:
            self.directives = []

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


_PHASE_TEMPLATE_IDS: Dict[str, str] = {
    "planning": "planning_v1",
    "executing": "executing_v1",
    "reflecting": "reflecting_v1",
}

_PLANNING_STAGE_TEMPLATE_IDS: Dict[str, str] = {
    "initial": "planning_initial_v1",
    "retry": "planning_retry_v1",
    "stuck": "planning_stuck_v1",
}

_PHASE_FOCUS: Dict[str, str] = {
    "planning": "Prefer safer decomposition and stronger prechecks before risky actions.",
    "executing": "Prefer deterministic tool calls; avoid speculative or repeated failed actions.",
    "reflecting": "Identify root cause precisely and generate concrete correction strategy.",
}


def normalize_phase(phase: Optional[str]) -> str:
    p = str(phase or "").strip().lower()
    if p in {"planning", "executing", "reflecting"}:
        return p
    return "planning"


def build_phase_payload(
    *,
    phase: Optional[str],
    attempt_stage: Optional[str] = None,
    correction_intensity: Optional[str] = None,
    reason: str = "",
    directives: Optional[list[str]] = None,
) -> PhasePayload:
    p = normalize_phase(phase)
    stage = str(attempt_stage or "initial").strip().lower()
    if stage not in {"initial", "retry", "stuck"}:
        stage = "initial"
    intensity = str(correction_intensity or "medium").strip().lower() or "medium"
    if intensity not in {"low", "medium", "high", "critical"}:
        intensity = "medium"
    template_id = _PHASE_TEMPLATE_IDS.get(p, "generic_v1")
    if p == "planning":
        template_id = _PLANNING_STAGE_TEMPLATE_IDS.get(stage, template_id)
    return PhasePayload(
        phase=p,
        template_id=template_id,
        attempt_stage=stage,
        correction_intensity=intensity,
        correction_focus=_PHASE_FOCUS.get(p, ""),
        reason=str(reason or ""),
        directives=list(directives or []),
    )
