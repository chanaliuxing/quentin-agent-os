from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.config import settings


@dataclass
class HarnessRunDossier:
    workflow_id: str
    phase_id: str
    terminal_state: str
    primary_failure_type: str
    secondary_failure_types: list[str]
    recovery_action: str
    evidence_summary_file: str
    evidence_record_file: str
    event_log_file: str
    missing_required_tests: list[str]
    failed_required_tests: list[str]
    required_test_failure_details: dict[str, list[str]]
    monitor_snapshot: dict[str, Any]
    promotion_snapshot: dict[str, Any]
    canary_snapshot: dict[str, Any]
    execution_ticket_file: str
    execution_ticket_type: str
    execution_ticket_owner: str
    execution_ticket_action: str
    execution_ticket_stage: str

    def to_markdown(self) -> str:
        execution_remediation_snapshot = dict(
            self.monitor_snapshot.get("execution_remediation_snapshot", {}) or {}
        )
        lines = [
            f"# Run Dossier `{self.workflow_id}/{self.phase_id}`",
            "",
            "## Terminal",
            f"- terminal_state: `{self.terminal_state}`",
            f"- primary_failure_type: `{self.primary_failure_type}`",
            f"- secondary_failure_types: `{', '.join(self.secondary_failure_types) if self.secondary_failure_types else '[]'}`",
            f"- recovery_action: `{self.recovery_action}`",
            "",
            "## Artifacts",
            f"- execution_summary: `{self.evidence_summary_file}`",
            f"- evidence_record: `{self.evidence_record_file}`",
            f"- event_log: `{self.event_log_file}`",
            "",
            "## Required Test Diagnostics",
            f"- missing_required_tests: `{', '.join(self.missing_required_tests) if self.missing_required_tests else '[]'}`",
            f"- failed_required_tests: `{', '.join(self.failed_required_tests) if self.failed_required_tests else '[]'}`",
            f"- required_test_failure_details: `{self.required_test_failure_details if self.required_test_failure_details else {}}`",
            "",
            "## Monitor Snapshot",
            f"- matched_count: `{self.monitor_snapshot.get('matched_count', 0)}`",
            f"- matched_ratio: `{self.monitor_snapshot.get('matched_ratio', 0.0)}`",
            f"- triggered: `{self.monitor_snapshot.get('triggered', False)}`",
            f"- execution_remediation_triggered: `{execution_remediation_snapshot.get('triggered', False)}`",
            f"- execution_remediation_top_stage: `{execution_remediation_snapshot.get('top_stage', '')}`",
            f"- execution_remediation_target_failure_type: `{execution_remediation_snapshot.get('target_failure_type', '')}`",
            "",
            "## Promotion Snapshot",
            f"- promotion_candidates: `{len(self.promotion_snapshot.get('promotion_candidates', []))}`",
            "",
            "## Canary Snapshot",
            f"- policy_mode: `{self.canary_snapshot.get('policy_mode', '')}`",
            f"- terminal_state_expected_match_rate: `{self.canary_snapshot.get('terminal_state_expected_match_rate', 0.0)}`",
            "",
            "## Execution Ticket",
            f"- execution_ticket_file: `{self.execution_ticket_file}`",
            f"- type: `{self.execution_ticket_type}`",
            f"- owner: `{self.execution_ticket_owner}`",
            f"- action: `{self.execution_ticket_action}`",
            f"- top_stage: `{self.execution_ticket_stage}`",
        ]
        return "\n".join(lines) + "\n"


class AgentHarness:
    def __init__(self, runtime_dir: Path | None = None) -> None:
        self.runtime_dir = runtime_dir or settings.runtime_dir

    def build_dossier(self, *, workflow_id: str, phase_id: str = "phase_01") -> HarnessRunDossier:
        summary_path = self.runtime_dir / "evidence" / workflow_id / phase_id / "execution_summary.json"
        summary = _read_json(summary_path)
        evidence_path, evidence = _latest_evidence_record(self.runtime_dir, workflow_id, phase_id)
        event_path = self.runtime_dir / "event_log" / workflow_id / phase_id / "events.jsonl"
        monitor_report = _read_json(self.runtime_dir / "metrics" / "business_failure_monitor_report.json")
        promotion_report = _read_json(self.runtime_dir / "metrics" / "business_failure_promotion_report.json")
        canary_report = _read_json(self.runtime_dir / "metrics" / "recovery_canary_report.json")
        ticket_path, ticket_payload = _latest_execution_ticket(self.runtime_dir, workflow_id=workflow_id)
        return HarnessRunDossier(
            workflow_id=workflow_id,
            phase_id=phase_id,
            terminal_state=str(summary.get("terminal_state", "")),
            primary_failure_type=str(summary.get("primary_failure_type", "")),
            secondary_failure_types=[str(item) for item in summary.get("secondary_failure_types", []) if str(item).strip()],
            recovery_action=str(summary.get("recovery_action", "")),
            evidence_summary_file=str(summary_path),
            evidence_record_file=str(evidence_path) if evidence_path else "",
            event_log_file=str(event_path),
            missing_required_tests=[
                str(item) for item in evidence.get("missing_required_tests", []) if str(item).strip()
            ],
            failed_required_tests=[
                str(item) for item in evidence.get("failed_required_tests", []) if str(item).strip()
            ],
            required_test_failure_details={
                str(key): [str(item) for item in value if str(item).strip()]
                for key, value in evidence.get("required_test_failure_details", {}).items()
                if isinstance(value, list)
            },
            monitor_snapshot=monitor_report,
            promotion_snapshot=promotion_report,
            canary_snapshot=canary_report,
            execution_ticket_file=str(ticket_path) if ticket_path else "",
            execution_ticket_type=str(ticket_payload.get("type", "")),
            execution_ticket_owner=str(ticket_payload.get("owner", "")),
            execution_ticket_action=str(ticket_payload.get("recommended_action", "")),
            execution_ticket_stage=str(ticket_payload.get("top_stage", "")),
        )


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _latest_evidence_record(runtime_dir: Path, workflow_id: str, phase_id: str) -> tuple[Path | None, dict[str, Any]]:
    record_dir = runtime_dir / "evidence" / workflow_id / phase_id
    if not record_dir.exists():
        return None, {}
    candidates = sorted(
        [path for path in record_dir.glob("evidence_*.json") if path.is_file()],
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    if not candidates:
        return None, {}
    latest = candidates[0]
    return latest, _read_json(latest)


def _latest_execution_ticket(runtime_dir: Path, *, workflow_id: str) -> tuple[Path | None, dict[str, Any]]:
    hooks_dir = runtime_dir / "hooks"
    if not hooks_dir.exists():
        return None, {}
    candidates = sorted(
        [path for path in hooks_dir.glob("execution_ticket_*.json") if path.is_file()],
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    for candidate in candidates:
        payload = _read_json(candidate)
        if str(payload.get("workflow_id", "")).strip() == str(workflow_id).strip():
            return candidate, payload
    if candidates:
        latest = candidates[0]
        return latest, _read_json(latest)
    return None, {}
