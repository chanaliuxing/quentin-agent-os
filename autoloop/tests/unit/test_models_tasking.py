import pytest
from pydantic import ValidationError

from app.models import PromptPacket, ResultPacket, TaskPacket


def test_task_packet_requires_writable_paths():
    with pytest.raises(ValidationError):
        TaskPacket(
            task_id="task_dev_01",
            run_id="run_01",
            phase_id="phase_01",
            module_id="module_alpha",
            agent="dev",
            sor_refs=["module:module_alpha"],
            input_artifact_ids=["artifact_plan_01"],
            writable_paths=[],
            expected_output_contract="contracts/dev_result.json",
            gate_expectations=["unit_pass"],
        )


def test_result_packet_requires_task_id():
    with pytest.raises(ValidationError):
        ResultPacket(
            result_id="result_01",
            task_id="",
            run_id="run_01",
            phase_id="phase_01",
            module_id="module_alpha",
            agent="dev",
            produced_artifact_ids=[],
            contract_payload={},
            claimed_file_changes=[],
        )


def test_every_packet_carries_run_and_phase_ids():
    task = TaskPacket(
        task_id="task_dev_01",
        run_id="run_01",
        phase_id="phase_01",
        module_id="module_alpha",
        agent="dev",
        sor_refs=["module:module_alpha"],
        input_artifact_ids=["artifact_plan_01"],
        writable_paths=["app/module_alpha.py"],
        expected_output_contract="contracts/dev_result.json",
        gate_expectations=["unit_pass"],
    )
    result = ResultPacket(
        result_id="result_01",
        task_id=task.task_id,
        run_id=task.run_id,
        phase_id=task.phase_id,
        module_id=task.module_id,
        agent=task.agent,
        produced_artifact_ids=["artifact_impl_01"],
        contract_payload={"status": "success"},
        claimed_file_changes=["app/module_alpha.py"],
    )
    prompt = PromptPacket(
        prompt_id="prompt_01",
        task_id=task.task_id,
        run_id=task.run_id,
        phase_id=task.phase_id,
        module_id=task.module_id,
        agent=task.agent,
        system_prompt="follow the packet",
        user_prompt="implement module alpha",
        rendered_task_markdown="# Task",
    )
    assert task.run_id == result.run_id == prompt.run_id == "run_01"
    assert task.phase_id == result.phase_id == prompt.phase_id == "phase_01"
