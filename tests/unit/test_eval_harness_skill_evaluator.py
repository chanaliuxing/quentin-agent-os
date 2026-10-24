from __future__ import annotations

import asyncio
from pathlib import Path

from quentin.infra.logging import Tracer
from quentin.infra.storage.kv_store import KVStore, KVStoreConfig
from quentin.kernel.schemas import ExperimentVariant
from quentin.l3.research.eval_harness import EvalHarness, EvalCase


def test_eval_harness_skill_evaluator_runs_module(tmp_path: Path) -> None:
    mod = tmp_path / "skill_mod.py"
    mod.write_text(
        "from __future__ import annotations\n"
        "from typing import Any, Dict\n"
        "def run_skill(params: Dict[str, Any]) -> Dict[str, Any]:\n"
        "    return {'ok': True, 'x': params.get('x')}\n",
        encoding="utf-8",
    )

    harness = EvalHarness(
        kv=KVStore(KVStoreConfig(db_path=str(tmp_path / "kv.sqlite3"))),
        tracer=Tracer(),
        results_path=tmp_path / "results.jsonl",
    )

    variant = ExperimentVariant(
        variant_id="v1",
        name="skill",
        params={"module_path": str(mod), "callable": "run_skill"},
        target_type="skill",
    )
    cases = [
        EvalCase(case_id="c1", description="skill", input_payload={"x": 7}, expected_keywords=["ok"]),
    ]

    suite = asyncio.run(harness.run_suite(experiment_id="exp", variant=variant, cases=cases, target_type="skill"))
    assert suite.metrics["success_rate"] >= 1.0
