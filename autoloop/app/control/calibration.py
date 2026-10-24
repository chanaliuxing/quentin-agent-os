from __future__ import annotations

import json
from pathlib import Path

from app.config import settings


class EnergyCalibrator:
    def __init__(self, state_path: Path | None = None, alpha: float = 0.2) -> None:
        self.state_path = state_path or (settings.runtime_dir / "control" / "energy_calibration.json")
        self.alpha = alpha
        self._state = self._load_state()

    def overlap_penalty(self, risk: str) -> float:
        penalties = self._state["overlap_penalties"]
        return float(penalties.get(risk, penalties["none"]))

    def unresolved_failure_penalty(self) -> float:
        return float(self._state["unresolved_failure_penalty"])

    def invariant_penalty(self) -> float:
        return float(self._state["invariant_penalty"])

    def update(self, *, weighted_score: float, succeeded: bool) -> None:
        target = 1.0 if succeeded else 0.0
        score_error = target - weighted_score
        self._state["mean_score_error"] = (
            (1 - self.alpha) * self._state["mean_score_error"] + self.alpha * score_error
        )
        adjust = max(-0.02, min(0.02, -self._state["mean_score_error"] * 0.05))
        for key in ["low", "medium", "high"]:
            self._state["overlap_penalties"][key] = max(
                0.0, min(0.3, self._state["overlap_penalties"][key] + adjust)
            )
        self._state["invariant_penalty"] = max(
            0.02, min(0.2, self._state["invariant_penalty"] + adjust / 2)
        )
        self._state["unresolved_failure_penalty"] = max(
            0.01, min(0.2, self._state["unresolved_failure_penalty"] + adjust / 2)
        )
        self._save_state()

    def _load_state(self) -> dict:
        if self.state_path.exists():
            return json.loads(self.state_path.read_text(encoding="utf-8"))
        state = {
            "mean_score_error": 0.0,
            "overlap_penalties": {
                "none": 0.0,
                "low": 0.03,
                "medium": 0.08,
                "high": 0.15,
            },
            "invariant_penalty": 0.1,
            "unresolved_failure_penalty": 0.05,
        }
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.state_path.write_text(json.dumps(state, indent=2), encoding="utf-8")
        return state

    def _save_state(self) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.state_path.write_text(json.dumps(self._state, indent=2), encoding="utf-8")
