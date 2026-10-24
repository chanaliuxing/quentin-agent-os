from __future__ import annotations

from app.models import (
    AgentRole,
    AgentStatus,
    ProjectState,
    RepairDecision,
    RepairExecutionResult,
    RepairExecutionStatus,
    RollbackTargetLayer,
)
from app.rollback.checkpoints import CheckpointStore
from app.rollback.restore import RestoreManager
from app.rollback.scopes import resolve_scope_modules
from app.sor import SorRepository, module_ids_from_scope_tokens
from app.provenance import ProvenanceStore
from app.models import ProvenanceRelation


class RollbackManager:
    def __init__(
        self,
        checkpoint_store: CheckpointStore | None = None,
        restore_manager: RestoreManager | None = None,
        sor_repository: SorRepository | None = None,
        provenance_store: ProvenanceStore | None = None,
    ) -> None:
        self.checkpoint_store = checkpoint_store or CheckpointStore()
        self.restore_manager = restore_manager or RestoreManager()
        self.sor_repository = sor_repository or SorRepository()
        self.provenance_store = provenance_store or ProvenanceStore()

    def execute(self, state: ProjectState, decision: RepairDecision) -> RepairExecutionResult:
        checkpoint = self.checkpoint_store.create_phase_checkpoint(state)
        self.restore_manager.save_artifact_snapshot(checkpoint=checkpoint, artifacts=dict(state.artifacts))
        phase = state.get_current_phase()
        if phase is None:
            return RepairExecutionResult(
                run_id=decision.run_id,
                phase_id=decision.phase_id,
                decision=decision,
                execution_status=RepairExecutionStatus.FAILED,
                notes=["phase not found"],
            )

        phase.repair_decision = decision
        phase.status = "repairing"
        phase.agent_statuses[AgentRole.DEV.value] = AgentStatus.PENDING
        phase.agent_statuses[AgentRole.QA.value] = AgentStatus.PENDING
        phase.test_results = []
        phase.git_overlaps = []

        state.artifacts[f"{phase.phase_id}_checkpoint"] = checkpoint.model_dump(mode="json")
        state.artifacts[f"{phase.phase_id}_rollback_scope"] = {
            "target_layer": decision.rollback_target_layer.value,
            "scope": list(decision.rollback_scope),
            "scope_source": decision.scope_source,
            "scope_confidence": decision.scope_confidence,
        }
        resolved_scope_modules = resolve_scope_modules(
            module_names=list(decision.affected_modules),
            rollback_scope=list(decision.rollback_scope),
            affected_modules=list(decision.affected_modules),
        )
        try:
            spec = self.sor_repository.load_project_spec(decision.run_id)
            sor_scope_modules = module_ids_from_scope_tokens(
                spec=spec,
                scope_tokens=list(decision.rollback_scope),
            )
            for module_id in sor_scope_modules:
                if module_id not in resolved_scope_modules:
                    resolved_scope_modules.append(module_id)
        except Exception:
            pass

        if decision.rollback_target_layer != RollbackTargetLayer.IMPLEMENTATION:
            state.artifacts = self.restore_manager.restore_artifacts(checkpoint=checkpoint)

        state.artifacts[f"{phase.phase_id}_resolved_scope_modules"] = resolved_scope_modules

        execution = RepairExecutionResult(
            run_id=decision.run_id,
            phase_id=decision.phase_id,
            decision=decision,
            execution_status=RepairExecutionStatus.EXECUTED,
            touched_modules=resolved_scope_modules or list(decision.affected_modules),
            generated_task_ids=[],
            notes=[
                f"checkpoint={checkpoint.checkpoint_id}",
                f"scope_source={decision.scope_source}",
                f"scope_confidence={decision.scope_confidence}",
            ],
        )
        phase.repair_execution = execution
        event = self.provenance_store.record_event(
            run_id=decision.run_id,
            phase_id=decision.phase_id,
            artifact_id=f"repair:{decision.phase_id}",
            event_type="rollback_executed",
            payload={
                "target_layer": decision.rollback_target_layer.value,
                "resolved_scope_modules": resolved_scope_modules,
                "scope_source": decision.scope_source,
                "scope_confidence": decision.scope_confidence,
            },
        )
        self.provenance_store.record_edge(
            run_id=decision.run_id,
            src_artifact_id=f"decision:{decision.phase_id}",
            dst_artifact_id=event.artifact_id,
            relation=ProvenanceRelation.REPAIRED_BY,
        )
        return execution

    def next_action_for(self, decision: RepairDecision) -> str:
        if decision.rollback_target_layer == RollbackTargetLayer.IMPLEMENTATION:
            return "dispatch_dev"
        return "lead_plan"
