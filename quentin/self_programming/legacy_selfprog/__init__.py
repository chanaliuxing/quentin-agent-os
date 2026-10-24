from __future__ import annotations

from quentin.self_programming.legacy_selfprog.models import Patch, PatchEvalReport
from quentin.self_programming.legacy_selfprog.registry import FileBackedPatchRegistry
from quentin.self_programming.legacy_selfprog.engine import (
    SelfProgrammingEngine,
    PatchTaskSpec,
    PatchResult,
    PatchTestResult,
    PatchGateResult,
    PatchGateCouncil,
)
from quentin.self_programming.legacy_selfprog.apply import PatchApplier

__all__ = [
    "Patch",
    "PatchEvalReport",
    "FileBackedPatchRegistry",
    "SelfProgrammingEngine",
    "PatchTaskSpec",
    "PatchResult",
    "PatchTestResult",
    "PatchGateResult",
    "PatchGateCouncil",
    "PatchApplier",
]

