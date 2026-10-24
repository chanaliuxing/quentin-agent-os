import pytest
from unittest.mock import MagicMock, AsyncMock
from datetime import datetime, UTC

from quentin.skills.skill_library import SkillLibrary
from quentin.kernel.schemas import SkillDefinition, SkillStatus # Correct import for SkillDefinition
from quentin.infra.logging import Tracer # For mocking
from quentin.infra.storage.kv_store import KVStore # For type hinting, uses MockKVStore

@pytest.fixture
def mock_tracer():
    mock = MagicMock(spec=Tracer)
    # Mock span method to do nothing
    mock.span.return_value = None
    return mock

@pytest.fixture
def skill_library(mock_kv_store, mock_tracer):
    return SkillLibrary(kv=mock_kv_store, tracer=mock_tracer)

@pytest.mark.asyncio
async def test_create_and_get_skill(skill_library, mock_kv_store):
    # Use quentin.kernel.schemas.SkillDefinition
    skill_data = {
        "skill_id": "skill_123",
        "name": "Test Skill",
        "description": "A test skill",
        "domain": "general",
        "pattern_goal": "do something",
        "steps": [],
        "created_at": datetime.now(UTC).isoformat(),
        "updated_at": datetime.now(UTC).isoformat(),
        "status": SkillStatus.draft.value # Provide a default status
    }
    skill = SkillDefinition(**skill_data) # Create SkillDefinition using dict

    await skill_library.save_skill(skill)
    
    retrieved_skill = await skill_library.get(skill.skill_id)
    assert retrieved_skill.name == skill.name
    assert retrieved_skill.skill_id == skill.skill_id
    # Assert that the list of all skills also contains this skill
    all_skills_ids = await mock_kv_store.get_list(skill_library.prefix + "all")
    assert skill.skill_id in all_skills_ids

@pytest.mark.asyncio
async def test_list_all_skills(skill_library, mock_kv_store):
    skill1_data = {
        "skill_id": "skill_id_1", "name": "Skill 1", "description": "d1", "domain": "general", "pattern_goal": "p1", "steps": [],
    "created_at": datetime.now(UTC).isoformat(), "updated_at": datetime.now(UTC).isoformat(), "status": SkillStatus.draft.value
    }
    skill2_data = {
        "skill_id": "skill_id_2", "name": "Skill 2", "description": "d2", "domain": "desktop", "pattern_goal": "p2", "steps": [],
    "created_at": datetime.now(UTC).isoformat(), "updated_at": datetime.now(UTC).isoformat(), "status": SkillStatus.draft.value
    }
    skill1 = SkillDefinition(**skill1_data)
    skill2 = SkillDefinition(**skill2_data)

    # Populate the mock_kv_store's internal data for the test
    await mock_kv_store.save(skill_library._key(skill1.skill_id), skill1.model_dump())
    await mock_kv_store.save(skill_library._key(skill2.skill_id), skill2.model_dump())
    await mock_kv_store.append_list(skill_library.prefix + "all", skill1.skill_id)
    await mock_kv_store.append_list(skill_library.prefix + "all", skill2.skill_id)

    skills = await skill_library.list_all()
    
    assert len(skills) == 2
    assert any(s.name == "Skill 1" for s in skills)
    assert any(s.name == "Skill 2" for s in skills)

@pytest.mark.asyncio
async def test_record_usage(skill_library, mock_kv_store):
    skill_id = "usage_skill"
    skill_data = {
        "skill_id": skill_id, "name": "Usage Skill", "description": "d", "domain": "general", "pattern_goal": "p", "steps": [],
        "stats": {"use_count": 5},
    "created_at": datetime.now(UTC).isoformat(), "updated_at": datetime.now(UTC).isoformat(), "status": SkillStatus.active.value
    }
    skill = SkillDefinition(**skill_data)
    
    # Populate the mock_kv_store's internal data
    await mock_kv_store.save(skill_library._key(skill.skill_id), skill.model_dump())

    await skill_library.record_usage(skill.skill_id)
    
    # Retrieve the updated skill from the mock store
    updated_skill_data = await mock_kv_store.get(skill_library._key(skill_id))
    assert updated_skill_data["stats"]["use_count"] == 6

@pytest.mark.asyncio
async def test_find_for_goal(skill_library, mock_kv_store):
    skill1_data = {
        "skill_id": "skill_id_1", "name": "Desktop Clicker", "description": "d", "domain": "desktop", "pattern_goal": "anything desktop clicker", "steps": [], "status": SkillStatus.active.value,
    "created_at": datetime.now(UTC).isoformat(), "updated_at": datetime.now(UTC).isoformat()
    }
    skill2_data = {
        "skill_id": "skill_id_2", "name": "General Logger", "description": "d", "domain": "general", "pattern_goal": "log anything event", "steps": [], "status": SkillStatus.active.value,
    "created_at": datetime.now(UTC).isoformat(), "updated_at": datetime.now(UTC).isoformat()
    }
    skill3_data = {
        "skill_id": "skill_id_3", "name": "Inactive Skill", "description": "d", "domain": "general", "pattern_goal": "do nothing", "steps": [], "status": SkillStatus.draft.value,
    "created_at": datetime.now(UTC).isoformat(), "updated_at": datetime.now(UTC).isoformat()
    }
    skill1 = SkillDefinition(**skill1_data)
    skill2 = SkillDefinition(**skill2_data)
    skill3 = SkillDefinition(**skill3_data)

    mock_kv_store._data[skill_library.prefix + "all"] = [skill1.skill_id, skill2.skill_id, skill3.skill_id]
    mock_kv_store._data[skill_library._key(skill1.skill_id)] = skill1.model_dump()
    mock_kv_store._data[skill_library._key(skill2.skill_id)] = skill2.model_dump()
    mock_kv_store._data[skill_library._key(skill3.skill_id)] = skill3.model_dump()

    # Test 1: "click a button" in "desktop" domain
    results = await skill_library.find_for_goal("click a button", domain="desktop")
    assert len(results) == 1
    assert results[0].name == "Desktop Clicker"

    # Test 2: "log events" in "general" domain
    results_general = await skill_library.find_for_goal("log events", domain="general")
    assert len(results_general) == 1
    assert results_general[0].name == "General Logger"

    # Test 3: "anything" in "general" domain, top_k=2
    results_all = await skill_library.find_for_goal("anything", domain="general", top_k=2)
    assert len(results_all) == 2 
    # Check if the correct skills are returned and sorted (Desktop Clicker, General Logger)
    assert results_all[0].name == "General Logger" # General Logger matches better for "anything"
    assert results_all[1].name == "Desktop Clicker"
