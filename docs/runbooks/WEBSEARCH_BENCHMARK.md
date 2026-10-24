# WebSearchTool Benchmark

## Goal
- Provide objective scoring for `extensions/tools/web_search`.
- Prove "this round is better than previous round" by numeric delta + pass gate.

## Run
```bash
python3 scripts/benchmark_websearch_tool.py \
  --tool-dir extensions/tools/web_search \
  --previous-report generated/benchmarks/web_search_benchmark_prev.json \
  --output generated/benchmarks/web_search_benchmark_report.json \
  --pass-score 75
```

## What is scored
- `manifest` (20): existence, parse, required fields, `output_trust`, entrypoint.
- `logic_load` (20): file exists and imports successfully.
- `contract` (20): callable `run` or `perform_search`.
- `functional` (30): mocked live call returns structured results and safe empty-query behavior.
- `quality` (10): no placeholder key, no interactive `input()`, no `__main__` interactive-only flow.

## Improvement proof
- Report has:
  - `score.total`
  - `comparison.previous_total`
  - `comparison.delta_total`
  - `comparison.improved`
- Recommend gate:
  - `score.passed == true`
  - `comparison.delta_total >= 1.0`
