# Memory Intelligence Benchmark

Date: 2026-02-21

Script: `scripts/bench_memory_intelligence.py`  
Pipeline: `scripts/run_memory_intelligence_pipeline.py`  
Default config: `config/memory_intelligence_slo.json`

## Purpose
- Measure whether memory behavior is getting smarter for task outcomes.
- Keep latency as a constraint, not the primary objective.
- Emit actionable weak-signal diagnostics instead of only aggregate scores.

## Core Metrics
- `task_success_rate`: expected memory appears in top-k for task queries.
- `first_hit_useful_rate`: top-1 is useful for task resolution.
- `error_recurrence_rate`: after correction memory injection, error repeats at top-1.
- `memory_pollution_rate`: top-k contamination by irrelevant-domain records.
- `intelligence_score`: weighted trend score from the above metrics.

Default benchmark profile uses mixed difficulty (`--case-profile mixed`):
- 50% exact-token queries
- 50% semantic queries (no exact token)

## Run
```bash
python scripts/bench_memory_intelligence.py \
  --backend sqlite \
  --n 1000,10000 \
  --modes text_only,vector_only,hybrid \
  --cases 40 --runs 5 --warmup 1 --dim 768 --top-k 10 \
  --case-profile mixed --query-domain-policy case \
  --out data/bench/memory_intelligence_bench.jsonl
```

sqlite-vec in venv:
```bash
venv/bin/python scripts/bench_memory_intelligence.py \
  --backend sqlite_vec --require-index-backend \
  --n 1000,10000 --modes vector_only,hybrid --cases 40 \
  --runs 5 --warmup 1 --dim 768 --top-k 10 \
  --case-profile mixed --query-domain-policy case
```

Pipeline:
```bash
python scripts/run_memory_intelligence_pipeline.py \
  --backend sqlite \
  --n 1000,10000 \
  --modes text_only,vector_only,hybrid \
  --cases 40 --runs 5 --warmup 1 --dim 768 --top-k 10 \
  --case-profile mixed --query-domain-policy case
```

Scale matrix runner (tiered long-run with timeout + summary):
```bash
venv/bin/python scripts/run_memory_intelligence_scale_matrix.py \
  --backend sqlite_vec --require-index-backend \
  --n 10000,30000,100000 \
  --modes hybrid --case-profile mixed --query-domain-policy case \
  --cases 40 --runs 1 --warmup 0 --dim 768 --top-k 10 \
  --timeout-s 1800 --fail-fast
```
Writes:
- per-tier jsonl: `/tmp/memory_intelligence_scale/bench_n<k>.jsonl`
- summary: `/tmp/memory_intelligence_scale/scale_summary.json`

## Failure Semantics
- `--fail-on-slo` returns exit code `2` on threshold violations.
- `--require-index-backend` returns exit code `3` when `sqlite_vec` was requested but not active.
- Pipeline precheck (`sqlite_vec`) uses `scripts/check_sqlite_vec_env.py --strict` and returns exit code `5` on env-not-ready.

## Interpretation
- Priority order for optimization:
1. Raise `task_success_rate`.
2. Raise `first_hit_useful_rate`.
3. Reduce `error_recurrence_rate`.
4. Reduce `memory_pollution_rate`.
5. Then optimize latency/cost.
