from __future__ import annotations

from types import SimpleNamespace

from quentin.memory.processors.situation_profile_builder import build_situation_profiles


def test_build_situation_profiles_from_session_delta_metadata() -> None:
    records = [
        SimpleNamespace(metadata={"situation_id": "s1", "executed_skill_ids": ["a"], "exec_success": True}),
        SimpleNamespace(metadata={"situation_id": "s1", "executed_skill_ids": ["a", "b"], "exec_success": False}),
        SimpleNamespace(metadata={"situation_id": "s1", "executed_skill_ids": ["b"], "exec_success": True}),
        SimpleNamespace(metadata={"situation_id": "s2", "executed_skill_ids": ["c"], "exec_success": False}),
    ]
    profiles = build_situation_profiles(records=records, top_k_skills=2)
    by_id = {p.situation_id: p for p in profiles}
    assert "s1" in by_id
    assert "s2" in by_id
    assert by_id["s1"].stats["observations"] == 3
    assert by_id["s1"].stats["successes"] == 2
    assert by_id["s1"].recommended_skills[0] in {"a", "b"}


def test_build_situation_profiles_applies_min_observation_and_success_rate_filters() -> None:
    records = [
        SimpleNamespace(metadata={"situation_id": "s1", "executed_skill_ids": ["a"], "exec_success": True}),
        SimpleNamespace(metadata={"situation_id": "s1", "executed_skill_ids": ["a"], "exec_success": False}),
        SimpleNamespace(metadata={"situation_id": "s2", "executed_skill_ids": ["b"], "exec_success": False}),
    ]
    profiles = build_situation_profiles(
        records=records,
        top_k_skills=2,
        min_observations=2,
        min_success_rate=0.5,
    )
    ids = {p.situation_id for p in profiles}
    assert "s1" in ids
    assert "s2" not in ids
