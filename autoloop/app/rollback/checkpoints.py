from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models import ProjectState


class CheckpointRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    checkpoint_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    phase_id: str = Field(min_length=1)
    created_at: datetime = Field(default_factory=datetime.now)
    snapshot: dict


class CheckpointStore:
    def create_phase_checkpoint(self, state: ProjectState) -> CheckpointRef:
        phase = state.get_current_phase()
        phase_id = phase.phase_id if phase else f"phase_{state.current_phase:02d}"
        snapshot = {
            "artifacts": dict(state.artifacts),
            "energy_history_size": len(state.energy_history),
            "phase_status": phase.status if phase else "missing",
            "review_loops": phase.review_loops if phase else 0,
        }
        return CheckpointRef(
            checkpoint_id=f"checkpoint_{phase_id}_{len(state.transition_history)}",
            run_id=state.project_id,
            phase_id=phase_id,
            snapshot=snapshot,
        )
