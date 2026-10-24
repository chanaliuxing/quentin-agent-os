import pytest

from quentin.infra.logging import Tracer
from quentin.infra.storage.kv_store import KVStore
from quentin.l3.research.eval_harness import EvalCase
from quentin.l3.research.experiment_orchestrator import ExperimentOrchestrator
from quentin.l3.research.experiment_schemas import (
    ExperimentConfig,
    ExperimentStatus,
    ExperimentVariant,
)


@pytest.mark.asyncio
async def test_experiment_orchestrator_run_flow():
    kv = KVStore()
    tracer = Tracer()
    orchestrator = ExperimentOrchestrator(tracer=tracer, kv=kv)

    config = ExperimentConfig(target_module="router", metrics=["success"])
    variants = [ExperimentVariant(variant_id="v1", name="A", params={}, target_type="router")]
    exp = await orchestrator.create_experiment(name="demo", description="desc", config=config, variants=variants)

    cases = [
        EvalCase(
            case_id="c1",
            description="check keyword",
            input_payload={"output": "great job"},
            expected_keywords=["great"],
        )
    ]

    run = await orchestrator.run_experiment(exp.experiment_id, cases=cases)
    assert run.status == ExperimentStatus.completed

    stored_run = await orchestrator.get_run(run.run_id)
    assert stored_run is not None
    assert stored_run.variant_results["v1"]["success_rate"] == 1.0

    runs = await orchestrator.list_runs(exp.experiment_id)
    assert runs and runs[-1].run_id == run.run_id
