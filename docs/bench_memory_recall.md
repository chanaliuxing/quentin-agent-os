# Memory Recall Micro-Benchmark

Date: 2026-02-06

Script: `scripts/bench_memory_recall.py`
Output: `data/bench/recall_bench.jsonl` (ignored by git)

## What It Measures
- Latency: `avg/p50/p95` ms per recall call.
- Correctness proxy: `hit@k`:
  - `text_only`: top-k contains the expected text record.
  - `vector_only`: top-k contains the expected vector record.
  - `hybrid`: top-k contains BOTH the expected text and vector records (and also reports `hit_text@k` / `hit_vec@k`).

The benchmark uses synthetic records with bracketed codes like `[CODE:E00042]` to avoid `LIKE` substring false positives.

For intelligence-first evaluation (task success / first-hit usefulness / recurrence / pollution),
use `docs/bench_memory_intelligence.md` and `scripts/bench_memory_intelligence.py`.

## How To Run
```bash
python scripts/bench_memory_recall.py
python scripts/bench_memory_recall.py --n 1000 --runs 20 --top-k 10
python scripts/bench_memory_recall.py --backend sqlite_vec --n 10000 --runs 10
```

## Notes
- Results vary by machine and SQLite configuration; regenerate locally after any memory-store change.
- `sqlite_vec` backend requires the sqlite-vec extension; if unavailable, use `--backend sqlite`.
- Plain SQLite vector recall uses client-side cosine; control scan behavior with `QUENTIN_MEMORY_VECTOR_SCAN_LIMIT` (default: 20000). Larger values improve hit@k but cost latency; prefer `sqlite_vec` for speed.

## Result Template
Update this section after regenerating `data/bench/recall_bench.jsonl`:
- 1,000 records:
- 10,000 records:
