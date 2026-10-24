# Milestone: Brain Stabilization (Pre-sensing + Trace Serialization + Smoke Verification)
**Date**: Feb 15, 2026
**Status**: Implemented (scope-limited) ✅

This milestone is intentionally narrow: it addresses the concrete, repeatedly observed failures from `verify_system.py` runs on a local laptop:
- Pre-sensing "blindness" caused by truncated directory listings.
- Trace serialization crashes with `maximum recursion depth exceeded`.
- Verification runs triggering self-programming / patchflow side effects.

## What Actually Shipped
### 1) Cycle-safe JSON serialization (prevents recursion crashes)
- Hardened JSON conversion with cycle detection, depth/item limits, string truncation, and safe `__dict__` handling.
- Done-check serialization now delegates to the same hardened conversion.

### 2) Focused pre-sensing evidence for large directories
- Directory evidence now includes:
  - `contents_head` + `contents_total`
  - `contents_matches` filtered by task keywords
  - explicit probes for expected plugin children (e.g. `extensions/tools/gemini_cli/{manifest.yaml,logic.py}`) when the task suggests Gemini.
- Focus paths include non-existent paths too (negative evidence), which makes "not done" determinations more reliable.

### 3) Safer default verification mode (smoke instead of stress)
- `verify_system.py` defaults to a smoke-style run that disables self-programming / patchflow behaviors.
- Tool-call protocol registry is forced on to avoid fragile "JSON-in-text" parsing.
- Stress mode is still available via `QUENTIN_VERIFY_STRESS=1`.

### 4) Reduced redundant `mkdir -p` noise
- `mkdir -p <dir>` returns `skipped` if the directory already exists.

## What Did NOT Ship (Do Not Assume)
The following items are **not** part of this milestone unless separately implemented and verified:
- `fs.write_file` idempotency / manifest schema validation
- SelfAwarenessEngine "format salvage" noise down-weighting
- Skill mining trigger / graph query-by-intent
- Ruff / mypy / quality gate middleware

## Acceptance (How To Verify)
Run unit tests that specifically cover the fixes:
- `pytest -q tests/unit/test_make_jsonable_cycle_guard.py`
- `pytest -q tests/unit/test_trace_event_serialization_no_recursion.py`
- `pytest -q tests/unit/test_pre_sensing_report_directory_matches.py`

Run smoke verification (no self-programming side effects expected):
- `python3 verify_system.py`

Run stress verification (explicitly allows background side effects):
- `QUENTIN_VERIFY_STRESS=1 python3 verify_system.py`
