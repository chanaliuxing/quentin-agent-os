# Memory Intelligence Benchmark TODO (Intelligence-First)

## Goal
- Primary objective: improve real memory-enabled task effectiveness (smarter behavior), not chase synthetic full scores.
- Constraint objective: keep latency/cost within usable bounds without sacrificing quality.

## Scoring Dimensions (Weighted)
- [x] Define `task_success_rate` as the top-level quality signal.
- [x] Define `first_hit_useful_rate` to capture precision of top-1 retrieval.
- [x] Define `error_recurrence_rate` to capture post-correction learning ability.
- [x] Define `memory_pollution_rate` to capture irrelevant/noisy recall contamination.
- [x] Define weighted `intelligence_score` for trend tracking (not final objective).

## Benchmark Design
- [x] Build deterministic synthetic corpus with domain anchors and explicit expected tokens.
- [x] Add mixed retrieval modes (`text_only`, `vector_only`, `hybrid`) in one benchmark run.
- [x] Add latency collection (`avg`, `p95`) as secondary constraints.
- [x] Add backend observability (`store`, `vector_backend`, `vector_math_backend`, `fetch_strategy`).
- [x] Add issue diagnostics for low intelligence signals and backend fallback.

## Threshold and Governance
- [x] Add config file for thresholds (`*_min`, `*_max`) and metric weights.
- [x] Add SLO evaluation path and fail-fast option (`--fail-on-slo`).
- [x] Keep threshold checks objective and interpretable (clear violation messages).

## Execution Pipeline
- [x] Add one-shot intelligence pipeline script.
- [x] Integrate sqlite-vec precheck for indexed backend runs.
- [x] Keep benchmark output machine-readable (`jsonl`) for downstream analysis.

## Testing
- [x] Add integration test for intelligence benchmark script run.
- [x] Add integration test for intelligence pipeline script run.
- [x] Assert required metric fields exist in produced artifacts.

## Documentation and Gap Sync
- [x] Add benchmark usage doc focused on intelligence metrics.
- [x] Sync migration log (`openclaw_memory_incremental_port.md`) with landed increment.
- [x] Sync gap todo (`openclaw_memory_gap_todo.md`) with completed rollout items.

## Rollout Acceptance Criteria
- [x] Can run benchmark with sqlite backend in CI/dev quickly.
- [x] Can run benchmark with sqlite_vec backend in venv with precheck and no fallback.
- [x] Report clearly identifies weak metrics instead of only printing aggregate score.
- [x] Team can iterate by optimizing weak dimensions one by one.
