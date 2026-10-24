from __future__ import annotations

from types import SimpleNamespace

from quentin.memory.processors.expected_state_template_builder import build_expected_state_templates


def test_expected_state_template_is_conservative_and_stable() -> None:
    records = [
        SimpleNamespace(metadata={"situation_id": "s1", "executed_skill_ids": ["a"], "exec_success": True}),
        SimpleNamespace(metadata={"situation_id": "s1", "executed_skill_ids": ["b"], "exec_success": False}),
        SimpleNamespace(metadata={"situation_id": "s2", "executed_skill_ids": [], "exec_success": True}),
    ]
    templates = build_expected_state_templates(records=records, max_markers=4)
    by_id = {t.situation_id: t for t in templates}
    assert by_id["s1"].stats["observations"] == 2
    assert "exec_success:true" in by_id["s1"].expected_markers
    assert by_id["s1"].fallback_paths


def test_expected_state_template_applies_min_observation_and_success_rate_filters() -> None:
    records = [
        SimpleNamespace(metadata={"situation_id": "s1", "executed_skill_ids": ["a"], "exec_success": True}),
        SimpleNamespace(metadata={"situation_id": "s1", "executed_skill_ids": ["a"], "exec_success": False}),
        SimpleNamespace(metadata={"situation_id": "s2", "executed_skill_ids": ["b"], "exec_success": False}),
    ]
    templates = build_expected_state_templates(
        records=records,
        max_markers=4,
        min_observations=2,
        min_success_rate=0.5,
    )
    ids = {t.situation_id for t in templates}
    assert "s1" in ids
    assert "s2" not in ids
