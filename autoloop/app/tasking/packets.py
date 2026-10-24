from __future__ import annotations

from typing import Any

from app.models import ModuleExecutionView, ResultPacket, TaskPacket


def build_task_packet(
    *,
    run_id: str,
    phase_id: str,
    agent: str,
    module_view: ModuleExecutionView,
) -> TaskPacket:
    return TaskPacket(
        task_id=f"task_{phase_id}_{module_view.module_id}_{agent}",
        run_id=run_id,
        phase_id=phase_id,
        module_id=module_view.module_id,
        agent=agent,
        sor_refs=module_view.sor_refs,
        input_artifact_ids=module_view.input_artifact_refs,
        writable_paths=module_view.writable_paths,
        expected_output_contract="result_packet.schema.json",
        gate_expectations=module_view.gate_expectations,
    )


def build_result_packet(
    *,
    task_packet: TaskPacket,
    produced_artifact_ids: list[str],
    contract_payload: dict[str, Any],
    claimed_file_changes: list[str],
) -> ResultPacket:
    return ResultPacket(
        result_id=f"result_{task_packet.task_id}",
        task_id=task_packet.task_id,
        run_id=task_packet.run_id,
        phase_id=task_packet.phase_id,
        module_id=task_packet.module_id,
        agent=task_packet.agent,
        produced_artifact_ids=produced_artifact_ids,
        contract_payload=contract_payload,
        claimed_file_changes=claimed_file_changes,
    )
