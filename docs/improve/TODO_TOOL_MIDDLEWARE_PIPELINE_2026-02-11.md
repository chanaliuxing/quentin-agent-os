# TODO: Tool Middleware Pipeline (Before + After Hooks)

Date: 2026-02-11
Scope: `quentin/tools/manager.py`, `quentin/tools/middleware/*`, `tests/*`

Problem:
- ToolManager currently supports only `before_hooks`.
- Recovery and self-healing needs "after hooks" to annotate tool results with heuristics (gentle traps).
- Hooks are appended ad-hoc, not discoverable, not ordered by policy, and not easily testable as a pipeline.

Goal:
- Model tool middleware as an explicit pipeline with:
  - before: mutate args, enforce guards, add metadata
  - after: wrap errors, add hints, normalize outputs
- Make middleware pluggable and ordered.

Non-goals:
- Do not move safety enforcement out of SafetyKernel; middleware supplements it.

Design (proposal):
- `ToolMiddleware`:
  - `id`, `priority`
  - `before(tool_name, args, ctx) -> (args, ctx_delta)`
  - `after(tool_name, args, result, ctx) -> (result, ctx_delta)`
- `ToolMiddlewareChain` owned by ToolManager.
- Feature flag:
  - `QUENTIN_TOOL_MIDDLEWARE_PIPELINE=1` to enable chain mode.
  - Keep legacy `add_before_hook()` working by wrapping into middleware shims.

Implementation Steps:
- [x] Add `quentin/tools/middleware/base.py` defining middleware protocol + chain runner.
- [x] Update `quentin/tools/manager.py`:
  - [x] Add middleware chain (before+after) behind `QUENTIN_TOOL_MIDDLEWARE_PIPELINE=1`.
  - [x] Keep legacy `add_before_hook()` working via a shim middleware in chain mode.
  - [x] Record middleware-added deltas under `ctx.metadata["tool_middleware"]`.
- [x] Add default middleware:
  - [x] Path fixer (existing) as a middleware (`quentin/tools/middleware/path_fixer.py:PathFixerMiddleware`).
  - [x] Heuristic error wrapper (`quentin/tools/middleware/error_hints.py:ErrorHintsMiddleware`):
    - promotes `{"status":"error","error":...,"hint":...}` dict outputs into `ToolCallResult.success/error/meta`
    - adds actionable hints for common patterns (search_replace misses, interactive TTY blocks)
  - [x] Tool-not-found hinting preserved via `KeyError` message enrichment in `ToolManager.call_tool()`.
- [x] Tests:
  - [x] `tests/unit/test_tool_middleware_chain.py` (ordering + after reverse + ctx merge).
  - [x] `tests/unit/test_tool_error_heuristics.py` (dict error normalization + hint carryover).

Acceptance Criteria:
- A tool failure yields an actionable hint without changing core error semantics.
- Middleware ordering is deterministic and test-covered.

Rollback:
- `QUENTIN_TOOL_MIDDLEWARE_PIPELINE=0` uses legacy behavior (before-only hooks).
