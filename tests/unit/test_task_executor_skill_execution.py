from meta_agent.runtime.task_executor import TaskExecutor
from meta_agent.skills.executor import SkillExecutor
from meta_agent.skills.schema import SkillDefinition, SkillImplType, SkillStatus


def test_task_executor_runs_builtin_skill() -> None:
    executor = TaskExecutor()
    task = {"id": "t1", "type": "demo", "description": "demo"}
    plan = {"steps": [{"type": "use_skill", "id": "s1", "skill_id": "builtin/echo", "inputs": {"x": 1}}]}
    out = executor.execute_plan(task, plan)
    assert out["success"] is True
    assert out["results"]["s1"]["status"] == "ok"


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


def test_skill_executor_usage_failure_not_marked_success() -> None:
    skill = SkillDefinition.new(
        name="wf",
        domain="core",
        tags=[],
        description="wf",
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


def test_skill_executor_usage_success_marked_success() -> None:
    skill = SkillDefinition.new(
        name="llm",
        domain="core",
        tags=[],
        description="llm",
        signature={},
        impl_type=SkillImplType.LLM_PROMPT,
        impl_payload={"prompt": "hi"},
        status=SkillStatus.ACTIVE,
    )
    mgr = _FakeSkillManager(skill)
    executor = SkillExecutor(skill_manager=mgr)
    executor._execute_llm_prompt = lambda s, i, t: {"status": "ok", "output": "ok"}  # type: ignore[assignment]
    out = executor.execute(skill.skill_id, {}, {})
    assert out["status"] == "ok"
    assert mgr.recorded == [True]
