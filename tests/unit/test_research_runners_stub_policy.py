from __future__ import annotations

import pytest

from quentin.eval.spec import EvalTaskSpec
from quentin.l3.research.experiments import VariantConfig
from quentin.l3.research.runners.patch_eval_runner import PatchEvalRunner
from quentin.l3.research.runners.skill_evolution_runner import SkillEvolutionRunner


@pytest.fixture(autouse=True)
def _clear_stub_runner_env(monkeypatch):
    monkeypatch.delenv("ALLOW_STUB_RESEARCH_RUNNERS", raising=False)


def test_patch_eval_runner_disabled_by_default() -> None:
    runner = PatchEvalRunner()
    task = EvalTaskSpec(task_id="t1", description="d", component="patch_eval")
    variant = VariantConfig(
        variant_id="v1",
        name="v1",
        description="v1",
        target_component="patch_eval",
        params={},
    )
    with pytest.raises(RuntimeError) as excinfo:
        runner.patch_eval_fn(task, variant, {})
    assert "ALLOW_STUB_RESEARCH_RUNNERS" in str(excinfo.value)


def test_skill_evolution_runner_disabled_by_default() -> None:
    runner = SkillEvolutionRunner()
    variant = VariantConfig(
        variant_id="v1",
        name="v1",
        description="v1",
        target_component="skill_evolution",
        params={},
    )
    with pytest.raises(RuntimeError) as excinfo:
        runner.skill_evolution_fn(None, variant, {})
    assert "ALLOW_STUB_RESEARCH_RUNNERS" in str(excinfo.value)

