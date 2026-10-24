import asyncio
import json
from pathlib import Path

from quentin.observability.service import ObservabilityService


def _write_jsonl(path: Path, rows) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def test_observability_memory_metrics_aggregates_events(tmp_path: Path) -> None:
    events_path = tmp_path / "data" / "traces" / "events.jsonl"
    _write_jsonl(
        events_path,
        [
            {"trace_id": "t1", "event_type": "memory", "payload": {"action": "remember", "vector_status": "generated"}},
            {"trace_id": "t1", "event_type": "memory", "payload": {"action": "recall", "use_vector": True, "result_count": 2, "latency_ms": 10.0, "query_tier": "STS", "query_kind": "episodic", "query_domain": "core", "source_counts": {"session_delta:s1": 2}, "text_count": 4, "vec_count": 3, "fused_count": 5}},
            {"trace_id": "t1", "event_type": "memory", "payload": {"action": "recall", "use_vector": False, "result_count": 0, "latency_ms": 30.0, "query_tier": "STS", "query_kind": "episodic", "query_domain": "core"}},
            {"trace_id": "t1", "event_type": "memory", "payload": {"action": "recall_across_sessions", "timed_out_sessions": ["s2"]}},
            {"trace_id": "t1", "event_type": "memory", "payload": {"action": "recall_across_sessions_async", "timed_out_sessions": ["s3"], "cancelled": True}},
            {"trace_id": "t1", "event_type": "memory", "payload": {"action": "decay_records", "ids": ["a", "b", "c"]}},
            {"trace_id": "t1", "event_type": "sleep", "payload": {"action": "v3_outputs_emitted", "training_pairs": 1, "skill_candidates": 1}},
        ],
    )

    tp_path = tmp_path / "data" / "training_pairs" / "training_pairs.jsonl"
    sc_path = tmp_path / "data" / "training_pairs" / "skill_candidates.jsonl"
    _write_jsonl(tp_path, [{"schema_version": "v1"}])
    _write_jsonl(sc_path, [{"schema_version": "v1"}])

    svc = ObservabilityService(runtime=None, repo_root=tmp_path)
    overview = asyncio.run(svc.get_overview())

    mem = overview["memory"]
    assert mem["events"]["totals"]["remember"] == 1
    assert mem["events"]["totals"]["decay_records"] == 3
    assert mem["events"]["recall"]["calls"] == 2
    assert mem["events"]["recall"]["vector_calls"] == 1
    assert mem["events"]["recall"]["results_total"] == 2
    assert mem["events"]["recall"]["source_counts"]["session_delta:s1"] == 2
    assert mem["events"]["recall"]["candidate_avg"]["text"] == 4.0
    assert mem["events"]["recall"]["candidate_avg"]["vec"] == 3.0
    assert mem["events"]["recall"]["candidate_avg"]["fused"] == 5.0
    assert mem["events"]["recall"]["latency_ms_p50"] == 20.0
    assert mem["events"]["recall"]["latency_ms_p95"] == 29.0
    assert mem["events"]["recall"]["cross_session_calls"] == 2
    assert mem["events"]["recall"]["cross_session_async_calls"] == 1
    assert mem["events"]["recall"]["cross_session_timeouts"] == 2
    assert mem["events"]["recall"]["cross_session_cancelled"] == 1
    assert mem["events"]["recall_hit_rate"][0]["hit_rate"] == 0.5

    assert mem["training_pairs"]["lines"] == 1
    assert mem["skill_candidates"]["lines"] == 1
    assert "fabric_status" in mem
    assert isinstance(mem["fabric_status"], dict)
    assert "embedding_batch" in mem
    assert "embedding_batch_hints" in mem
    assert isinstance(mem["embedding_batch_hints"], list)
    assert "memory_performance_hints" in mem
    assert isinstance(mem["memory_performance_hints"], list)


def test_observability_memory_metrics_runtime_batch_hints() -> None:
    class _RuntimeMemory:
        def stats(self):
            return {
                "provider": "openai",
                "total_records": 9000,
                "vector": {"backend": "client_scan", "math_backend": "python"},
                "batch": {
                    "retry_attempts_total": 25,
                    "fallback_calls_total": 8,
                    "resumed_jobs_total": 1,
                    "provider_disabled_total": 2,
                },
            }

    class _Runtime:
        memory = _RuntimeMemory()

    svc = ObservabilityService(runtime=_Runtime(), repo_root=".")
    overview = asyncio.run(svc.get_overview())
    mem = overview["memory"]
    hints = mem["embedding_batch_hints"]
    assert isinstance(hints, list)
    assert "openai_batch_disabled_check_api_key_org_billing" in hints
    assert "embedding_batch_fallback_spike_consider_reduce_concurrency_or_batch_size" in hints
    assert "embedding_retry_pressure_high_consider_backoff_and_rate_limit_tuning" in hints
    perf_hints = mem["memory_performance_hints"]
    assert "memory_vector_backend_client_scan_enable_sqlite_vec_or_pgvector_for_large_scale" in perf_hints
    assert "memory_vector_math_python_only_install_numpy_or_enable_vector_index" in perf_hints


def test_observability_memory_metrics_text_index_hint() -> None:
    class _RuntimeMemory:
        def stats(self):
            return {
                "provider": "openai",
                "total_records": 80000,
                "vector": {"backend": "client_scan", "math_backend": "numpy"},
                "warnings": ["large_corpus_without_fts_or_sqlite_vec"],
                "batch": {},
            }

    class _Runtime:
        memory = _RuntimeMemory()

    svc = ObservabilityService(runtime=_Runtime(), repo_root=".")
    overview = asyncio.run(svc.get_overview())
    hints = overview["memory"]["memory_performance_hints"]
    assert "memory_text_path_without_fts_enable_quentin_memory_fts_for_large_corpus" in hints


def test_observability_memory_schema_contract_keys(tmp_path: Path) -> None:
    events_path = tmp_path / "data" / "traces" / "events.jsonl"
    _write_jsonl(events_path, [])
    svc = ObservabilityService(runtime=None, repo_root=tmp_path)
    overview = asyncio.run(svc.get_overview())
    mem = overview["memory"]
    required = {
        "tiers",
        "total",
        "events",
        "sleep_outputs",
        "training_pairs",
        "skill_candidates",
        "fabric_status",
        "embedding_batch",
        "embedding_batch_hints",
        "memory_performance_hints",
        "sources",
    }
    assert required.issubset(set(mem.keys()))
