# Brain AutoLoop (verify → analyze → fix → test)

## Purpose
- Keep Quentin core architecture unchanged.
- Iterate in engineering layer: run verify, analyze logs, generate fixes, run tests, loop.
- Stop immediately when Gemini quota/token is exhausted.

## Quick Start
```bash
cp config/brain_autoloop.example.json config/brain_autoloop.local.json
python3 scripts/brain_autoloop.py --config config/brain_autoloop.local.json
```

## Important Safety Choice
- Repository default keeps `CODER_BACKEND=llm_client` (normal behavior unchanged).
- AutoLoop can override env only inside subprocess via:
  - `env_overrides.CODER_BACKEND=auto_cli`

## Stop Conditions
- `verify` and tests both green → stop.
- Gemini returns quota/rate-limit/token-exhaust patterns → stop.
- Fixer output is not valid JSON plan → stop.
- Fixer produced no real file changes (configurable) → stop.
- Optional benchmark not improved (`require_benchmark_improve=true`) → stop.
- Max iterations reached → stop.

## Fixer Completion Contract
- AutoLoop only treats fixer as "done" when:
  - Gemini process exits (or times out),
  - `fixer_raw.txt` can be parsed into JSON plan,
  - `changes` are applied and `apply_report.json` contains non-empty `changed_files` (when enabled).

## Optional Benchmark Gate
- Configure `benchmark_command` to run after tests each iteration.
- Example command uses `scripts/benchmark_websearch_tool.py`.
- AutoLoop stores summary in iteration record and can stop on regression.

## Output
- Run artifacts: `generated/brain_autoloop/<timestamp>/`
- Per-iteration files:
  - `verify_stdout.log`, `verify_stderr.log`
  - `log_events.jsonl.txt`, `log_audit_events.jsonl.txt`, `log_llm_raw_history.jsonl.txt`
  - `analyzer_prompt.txt`, `analyzer_raw.txt`, `issues.json`
  - `fixer_prompt.txt`, `fixer_raw.txt`
  - `tests_stdout.log`, `tests_stderr.log`
  - `run_report.json`
