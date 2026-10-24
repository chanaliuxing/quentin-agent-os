from __future__ import annotations

from quentin.cognitive.phase_payloads import build_phase_payload
from quentin.cognitive.prompt_factory import RuntimeInfo, build_system_prompt


def test_build_phase_payload_normalizes_and_sets_template() -> None:
    payload = build_phase_payload(phase="PLANNING", correction_intensity="HIGH", reason="x").to_dict()
    assert payload["phase"] == "planning"
    assert payload["template_id"] == "planning_initial_v1"
    assert payload["attempt_stage"] == "initial"
    assert payload["correction_intensity"] == "high"


def test_build_phase_payload_uses_stage_specific_template() -> None:
    payload = build_phase_payload(
        phase="planning",
        attempt_stage="stuck",
        correction_intensity="critical",
        reason="loop_detected",
        directives=["d1"],
    ).to_dict()
    assert payload["template_id"] == "planning_stuck_v1"
    assert payload["attempt_stage"] == "stuck"
    assert payload["directives"] == ["d1"]


def test_build_system_prompt_includes_phase_template_and_payload() -> None:
    phase_payload = build_phase_payload(phase="reflecting", correction_intensity="critical", reason="retry").to_dict()
    out = build_system_prompt(
        mode="full",
        runtime_info=RuntimeInfo(agent_id="a", workspace=".", os_name="linux", model="m"),
        phase_payload=phase_payload,
    )
    assert "Reflecting State Template" in out
    assert "Phase Payload:" in out
