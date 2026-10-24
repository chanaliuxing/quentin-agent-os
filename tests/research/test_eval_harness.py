from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List
import pytest
import asyncio

from quentin.kernel.schemas import ExperimentVariant
from quentin.l3.research.eval_harness import EvalCase, EvalHarness, EvalSuiteResult
from quentin.infra.logging import Tracer
from quentin.infra.storage.kv_store import KVStore


class MockKVStore(KVStore):
    def __init__(self):
        self._data = {}

    async def save(self, key: str, value: Any) -> None:
        self._data[key] = value

    async def load(self, key: str) -> Any:
        return self._data.get(key)

    async def append_list(self, key: str, value: Any) -> None:
        if key not in self._data:
            self._data[key] = []
        self._data[key].append(value)
    
    async def load_list(self, key: str) -> List[Any]:
        return self._data.get(key, [])

    def get_all_data(self):
        return self._data

@pytest.fixture
def mock_kv_store() -> MockKVStore:
    return MockKVStore()

@pytest.fixture
def mock_tracer() -> Tracer:
    # A minimal mock tracer that does nothing.
    class MockTracer(Tracer):
        def span(self, *args, **kwargs):
            pass
        def event(self, *args, **kwargs):
            pass
    return MockTracer()

@pytest.fixture
def temp_results_path(tmp_path: Path) -> Path:
    return tmp_path / "eval_results.jsonl"

@pytest.fixture
def eval_harness(mock_kv_store: MockKVStore, mock_tracer: Tracer, temp_results_path: Path) -> EvalHarness:
    return EvalHarness(kv=mock_kv_store, tracer=mock_tracer, results_path=temp_results_path)


@pytest.mark.asyncio
async def test_run_suite_with_default_evaluator(
    eval_harness: EvalHarness,
    mock_kv_store: MockKVStore,
    temp_results_path: Path,
):
    """
    Tests the full flow of run_suite using the default keyword-matching evaluator.
    Verifies aggregation and persistence to both KVStore and JSONL.
    """
    # 1. Define test data
    experiment_id = "test_exp_01"
    variant = ExperimentVariant(variant_id="variant_A", name="Variant A", target_type="default")
    cases = [
        EvalCase(
            case_id="case_01",
            description="Test successful keyword match",
            input_payload={"output": "The quick brown fox jumps over the lazy dog."},
            expected_keywords=["fox", "dog"],
            pass_threshold=0.8,
        ),
        EvalCase(
            case_id="case_02",
            description="Test failed keyword match",
            input_payload={"output": "A sleepy cat naps on the mat."},
            expected_keywords=["fox", "dog"],
            pass_threshold=0.8,
        ),
        EvalCase(
            case_id="case_03",
            description="Test partial match (success)",
            input_payload={"output": "Only the fox is here."},
            expected_keywords=["fox", "dog"],
            pass_threshold=0.5,
        ),
    ]

    # 2. Run the suite
    suite_result = await eval_harness.run_suite(
        experiment_id=experiment_id,
        variant=variant,
        cases=cases,
    )

    # 3. Assertions on the returned EvalSuiteResult object
    assert isinstance(suite_result, EvalSuiteResult)
    assert suite_result.experiment_id == experiment_id
    assert suite_result.variant_id == variant.variant_id
    assert len(suite_result.case_results) == 3

    # Check individual case results
    assert suite_result.case_results[0].status == "success"
    assert suite_result.case_results[0].success == 1.0
    assert suite_result.case_results[1].status == "error"
    assert suite_result.case_results[1].success == 0.0
    assert suite_result.case_results[2].status == "success"
    assert suite_result.case_results[2].success == 0.5
    
    # Check aggregated metrics
    assert suite_result.metrics["num_cases"] == 3
    assert pytest.approx(suite_result.metrics["success_rate"]) == (1.0 + 0.0 + 0.5) / 3

    # 4. Assertions on persistence (JSONL file)
    assert temp_results_path.exists()
    with temp_results_path.open("r") as f:
        data = json.load(f)
        assert data["run_id"] == suite_result.run_id
        assert data["experiment_id"] == experiment_id
        assert len(data["case_results"]) == 3
        assert data["metrics"]["num_cases"] == 3

    # 5. Assertions on persistence (KVStore)
    kv_data = mock_kv_store.get_all_data()
    assert f"eval:run:{suite_result.run_id}" in kv_data
    assert "eval:index:runs" in kv_data
    assert kv_data["eval:index:runs"][0] == suite_result.run_id
    assert kv_data[f"eval:run:{suite_result.run_id}"]["metrics"]["num_cases"] == 3

