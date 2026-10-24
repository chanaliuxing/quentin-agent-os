import json

import pytest

from app.module_main import (
    ToolCapability,
    ToolLearningRegistry,
    run_module_main_phase,
    run_phase_01_module_main,
)


@pytest.mark.asyncio
async def test_run_phase_01_module_main_writes_and_validates_artifact(tmp_path):
    artifact_path = await run_phase_01_module_main(
        task="Automate desktop workflow",
        artifact_root=tmp_path / "app" / "module_main" / "artifacts",
    )

    assert artifact_path.exists()
    assert artifact_path.name == "phase_01_result.json"
    payload = json.loads(artifact_path.read_text(encoding="utf-8"))
    assert payload["step_results"][0]["track"] == "mcp_tool"
    assert payload["step_results"][0]["executor"] == "desktop_mcp"


@pytest.mark.asyncio
async def test_run_module_main_phase_writes_custom_phase_artifact(tmp_path):
    artifact_path = await run_module_main_phase(
        task="Automate desktop workflow",
        artifact_root=tmp_path / "app" / "module_main" / "artifacts",
        phase_id="phase_01_custom",
    )

    assert artifact_path.exists()
    assert artifact_path.name == "phase_01_custom_result.json"
    payload = json.loads(artifact_path.read_text(encoding="utf-8"))
    assert payload["phase_id"] == "phase_01_custom"
    assert payload["module_name"] == "module_main"


@pytest.mark.asyncio
async def test_run_phase_01_module_main_rolls_back_artifact_on_validation_failure(tmp_path, monkeypatch):
    from app.module_main import pipeline

    async def _force_validation_failure(*args, **kwargs):
        raise ValueError("forced validation failure")

    monkeypatch.setattr(pipeline, "validate_phase_result_artifact", _force_validation_failure)

    artifact_root = tmp_path / "app" / "module_main" / "artifacts"
    with pytest.raises(ValueError, match="forced validation failure"):
        await run_phase_01_module_main(
            task="Automate desktop workflow",
            artifact_root=artifact_root,
            phase_id="phase_01",
            rollback_on_failure=True,
        )

    assert (artifact_root / "phase_01_result.json").exists() is False


@pytest.mark.asyncio
async def test_run_phase_01_module_main_rejects_invalid_phase_id(tmp_path):
    artifact_root = tmp_path / "app" / "module_main" / "artifacts"
    with pytest.raises(ValueError, match="invalid characters"):
        await run_phase_01_module_main(
            task="Automate desktop workflow",
            artifact_root=artifact_root,
            phase_id="../phase_01",
        )

    assert artifact_root.exists() is False


@pytest.mark.asyncio
async def test_run_phase_01_module_main_respects_explicit_empty_tool_list(tmp_path):
    artifact_path = await run_phase_01_module_main(
        task="Automate desktop workflow",
        tools=[],
        artifact_root=tmp_path / "app" / "module_main" / "artifacts",
    )

    payload = json.loads(artifact_path.read_text(encoding="utf-8"))
    assert payload["step_results"][0]["track"] == "self_programming"
    assert payload["step_results"][0]["executor"] == "self_programming_engine"


@pytest.mark.asyncio
async def test_run_phase_01_module_main_supports_tool_registry(tmp_path):
    registry = ToolLearningRegistry(
        tools=[ToolCapability(tool_name="desktop_mcp", capabilities=["desktop_automation"], reliability=0.95)]
    )
    artifact_path = await run_phase_01_module_main(
        task="Automate desktop workflow",
        tool_registry=registry,
        artifact_root=tmp_path / "app" / "module_main" / "artifacts",
    )

    payload = json.loads(artifact_path.read_text(encoding="utf-8"))
    assert payload["step_results"][0]["track"] == "mcp_tool"
    assert payload["step_results"][0]["executor"] == "desktop_mcp"


@pytest.mark.asyncio
async def test_run_phase_01_module_main_registry_records_execution_observations(tmp_path):
    registry = ToolLearningRegistry(
        tools=[ToolCapability(tool_name="desktop_mcp", capabilities=["desktop_automation"], reliability=0.95)]
    )
    await run_phase_01_module_main(
        task="Automate desktop workflow",
        tool_registry=registry,
        artifact_root=tmp_path / "app" / "module_main" / "artifacts",
    )

    assert registry.get_observation_counts("desktop_mcp") == (1, 1)


@pytest.mark.asyncio
async def test_run_phase_01_module_main_rejects_mixed_tools_and_registry(tmp_path):
    registry = ToolLearningRegistry(
        tools=[ToolCapability(tool_name="desktop_mcp", capabilities=["desktop_automation"], reliability=0.95)]
    )
    with pytest.raises(ValueError, match="mutually exclusive"):
        await run_phase_01_module_main(
            task="Automate desktop workflow",
            tools=[],
            tool_registry=registry,
            artifact_root=tmp_path / "app" / "module_main" / "artifacts",
        )


@pytest.mark.asyncio
async def test_run_phase_01_module_main_rejects_invalid_tools_entries(tmp_path):
    with pytest.raises(TypeError, match="ToolCapability"):
        await run_phase_01_module_main(
            task="Automate desktop workflow",
            tools=[123],  # type: ignore[list-item]
            artifact_root=tmp_path / "app" / "module_main" / "artifacts",
        )


@pytest.mark.asyncio
async def test_run_phase_01_module_main_accepts_mapping_tool_entries(tmp_path):
    artifact_path = await run_phase_01_module_main(
        task="Automate desktop workflow",
        tools=[
            {
                "tool_name": "desktop_mcp",
                "capabilities": ["desktop_automation"],
                "reliability": 0.95,
            }
        ],  # type: ignore[list-item]
        artifact_root=tmp_path / "app" / "module_main" / "artifacts",
    )

    payload = json.loads(artifact_path.read_text(encoding="utf-8"))
    assert payload["step_results"][0]["track"] == "mcp_tool"
    assert payload["step_results"][0]["executor"] == "desktop_mcp"


@pytest.mark.asyncio
async def test_run_phase_01_module_main_keeps_artifact_when_rollback_disabled(tmp_path, monkeypatch):
    from app.module_main import pipeline

    async def _force_validation_failure(*args, **kwargs):
        raise ValueError("forced validation failure")

    monkeypatch.setattr(pipeline, "validate_phase_result_artifact", _force_validation_failure)

    artifact_root = tmp_path / "app" / "module_main" / "artifacts"
    with pytest.raises(ValueError, match="forced validation failure"):
        await run_phase_01_module_main(
            task="Automate desktop workflow",
            artifact_root=artifact_root,
            phase_id="phase_01",
            rollback_on_failure=False,
        )

    assert (artifact_root / "phase_01_result.json").exists() is True


@pytest.mark.asyncio
async def test_run_phase_01_module_main_preserves_existing_artifact_on_failure(tmp_path, monkeypatch):
    from app.module_main import pipeline

    async def _force_validation_failure(*args, **kwargs):
        raise ValueError("forced validation failure")

    monkeypatch.setattr(pipeline, "validate_phase_result_artifact", _force_validation_failure)

    artifact_root = tmp_path / "app" / "module_main" / "artifacts"
    artifact_root.mkdir(parents=True, exist_ok=True)
    preexisting_artifact = artifact_root / "phase_01_result.json"
    preexisting_artifact.write_text('{"preexisting": true}', encoding="utf-8")

    with pytest.raises(ValueError, match="forced validation failure"):
        await run_phase_01_module_main(
            task="Automate desktop workflow",
            artifact_root=artifact_root,
            phase_id="phase_01",
            rollback_on_failure=True,
        )

    assert preexisting_artifact.exists() is True
    assert preexisting_artifact.read_text(encoding="utf-8") == '{"preexisting": true}'


@pytest.mark.asyncio
async def test_run_phase_01_module_main_rejects_boolean_artifact_root():
    with pytest.raises(TypeError, match="path-like"):
        await run_phase_01_module_main(
            task="Automate desktop workflow",
            artifact_root=True,  # type: ignore[arg-type]
        )


@pytest.mark.asyncio
async def test_run_phase_01_module_main_rejects_non_pathlike_artifact_root():
    with pytest.raises(TypeError, match="path-like"):
        await run_phase_01_module_main(
            task="Automate desktop workflow",
            artifact_root=123,  # type: ignore[arg-type]
        )
