from __future__ import annotations

import asyncio
import json
import re
from datetime import datetime, UTC
from os import PathLike
from pathlib import Path
from typing import Any, Mapping

from .core import ModuleMainResult

_PHASE_ID_PATTERN = re.compile(r"^[a-zA-Z0-9_-]+$")
ArtifactRoot = str | PathLike[str] | Path


def normalize_phase_id(phase_id: str) -> str:
    if isinstance(phase_id, bool) or not isinstance(phase_id, str):
        raise TypeError("phase_id must be a string")
    normalized = phase_id.strip()
    if not normalized:
        raise ValueError("phase_id must not be empty")
    if not _PHASE_ID_PATTERN.fullmatch(normalized):
        raise ValueError("phase_id contains invalid characters")
    return normalized


def build_phase_result_payload(
    *,
    phase_id: str,
    module_result: ModuleMainResult,
) -> dict[str, Any]:
    normalized_phase_id = normalize_phase_id(phase_id)
    successful_steps = sum(1 for item in module_result.step_results if item.success)
    failed_steps = len(module_result.step_results) - successful_steps
    return {
        "contract_version": "1.0",
        "generated_at": datetime.now(UTC).isoformat(),
        "phase_id": normalized_phase_id,
        "module_name": "module_main",
        "task": module_result.task,
        "summary": {
            "total_steps": len(module_result.steps),
            "successful_steps": successful_steps,
            "failed_steps": failed_steps,
            "next_investment_area": module_result.next_investment_area,
        },
        "memory_updates": list(module_result.memory_updates),
        "reflection": module_result.reflection,
        "steps": [step.model_dump(mode="json") for step in module_result.steps],
        "step_results": [result.model_dump(mode="json") for result in module_result.step_results],
    }


async def write_phase_result_artifact(
    *,
    phase_id: str,
    module_result: ModuleMainResult,
    artifact_root: ArtifactRoot | None = None,
) -> Path:
    if artifact_root is None:
        root = Path(__file__).resolve().parent / "artifacts"
    elif isinstance(artifact_root, bool):
        raise TypeError("artifact_root must be a path-like value")
    else:
        root = Path(artifact_root)
    normalized_phase_id = normalize_phase_id(phase_id)
    target_path = root / f"{normalized_phase_id}_result.json"
    payload = build_phase_result_payload(phase_id=normalized_phase_id, module_result=module_result)
    await asyncio.to_thread(target_path.parent.mkdir, parents=True, exist_ok=True)
    await asyncio.to_thread(
        target_path.write_text,
        json.dumps(payload, ensure_ascii=False, indent=2),
        "utf-8",
    )
    return target_path


def validate_phase_result_payload(
    payload: Mapping[str, Any],
    *,
    required_phase_id: str,
    required_module_name: str = "module_main",
) -> None:
    required_top_level_fields = {
        "contract_version",
        "generated_at",
        "phase_id",
        "module_name",
        "task",
        "summary",
        "memory_updates",
        "reflection",
        "steps",
        "step_results",
    }
    missing_fields = [name for name in sorted(required_top_level_fields) if name not in payload]
    if missing_fields:
        missing = ", ".join(missing_fields)
        raise ValueError(f"phase result payload missing fields: {missing}")

    contract_version = str(payload["contract_version"]).strip()
    if contract_version != "1.0":
        raise ValueError(f"contract_version mismatch: expected 1.0, got {contract_version}")

    expected_phase_id = normalize_phase_id(required_phase_id)
    phase_id = normalize_phase_id(str(payload["phase_id"]))
    if phase_id != expected_phase_id:
        raise ValueError(f"phase_id mismatch: expected {expected_phase_id}, got {phase_id}")

    module_name = str(payload["module_name"])
    if module_name != required_module_name:
        raise ValueError(f"module_name mismatch: expected {required_module_name}, got {module_name}")

    generated_at_raw = str(payload["generated_at"]).strip()
    if not generated_at_raw:
        raise ValueError("generated_at must not be empty")
    try:
        datetime.fromisoformat(generated_at_raw.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError("generated_at must be an ISO-8601 datetime") from error

    task = str(payload["task"]).strip()
    if not task:
        raise ValueError("task must not be empty")

    memory_updates = payload["memory_updates"]
    if not isinstance(memory_updates, list):
        raise ValueError("memory_updates must be an array")
    if any(not isinstance(item, str) for item in memory_updates):
        raise ValueError("memory_updates entries must be strings")
    if any(not item.strip() for item in memory_updates):
        raise ValueError("memory_updates entries must be non-empty strings")

    reflection = str(payload["reflection"]).strip()
    if not reflection:
        raise ValueError("reflection must not be empty")

    summary = payload["summary"]
    if not isinstance(summary, Mapping):
        raise ValueError("summary must be an object")

    required_summary_fields = {"total_steps", "successful_steps", "failed_steps", "next_investment_area"}
    missing_summary_fields = [name for name in sorted(required_summary_fields) if name not in summary]
    if missing_summary_fields:
        missing = ", ".join(missing_summary_fields)
        raise ValueError(f"summary missing fields: {missing}")

    total_steps_value = summary["total_steps"]
    successful_steps_value = summary["successful_steps"]
    failed_steps_value = summary["failed_steps"]
    if any(
        isinstance(item, bool) or not isinstance(item, int)
        for item in (total_steps_value, successful_steps_value, failed_steps_value)
    ):
        raise ValueError("summary step counts must be integers")

    total_steps = total_steps_value
    successful_steps = successful_steps_value
    failed_steps = failed_steps_value
    if total_steps < 0 or successful_steps < 0 or failed_steps < 0:
        raise ValueError("summary step counts must be non-negative")
    if total_steps != successful_steps + failed_steps:
        raise ValueError("summary step counts are inconsistent")
    next_investment_area = str(summary["next_investment_area"]).strip()
    if not next_investment_area:
        raise ValueError("summary next_investment_area must not be empty")

    steps = payload["steps"]
    step_results = payload["step_results"]
    if not isinstance(steps, list) or not isinstance(step_results, list):
        raise ValueError("steps and step_results must be arrays")
    if len(steps) != total_steps or len(step_results) != total_steps:
        raise ValueError("summary total_steps does not match payload arrays")
    if len(memory_updates) != total_steps:
        raise ValueError("memory_updates length does not match summary total_steps")
    if any(not isinstance(item, Mapping) for item in steps):
        raise ValueError("steps entries must be objects")
    if any(not isinstance(item, Mapping) for item in step_results):
        raise ValueError("step_results entries must be objects")

    for item in steps:
        description = item.get("description")
        required_capability = item.get("required_capability")
        if not isinstance(description, str) or not description.strip():
            raise ValueError("steps entries must include non-empty description values")
        if not isinstance(required_capability, str) or not required_capability.strip():
            raise ValueError("steps entries must include non-empty required_capability values")

    step_ids = [str(item.get("step_id", "")).strip() for item in steps]
    if any(not step_id for step_id in step_ids):
        raise ValueError("steps entries must include non-empty step_id values")
    if len(set(step_ids)) != len(step_ids):
        raise ValueError("steps entries must use unique step_id values")

    result_step_ids = [str(item.get("step_id", "")).strip() for item in step_results]
    if any(not step_id for step_id in result_step_ids):
        raise ValueError("step_results entries must include non-empty step_id values")
    if result_step_ids != step_ids:
        raise ValueError("step_results must align with steps by step_id")

    for item in step_results:
        track = item.get("track")
        executor = item.get("executor")
        output = item.get("output")
        success = item.get("success")
        if track not in {"mcp_tool", "self_programming"}:
            raise ValueError("step_results entries must include a valid track value")
        if not isinstance(executor, str) or not executor.strip():
            raise ValueError("step_results entries must include non-empty executor values")
        if not isinstance(output, str):
            raise ValueError("step_results entries must include string output values")
        if not isinstance(success, bool):
            raise ValueError("step_results entries must include boolean success values")

    expected_memory_updates = [
        f"{step_id}:{item['track']}:{'ok' if item['success'] else 'fail'}"
        for step_id, item in zip(step_ids, step_results, strict=True)
    ]
    if memory_updates != expected_memory_updates:
        raise ValueError("memory_updates must align with step_results")

    actual_successful_steps = sum(1 for item in step_results if item.get("success") is True)
    actual_failed_steps = len(step_results) - actual_successful_steps
    if successful_steps != actual_successful_steps or failed_steps != actual_failed_steps:
        raise ValueError("summary step counts do not match step_results")


async def validate_phase_result_artifact(
    artifact_path: Path,
    *,
    required_phase_id: str,
    required_module_name: str = "module_main",
) -> dict[str, Any]:
    if not artifact_path.exists():
        raise ValueError(f"phase result artifact not found: {artifact_path}")
    raw = await asyncio.to_thread(artifact_path.read_text, "utf-8")
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as error:
        raise ValueError("phase result artifact contains invalid JSON") from error
    if not isinstance(payload, dict):
        raise ValueError("phase result artifact payload must be an object")
    validate_phase_result_payload(
        payload=payload,
        required_phase_id=required_phase_id,
        required_module_name=required_module_name,
    )
    return payload
