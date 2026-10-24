# SQLite Vec Memory Store (Optional)

This project can use an optional sqlite-vec backend for vector search while keeping the
same MemoryFabric API. When the extension is missing, it automatically falls back to
the standard SQLite store.

## Enable

- Set `QUENTIN_MEMORY_STORE=sqlite_vec`
- Provide the extension path if needed: `QUENTIN_SQLITE_VEC_PATH=/path/to/vec0`
- Optional: `MEM_EMBED_DIM=768` to match your embedding dimension
- Precheck sqlite-vec readiness:
  - `python scripts/check_sqlite_vec_env.py --strict`
  - exits with code `5` when neither env-path extension nor python module load path is usable
- Verify with benchmark guard:
  - `python scripts/bench_memory_recall.py --backend sqlite_vec --n 10000 --modes vector_only --require-index-backend`
  - exits with code `3` when sqlite-vec is not active (instead of silently accepting fallback)
- Rebaseline SLO from index-backed results only:
  - `python scripts/rebaseline_memory_slo.py --in data/bench/recall_bench.jsonl --out config/memory_recall_slo.generated.json --backend sqlite_vec --vector-backend sqlite_vec --fail-on-empty`
  - exits with code `4` when no index-backed rows are available after filtering
- One-shot pipeline:
  - `python scripts/run_memory_slo_pipeline.py --backend sqlite_vec --require-index-backend --vector-backend sqlite_vec --n 10000,100000,1000000 --tiers 10000,100000,1000000`
  - runs precheck + benchmark + guarded backend check + SLO generation in one command
  - use `--skip-precheck` only when environment readiness is validated elsewhere

## Behavior

- If the extension loads successfully, vector search uses the sqlite-vec virtual table.
- If the extension fails to load, the store logs a warning and falls back to `sqlite`.
- Reindex uses a rebuild-and-swap strategy for the vec tables to keep the old index available on failure.

## Notes

- This is a local-only optimization and requires a compiled sqlite-vec extension
  compatible with your platform and SQLite build.
- No secrets are required; remote providers are not used here.
