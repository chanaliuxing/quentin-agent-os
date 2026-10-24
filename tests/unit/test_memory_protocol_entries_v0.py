from __future__ import annotations

from quentin.memory.expected_state_template import ExpectedStateTemplateEntry
from quentin.memory.situation_profile import SituationProfileEntry
from quentin.memory.kinds import KIND_EXPECTED_STATE_TEMPLATE, KIND_SITUATION_PROFILE
from quentin.memory.models import MemoryTier


def test_situation_profile_entry_to_record() -> None:
    entry = SituationProfileEntry(
        situation_id="s1",
        signals=["url:example"],
        recommended_skills=["skill_a"],
        stats={"observations": 3},
    )
    rec = entry.to_memory_record(tier=MemoryTier.MTS)
    assert rec.kind == KIND_SITUATION_PROFILE
    assert rec.metadata.get("situation_id") == "s1"
    assert "recommended_skills" in rec.metadata


def test_expected_state_template_entry_to_record() -> None:
    entry = ExpectedStateTemplateEntry(
        situation_id="s1",
        expected_markers=["exec_success:true"],
        fallback_paths=["skill_a"],
        stats={"observations": 2},
    )
    rec = entry.to_memory_record(tier=MemoryTier.MTS)
    assert rec.kind == KIND_EXPECTED_STATE_TEMPLATE
    assert rec.metadata.get("situation_id") == "s1"
    assert "expected_markers" in rec.metadata

