from __future__ import annotations

from meta_agent.skills.executor import SkillExecutor
from meta_agent.skills.schema import SkillDefinition, SkillImplType, SkillStatus


class _FakeSkillManager:
    def __init__(self, skill: SkillDefinition) -> None:
        self._skill = skill
        self.recorded: list[bool] = []

    def get(self, skill_id: str):  # type: ignore[no-untyped-def]
        if skill_id == self._skill.skill_id:
            return self._skill
        return None

    def record_usage(self, skill_id: str, success: bool) -> None:
        _ = skill_id
        self.recorded.append(bool(success))


def test_skill_executor_records_failure_on_error_outcome() -> None:
    skill = SkillDefinition.new(
        name="x",
        domain="core",
        tags=[],
        description="x",
        signature={},
        impl_type=SkillImplType.WORKFLOW_REF,
        impl_payload={},
        status=SkillStatus.ACTIVE,
    )
    mgr = _FakeSkillManager(skill)
    executor = SkillExecutor(skill_manager=mgr)

    out = executor.execute(skill.skill_id, {}, {})
    assert out["status"] == "error"
    assert mgr.recorded == [False]


def test_skill_executor_records_success_on_ok_outcome() -> None:
    skill = SkillDefinition.new(
        name="x",
        domain="core",
        tags=[],
        description="x",
        signature={},
        impl_type=SkillImplType.LLM_PROMPT,
        impl_payload={"prompt": "hi"},
        status=SkillStatus.ACTIVE,
    )
    mgr = _FakeSkillManager(skill)
    executor = SkillExecutor(skill_manager=mgr)

    # Bypass real LLM path by patching method directly.
    executor._execute_llm_prompt = lambda s, i, t: {"status": "ok", "output": "ok"}  # type: ignore[assignment]
    out = executor.execute(skill.skill_id, {}, {})
    assert out["status"] == "ok"
    assert mgr.recorded == [True]

