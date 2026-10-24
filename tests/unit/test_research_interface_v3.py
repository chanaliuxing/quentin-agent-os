from quentin.infra.logging import Tracer
from quentin.infra.storage.kv_store import KVStore, KVStoreConfig
from quentin.l3.research.eval_harness import EvalHarness
from quentin.l3.research.experiment_orchestrator import ExperimentOrchestrator
from quentin.l3.research.interface import ResearchInterface


def test_research_interface_v3_create_run_export(tmp_path) -> None:
    kv = KVStore(config=KVStoreConfig(db_path=str(tmp_path / "kv.sqlite3")))
    tracer = Tracer(store=kv)
    harness = EvalHarness(kv=kv, tracer=tracer)
    orch = ExperimentOrchestrator(tracer=tracer, kv=kv, eval_harness=harness)

    ri = ResearchInterface(orchestrator=orch)
    rec = ri.create_experiment(
        {
            "name": "planner_ab",
            "description": "test",
            "target_type": "planner",
            "metrics": ["success_rate"],
            "variants": [
                {"variant_id": "baseline", "name": "baseline", "params": {"strategy": "baseline"}},
                {"variant_id": "candidate", "name": "candidate", "params": {"strategy": "hierarchical"}},
            ],
        }
    )
    exp_id = rec["experiment_id"]

    run = ri.run_experiment(
        exp_id,
        cases=[
            {
                "case_id": "c1",
                "description": "do thing",
                "input_payload": {"domain": "core"},
                "expected_keywords": ["Execute"],
                "pass_threshold": 0.0,
            }
        ],
    )
    assert run["status"] in {"completed", "failed"}

    exported = ri.export_results(exp_id)
    assert exported["experiment"] is not None

