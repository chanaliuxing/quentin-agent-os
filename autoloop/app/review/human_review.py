from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from app.config import settings
from .repair_templates import resolve_repair_template


def list_human_reviews(hooks_dir: Path | None = None) -> list[dict[str, Any]]:
    root = hooks_dir or settings.hooks_dir
    if not root.exists():
        return []

    records: list[dict[str, Any]] = []
    for path in sorted(root.glob("*_human_review_required.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            payload = {"status": "invalid_payload"}
        payload["hook_file"] = str(path)
        records.append(payload)
    return records


def latest_human_review(hooks_dir: Path | None = None) -> dict[str, Any] | None:
    reviews = list_human_reviews(hooks_dir)
    return reviews[0] if reviews else None


def latest_review_resolution(hooks_dir: Path | None = None) -> dict[str, Any] | None:
    root = hooks_dir or settings.hooks_dir
    if not root.exists():
        return None
    candidates = sorted(
        root.glob("*_human_review_resolution.json"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    if not candidates:
        return None
    path = candidates[0]
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    payload["resolution_file"] = str(path)
    return payload


def build_review_task_patch(
    *,
    phase_id: str,
    module_name: str,
    hooks_dir: Path | None = None,
) -> dict[str, Any] | None:
    resolution = latest_review_resolution(hooks_dir=hooks_dir)
    if not resolution:
        return None
    if str(resolution.get("phase_id", "")).strip() != phase_id:
        return None
    if str(resolution.get("decision", "")).strip().lower() != "approved":
        return None
    notes = str(resolution.get("notes", "")).strip()
    reviewer = str(resolution.get("reviewer", "human_reviewer")).strip() or "human_reviewer"
    repair_template = str(resolution.get("repair_template", "")).strip()
    patch_text = notes if notes else "No additional notes."
    if repair_template:
        patch_text = f"{patch_text}\n\nRepair template:\n{repair_template}"
    constraints = {
        "failure_signature": str(resolution.get("failure_signature", "")),
        "first_failure_stage": str(resolution.get("first_failure_stage", "")),
        "repair_template": repair_template,
        "required_actions": [
            "Preserve output contract validity",
            "Bind changes to allowed paths and required tests",
            "Address repair_template before declaring success",
        ],
    }
    return {
        "patch_id": f"human_review_patch_{phase_id}_{module_name}",
        "phase_id": phase_id,
        "module_name": module_name,
        "source": str(resolution.get("resolution_file", "")),
        "reviewer": reviewer,
        "notes": patch_text,
        "repair_template": repair_template,
        "constraints": constraints,
    }


def resolve_human_review(
    *,
    phase_id: str,
    decision: str,
    reviewer: str,
    notes: str = "",
    policy_version: str = "manual_review_v1",
    hooks_dir: Path | None = None,
) -> dict[str, Any]:
    root = hooks_dir or settings.hooks_dir
    required_hook = root / f"{phase_id}_human_review_required.json"
    if not required_hook.exists():
        raise FileNotFoundError(f"human review hook not found: {required_hook}")
    hook_payload = json.loads(required_hook.read_text(encoding="utf-8"))
    evidence_payload = _load_json_file(str(hook_payload.get("evidence_file", "")))
    failure_signature = str(evidence_payload.get("failure_signature", "")).strip()
    first_failure_stage = str(evidence_payload.get("first_failure_stage", "")).strip()
    repair_template = resolve_repair_template(
        failure_signature=failure_signature,
        first_failure_stage=first_failure_stage,
    )
    normalized_decision = decision.strip().lower()
    if normalized_decision not in {"approved", "rejected"}:
        raise ValueError("decision must be approved or rejected")

    resolution_payload = {
        "project_id": hook_payload.get("project_id", ""),
        "phase_id": phase_id,
        "prd_path": hook_payload.get("prd_path", ""),
        "decision": normalized_decision,
        "reviewer": reviewer,
        "policy_version": policy_version,
        "notes": notes,
        "evidence_file": hook_payload.get("evidence_file", ""),
        "failure_signature": failure_signature,
        "first_failure_stage": first_failure_stage,
        "repair_template": repair_template,
        "required_hook": str(required_hook),
        "trace_id": str(hook_payload.get("trace_id", "")).strip(),
        "timestamp": datetime.now().isoformat(),
    }
    resolution_file = root / f"{phase_id}_human_review_resolution.json"
    resolution_file.write_text(
        json.dumps(resolution_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    archive_dir = root / "archive"
    archive_dir.mkdir(parents=True, exist_ok=True)
    archived_required_hook = archive_dir / f"{phase_id}_human_review_required_{datetime.now().strftime('%Y%m%d%H%M%S')}.json"
    required_hook.rename(archived_required_hook)
    resolution_payload["resolution_file"] = str(resolution_file)
    resolution_payload["archived_required_hook"] = str(archived_required_hook)
    return resolution_payload


def _load_json_file(path_text: str) -> dict[str, Any]:
    if not path_text:
        return {}
    path = Path(path_text)
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
