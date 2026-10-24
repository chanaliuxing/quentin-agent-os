import json
from pathlib import Path

import pytest

from app.module_main import (
    AcquisitionTrack,
    ExecutionStep,
    ModuleMainResult,
    StepResult,
    build_phase_result_payload,
    normalize_phase_id,
    write_phase_result_artifact,
)
from app.module_main.artifacts import validate_phase_result_artifact, validate_phase_result_payload


def _build_module_result() -> ModuleMainResult:
    return ModuleMainResult(
        task="Automate desktop workflow",
        steps=[
            ExecutionStep(
                step_id="step_01",
                description="Automate desktop workflow",
                required_capability="desktop_automation",
            )
        ],
        step_results=[
            StepResult(
                step_id="step_01",
                track=AcquisitionTrack.MCP_TOOL,
                executor="desktop_mcp",
                success=True,
                output="ok",
            )
        ],
        memory_updates=["step_01:mcp_tool:ok"],
        reflection="Executed 1 steps with 1 successes; MCP steps=1, self_programming steps=0.",
        next_investment_area="execution_efficiency",
    )


def test_build_phase_result_payload_has_contract_shape():
    payload = build_phase_result_payload(phase_id="phase_01", module_result=_build_module_result())

    assert payload["contract_version"] == "1.0"
    assert payload["phase_id"] == "phase_01"
    assert payload["module_name"] == "module_main"
    assert payload["summary"]["total_steps"] == 1
    assert payload["summary"]["successful_steps"] == 1
    assert payload["summary"]["failed_steps"] == 0
    assert payload["step_results"][0]["track"] == "mcp_tool"


def test_normalize_phase_id_rejects_invalid_characters():
    with pytest.raises(ValueError, match="invalid characters"):
        normalize_phase_id("../phase_01")


def test_normalize_phase_id_rejects_non_string_input():
    with pytest.raises(TypeError, match="must be a string"):
        normalize_phase_id(123)  # type: ignore[arg-type]


def test_normalize_phase_id_rejects_boolean_input():
    with pytest.raises(TypeError, match="must be a string"):
        normalize_phase_id(True)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_write_phase_result_artifact_persists_json(tmp_path):
    artifact_path = await write_phase_result_artifact(
        phase_id="phase_01",
        module_result=_build_module_result(),
        artifact_root=tmp_path / "app" / "module_main" / "artifacts",
    )

    assert artifact_path == tmp_path / "app" / "module_main" / "artifacts" / "phase_01_result.json"
    payload = json.loads(artifact_path.read_text(encoding="utf-8"))
    assert payload["module_name"] == "module_main"
    assert payload["phase_id"] == "phase_01"


@pytest.mark.asyncio
async def test_write_phase_result_artifact_accepts_string_artifact_root(tmp_path):
    artifact_root = str(tmp_path / "app" / "module_main" / "artifacts")
    artifact_path = await write_phase_result_artifact(
        phase_id="phase_01",
        module_result=_build_module_result(),
        artifact_root=artifact_root,
    )

    assert artifact_path == Path(artifact_root) / "phase_01_result.json"
    assert artifact_path.exists()


@pytest.mark.asyncio
async def test_write_phase_result_artifact_rejects_boolean_artifact_root():
    with pytest.raises(TypeError, match="path-like"):
        await write_phase_result_artifact(
            phase_id="phase_01",
            module_result=_build_module_result(),
            artifact_root=True,
        )


@pytest.mark.asyncio
async def test_write_phase_result_artifact_rejects_invalid_phase_id(tmp_path):
    with pytest.raises(ValueError, match="invalid characters"):
        await write_phase_result_artifact(
            phase_id="../phase_01",
            module_result=_build_module_result(),
            artifact_root=tmp_path / "app" / "module_main" / "artifacts",
        )


def test_validate_phase_result_payload_rejects_invalid_generated_at():
    payload = build_phase_result_payload(phase_id="phase_01", module_result=_build_module_result())
    payload["generated_at"] = "not-a-datetime"

    with pytest.raises(ValueError, match="ISO-8601"):
        validate_phase_result_payload(payload, required_phase_id="phase_01")


def test_validate_phase_result_payload_rejects_contract_version_mismatch():
    payload = build_phase_result_payload(phase_id="phase_01", module_result=_build_module_result())
    payload["contract_version"] = "2.0"

    with pytest.raises(ValueError, match="contract_version mismatch"):
        validate_phase_result_payload(payload, required_phase_id="phase_01")


def test_validate_phase_result_payload_rejects_non_string_memory_updates():
    payload = build_phase_result_payload(phase_id="phase_01", module_result=_build_module_result())
    payload["memory_updates"] = ["ok", 1]

    with pytest.raises(ValueError, match="entries must be strings"):
        validate_phase_result_payload(payload, required_phase_id="phase_01")


def test_validate_phase_result_payload_rejects_empty_memory_updates_entries():
    payload = build_phase_result_payload(phase_id="phase_01", module_result=_build_module_result())
    payload["memory_updates"] = ["step_01:mcp_tool:ok", "   "]

    with pytest.raises(ValueError, match="non-empty strings"):
        validate_phase_result_payload(payload, required_phase_id="phase_01")


def test_validate_phase_result_payload_rejects_memory_updates_length_mismatch():
    payload = build_phase_result_payload(phase_id="phase_01", module_result=_build_module_result())
    payload["memory_updates"] = []

    with pytest.raises(ValueError, match="memory_updates length"):
        validate_phase_result_payload(payload, required_phase_id="phase_01")


def test_validate_phase_result_payload_rejects_empty_next_investment_area():
    payload = build_phase_result_payload(phase_id="phase_01", module_result=_build_module_result())
    payload["summary"]["next_investment_area"] = "   "

    with pytest.raises(ValueError, match="next_investment_area"):
        validate_phase_result_payload(payload, required_phase_id="phase_01")


def test_validate_phase_result_payload_rejects_misaligned_step_results():
    payload = build_phase_result_payload(phase_id="phase_01", module_result=_build_module_result())
    payload["step_results"][0]["step_id"] = "step_99"

    with pytest.raises(ValueError, match="align with steps"):
        validate_phase_result_payload(payload, required_phase_id="phase_01")


def test_validate_phase_result_payload_rejects_misaligned_memory_updates():
    payload = build_phase_result_payload(phase_id="phase_01", module_result=_build_module_result())
    payload["memory_updates"] = ["step_01:mcp_tool:fail"]

    with pytest.raises(ValueError, match="memory_updates must align with step_results"):
        validate_phase_result_payload(payload, required_phase_id="phase_01")


def test_validate_phase_result_payload_accepts_aligned_memory_updates():
    payload = build_phase_result_payload(phase_id="phase_01", module_result=_build_module_result())
    payload["memory_updates"] = ["step_01:mcp_tool:ok"]

    validate_phase_result_payload(payload, required_phase_id="phase_01")


def test_validate_phase_result_payload_rejects_inconsistent_summary_counts():
    payload = build_phase_result_payload(phase_id="phase_01", module_result=_build_module_result())
    payload["summary"]["successful_steps"] = 0
    payload["summary"]["failed_steps"] = 1

    with pytest.raises(ValueError, match="do not match step_results"):
        validate_phase_result_payload(payload, required_phase_id="phase_01")


def test_validate_phase_result_payload_rejects_boolean_summary_counts():
    payload = build_phase_result_payload(phase_id="phase_01", module_result=_build_module_result())
    payload["summary"]["total_steps"] = True

    with pytest.raises(ValueError, match="must be integers"):
        validate_phase_result_payload(payload, required_phase_id="phase_01")


def test_checked_in_phase_result_artifact_matches_contract():
    artifact_path = Path("app/module_main/artifacts/phase_01_result.json")

    payload = json.loads(artifact_path.read_text(encoding="utf-8"))

    validate_phase_result_payload(payload, required_phase_id="phase_01", required_module_name="module_main")
    assert payload["contract_version"] == "1.0"


def test_checked_in_probe_phase_result_artifact_matches_contract():
    artifact_path = Path("app/module_main/artifacts/phase_probe_session_policy_agent_spec_result.json")

    payload = json.loads(artifact_path.read_text(encoding="utf-8"))

    validate_phase_result_payload(
        payload,
        required_phase_id="phase_probe_session_policy_agent_spec",
        required_module_name="module_main",
    )
    assert payload["contract_version"] == "1.0"


def test_checked_in_probe_window_phase_result_artifact_matches_contract():
    artifact_path = Path("app/module_main/artifacts/phase_probe_session_policy_window_result.json")

    payload = json.loads(artifact_path.read_text(encoding="utf-8"))

    validate_phase_result_payload(
        payload,
        required_phase_id="phase_probe_session_policy_window",
        required_module_name="module_main",
    )
    assert payload["contract_version"] == "1.0"


@pytest.mark.asyncio
async def test_validate_phase_result_artifact_rejects_invalid_json(tmp_path):
    artifact_path = tmp_path / "app" / "module_main" / "artifacts" / "phase_01_result.json"
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    artifact_path.write_text("{invalid", encoding="utf-8")

    with pytest.raises(ValueError, match="invalid JSON"):
        await validate_phase_result_artifact(artifact_path, required_phase_id="phase_01")


@pytest.mark.asyncio
async def test_validate_phase_result_artifact_rejects_non_object_payload(tmp_path):
    artifact_path = tmp_path / "app" / "module_main" / "artifacts" / "phase_01_result.json"
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    artifact_path.write_text("[]", encoding="utf-8")

    with pytest.raises(ValueError, match="must be an object"):
        await validate_phase_result_artifact(artifact_path, required_phase_id="phase_01")
