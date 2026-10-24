# Tool Adaptation Benchmark TODO

Date: 2026-02-22
Latest report: `generated/benchmarks/tool_adaptation_benchmark_report.json`

## Run Snapshot
- Command:
  - `PYTHONPATH=. python scripts/tool_adaptation_benchmark.py --output generated/benchmarks/tool_adaptation_benchmark_report.json --previous generated/benchmarks/tool_adaptation_benchmark_prev.json --history generated/benchmarks/tool_adaptation_benchmark_history.jsonl --min-score 0.7 --moving-window 5 --trend-drop-tolerance 0.05 --ci-mode`
- Current result:
  - `quality_score=1.0`
  - `pass=true`
  - `schema_ok=true`
  - `trend_guard.pass=true`

## Landed In This Round
- [x] Added decision-level memory visibility case (`decision_memory_reuse_effect`)
- [x] Added natural-language affordance generalization case (`nl_generalization_affordance`)
- [x] Added failure->fallback recovery case (`failure_recovery_fallback`)
- [x] Upgraded cache case with latency/speedup metrics (`tool_plugin_cache`)
- [x] Added cross-session persistence case (`cross_session_persistence`)
- [x] Added `meta_agent` registry/sync path case (`meta_agent_registry_path`)
- [x] Added domain-calibrated case weights
- [x] Added trend guard (`moving_window`, `trend_drop_tolerance`)
- [x] Added report schema version + schema validation gate
- [x] Added CI mode and environment snapshot
- [x] Exposed new benchmark knobs in both:
  - `scripts/tool_adaptation_benchmark.py`
  - `python -m quentin.cli.qctl bench-tool-adaptation`
- [x] Replaced plugin-internal NL generalization with executor-level selection path benchmark
- [x] Upgraded decision reuse from prompt visibility to A/B measurable retry delta benchmark
- [x] Added memory conflict robustness case (`memory_conflict_resolution`)
  - Landed:
    - Inject conflicting tool memories (`bench.screwdriver` vs unknown `bench.box_opener`).
    - Executor knowledge prompt keeps known tool and filters unknown tool.
- [x] Added latency percentiles and replay metadata
  - Landed:
    - `timeout_summary` now contains `runtime/tool_runtime p50,p90`.
    - report now includes `replay.seed` + exact rerun command.
- [x] Added operations exports and remediation queue
  - Landed:
    - Added NDJSON trend export (`generated/benchmarks/tool_adaptation_trend.ndjson`).
    - Added `remediation_queue` generated from `regression_explain.failed_cases`.

## Current Gaps (Next Iteration)

### P0 (high impact)
- [x] Replace plugin-level generalization with planner/executor-level tool selection benchmark
  - Landed:
    - `nl_generalization_affordance` now runs through `Executor._fallback_llm_execute`, not direct plugin call.
    - Case output now records selection trace (`selected_tool`, `reason`) and fallback rationale.

- [x] Add real decision-reuse metric
  - Landed:
    - `decision_memory_reuse_effect` now runs A/B (`tool_knowledge prompt on/off`).
    - Benchmark checks measurable deltas: first selected tool + retries before success.

### P1 (stability)
- [x] Add deterministic fixtures for benchmark tools to reduce pydantic/noise warnings in CI logs
  - Landed:
    - Benchmark run now supports deterministic fixture mode (`QUENTIN_BENCHMARK_FIXTURE_MODE=1`, fixed TZ/hash in CI mode).
    - Unit test adds benchmark-specific warning filters for known pydantic deprecation noise.

- [x] Add strict report schema JSON file and validate against schema (not only key/type checks)
  - Landed:
    - Added schema file: `quentin/benchmarks/schemas/tool_adaptation_report.schema.json`.
    - Report validation now loads schema and runs recursive strict checks (required/type/additionalProperties).

- [x] Add case-level timeout budgets and timeout diagnostics in report
  - Landed:
    - Every case now writes `runtime_ms`, `timeout_budget_ms`, `timeout_exceeded`.
    - Added top-level `timeout_summary` and pass breakdown gate `timeout_pass`.

### P2 (operational)
- [x] Add a benchmark “regression explain” section auto-generated from failed cases
  - Landed:
    - Added `regression_explain` with failed case issue keys and suggested actions.

- [x] Add rolling trend export for dashboarding (`quality_score`, `dimension deltas`, `top issue keys`)
  - Landed:
    - Added `trend_export` with moving averages, dimension deltas, rolling issue keys, timeline tail.

## Execution Order
1. P0 planner/executor-level decision benchmarks. ✅
2. P1 schema strictness + stability hardening. ✅
3. P2 operational reporting and dashboard-oriented exports. ✅

## Next Wave
- [x] Full loop robustness benchmark (`planner -> executor -> done`) under adversarial memory injection.
  - Landed:
    - Added `full_loop_adversarial_memory` case.
    - Injects adversarial tool memory, runs full loop with stub LLM, requires `done` + `BENCH_DONE` evidence.
- [x] Add end-to-end fallback-reason trace requirement in full loop robustness case.
  - Landed:
    - Case requires trace evidence of fallback reason (`tool_execution_error`) via `attempt_evaluated` / planning diagnostics.
- [x] Add domain-specific weighting presets auto-tuned from historical failures.
  - Landed:
    - Added history-pressure weight autotuning (`weight_tuning`) on top of domain base weights.
    - Supports disable switch (`--no-auto-tune-weights`) for stable A/B calibration.
- [x] Add channel gateway productization benchmark cases.
  - Landed:
    - Added `channel_gateway_contract` (flag gating, inbound accepted, outbound routing/404).
    - Added `domain_adapter_channel_gateway` (single intent reused across discord/slack/telegram).
- [x] Add channel provider governance/resilience benchmark cases.
  - Landed:
    - Added `channel_provider_config_gate` (missing token fail-closed).
    - Added `channel_listener_resilience_policy` (retry/backoff/error classification contract).
