# Audit: Modular/Pluggable Landing Gaps (Blueprint v3 Plan)

Date: 2026-02-14
Scope:
- `docs/improve/BLUEPRINT_V3_MODULAR_PLUGGABLE_UPGRADE_PLAN_2026-02-11.md`
- P1/P2/P3 TODO docs listed by user

This document records audit findings vs Blueprint/TODO intent and tracks fixes as checkboxes.

## Summary

Status: **NOT fully conforming yet** (there are blockers that invalidate “all landed”).

Top issues:
- `SyntaxError` in `quentin/infra/concurrency/session_registry.py` breaks unit test collection and imports of BrainDaemon.
- Tool middleware pipeline (P1-C) exists in files, but is **not actually executed** in `ToolManager.call_tool()` path.
- Tool handler contract is inconsistent: some handlers expect `ToolCallRequest`, but `ToolManager.call_tool()` passes a `dict` payload, breaking MCP/plugin handlers.
- `SafetyKernel.guard_action()` async drift breaks tool guarding and creates widespread await/non-await mismatches.
- Legacy `meta_agent/evolution/*` loops had drifted into isolated implementations and were not aligned with Quentin canonical entrypoints.
- Diagnostics/Eval/Multi-agent outputs had partial MemoryFabric writeback but lacked consistent SystemEventQueue closure for CognitiveLoop/AutoFixer sensing.

## Findings (Ranked)

### F0 Blockers (must fix first)

1) Unit tests cannot be collected due to SyntaxError
- Evidence:
  - `quentin/infra/concurrency/session_registry.py` contains an unterminated f-string (lock file write).
- Impact:
  - `pytest tests/unit -q` fails during collection; all “evidence-first” guarantees are invalidated.
- Fix:
  - Make lock file writing syntactically correct, safe session_id -> filename, and ideally atomic create.
- Track:
  - [x] Fix `quentin/infra/concurrency/session_registry.py`
  - [x] Add unit tests for SessionRegistry locking (`tests/unit/test_session_registry.py`)

2) P1-C Tool middleware pipeline is not active in the tool execution path
- Evidence:
  - `docs/improve/TODO_TOOL_MIDDLEWARE_PIPELINE_2026-02-11.md` is marked done.
  - But `quentin/tools/manager.py` currently does not apply `_middlewares` in `call_tool()`.
- Impact:
  - “after hooks” never run; error normalization/hints don’t happen; pipeline is effectively a no-op.
- Fix:
  - Wrap `call_tool()` with middleware chain before+after when `QUENTIN_TOOL_MIDDLEWARE_PIPELINE=1`.
- Track:
  - [x] Ensure before middleware runs before safety guard (via `ToolMiddlewareChain.run_before`)
  - [x] Ensure after middleware runs on every ToolCallResult (via `ToolMiddlewareChain.run_after`)
  - [x] Make legacy `add_before_hook()` compatible (shim middleware)

3) Tool handler contract mismatch (ToolCallRequest vs dict payload)
- Evidence:
  - MCP tool provider handler reads `req.payload`: `quentin/tools/providers/mcp.py`
  - Plugin loader handler expects `ToolCallRequest`: `quentin/tools/plugin_loader.py`
  - But `ToolManager.call_tool()` calls handlers with `params: dict` in some paths.
- Impact:
  - Tools register successfully but receive empty/incorrect args at runtime; silent failures.
- Fix:
  - Support both handler styles: prefer passing `ToolCallRequest` when handler expects it, otherwise pass dict payload.
- Track:
  - [x] Fix `_call_handler_with_optional_ctx` / dispatch logic in ToolManager (request-style + dict-style handlers)
  - [x] Add unit coverage for “request-style handler” (`tests/unit/test_tool_manager_request_style_handler.py`)

4) SafetyKernel async drift breaks tool guarding contract
- Evidence:
  - `quentin/kernel/safety.py` had `async def guard_action(...)`.
  - Many call sites use `kernel.guard_action(action)` synchronously.
- Impact:
  - `ToolManager` attempted `await kernel.guard_action(...)` and blew up when kernel returns non-awaitable decisions.
  - Broad contract mismatch that can cascade into “all landed” false positives.
- Fix:
  - Keep `SafetyKernel.guard_action()` sync (Option A). Human approval should be implemented as a pluggable interceptor/middleware (default OFF).
- Track:
  - [x] Make `SafetyKernel.guard_action()` synchronous again
  - [x] Implement approval gate as optional SafetyKernel gate (default OFF) via `QUENTIN_APPROVAL_GATE=1`

11) Self-programming trigger wiring (avoid “island engine”)
- Notes:
  - AutoFixer existed but was unguarded and too implicit for Blueprint safe-default expectations.
- Track:
  - [x] Gate AutoFixer behind `QUENTIN_AUTO_FIXER_ENABLED=1` (default OFF)
  - [x] Expand AutoFixer signals to include blocked-actions / capability-gap hints (still uses EngineV2 backend)

### F1 High Priority Gaps (needs strengthening)

4) “Config-only switching” is incomplete for some modules
- Skill backends TODO claims `QUENTIN_SKILL_BACKEND`, but code does not honor it.
- Self-prog backends TODO claims `QUENTIN_SELFPROG_BACKEND`, but code does not honor it.
- Router/Dialect TODO claims `QUENTIN_ROUTING_POLICY`/`QUENTIN_PROMPT_DIALECT`, but implementation uses plugin enable flags and `call_llm()` does not apply dialect plugins.
- Track:
  - [x] Decide canonical env var names (match TODO) and implement adapters (`QUENTIN_ROUTING_POLICY`, `QUENTIN_PROMPT_DIALECT`, `QUENTIN_SKILL_BACKEND`, `QUENTIN_SELFPROG_BACKEND`)
  - [x] Ensure `quentin/llm/client.py:call_llm()` applies prompt dialect plugin in one place (validated by `tests/unit/test_llm_client_prompt_dialect.py`)

5) Observability EventStore backend selection + tests are not complete
- Evidence:
  - Backend abstraction exists (`quentin/runtime/event_store/*`) and SystemEventQueue uses it.
  - TODO still has open items: backend selection via `QUENTIN_OBS_EVENT_STORE_BACKEND` and tests.
- Track:
  - [x] Implement backend selection via config/env (`QUENTIN_OBS_EVENT_STORE_BACKEND`)
  - [x] Add `tests/unit/test_event_store_backend_file.py`

6) Env var canonicalization drift vs TODO docs (Router/Dialect/Skill/SelfProg)
- Track:
  - [x] Router policy uses `QUENTIN_ROUTING_POLICY` (back-compat `QUENTIN_ROUTING_POLICY_PLUGINS=1`)
  - [x] Prompt dialect uses `QUENTIN_PROMPT_DIALECT`
  - [x] Skill backend selection honors `QUENTIN_SKILL_BACKEND`
  - [x] Self-prog backend bundle selection honors `QUENTIN_SELFPROG_BACKEND` (minimal variants)

### F1.5 OpenClaw Parity Gaps (ported in this repo but not consistently wired)

7) Env normalization & port management modules
- Notes:
  - OpenClaw has a dedicated env normalizer (bool parsing, legacy mapping) and port manager (availability/owner).
- Track:
  - [x] Add `quentin/infra/env_manager.py` (parse helpers + conservative normalize())
  - [x] Add `quentin/infra/network/port_manager.py` (best-effort availability + owner introspection)

8) Lane-based concurrency hierarchical resolution
- Notes:
  - Current lanes exist but lacked an explicit hierarchical resolver API (session + global + optional sublane).
- Track:
  - [x] Add `resolve_lane_hierarchy()` + `enqueue_hierarchical()` in `quentin/infra/concurrency/lanes.py`

9) Retry/failover implementation hygiene
- Track:
  - [x] Fix async sleep bug in `quentin/infra/llm/failover.py`
  - [x] Fix missing `sleep_with_jitter()` in `quentin/infra/llm/retry.py`

10) Gateway-style API entrypoint
- Track:
  - [x] Add `quentin/api/server.py` wrapper app (mounts `meta_agent.api.server`)

12) Diagnostics/Eval persistence into MemoryFabric (avoid “log-only islands”)
- Notes:
  - Diagnostics/eval modules existed but mostly wrote to JSONL/logs; optional persistence enables consolidation/recall.
- Track:
  - [x] EvalHarness can persist suite summary into MemoryFabric via `QUENTIN_EVAL_RESULTS_TO_MEMORY=1`.
  - [x] ObservabilityService can persist overview/audit snapshot into MemoryFabric via `QUENTIN_DIAGNOSTICS_TO_MEMORY=1`.

13) Multi-agent routing as a pluggable routing policy (close “multi-agent island”)
- Track:
  - [x] Add `MultiAgentRoutingPolicy` (id `multi_agent`) and register in routing policy bootstrap.
  - [x] Add unit coverage `tests/unit/test_routing_policy_multi_agent.py`.

14) Legacy "old brain" convergence (`meta_agent/evolution/*`) to avoid split-brain runtime
- Notes:
  - Legacy modules remained importable but had implementation drift and missing dependencies.
- Track:
  - [x] `meta_agent/evolution/cognitive_loop.py` converted to deprecated compatibility shim delegating to `quentin.cognitive.loop.CognitiveLoop`.
  - [x] `meta_agent/evolution/sleep_loop.py` converted to deprecated compatibility shim delegating to `quentin.sleep.loop.SleepLoop`.
  - [x] `meta_agent/evolution/skill_evolution_loop.py` converted to deprecated compatibility shim aligned to Quentin skill candidate pipeline.
  - [x] `quentin/daemon_entry.py` marked as compatibility entrypoint and switched to canonical API app path.

15) Diagnostics/Eval/Multi-agent event closure into EventStore backend
- Notes:
  - Memory writeback existed (opt-in), but core outputs were not consistently surfaced to SystemEventQueue.
- Track:
  - [x] EvalHarness emits `evaluation_suite_completed` event (opt-in: `QUENTIN_EVAL_RESULTS_TO_EVENTS` or `QUENTIN_OUTCOME_EVENTS`).
  - [x] MultiAgentCoordinator emits `multi_agent_routing_decision` event (opt-in: `QUENTIN_MULTI_AGENT_EVENTS` or `QUENTIN_OUTCOME_EVENTS`).
  - [x] ObservabilityService emits `diagnostics_overview_ready` event (opt-in: `QUENTIN_DIAGNOSTICS_TO_EVENTS` or `QUENTIN_OUTCOME_EVENTS`).

### F2 Documentation Consistency

6) TODO checkboxes and file paths drift from actual code
- Example:
  - `docs/improve/TODO_MODULAR_TASK_SOURCES_2026-02-11.md` references `quentin/runtime/task_sources.py`, but current code uses `quentin/runtime/task_sources/`.
  - Some tests exist but are not checked in TODO doc.
- Track:
  - [x] Update TODO docs to reflect current file paths and actual tests

## Fix Log

- 2026-02-14:
  - [x] Started audit and created this doc.
  - [x] Stabilized unit-test baseline (`pytest tests/unit -q` now green).
  - [x] Re-aligned `PathGuard` defaults to conservative write roots (prevents writing `quentin/kernel/*`, `quentin/config/*` by default).
  - [x] Repaired ToolPackRegistry contract (priority ordering, enabled() skipping, reports) to match Blueprint modular registry shape.
  - [x] Repaired PromptFactory contract (required section labels + stable ordering).
  - [x] Repaired LLM client contracts for unit-testable provider shims (OpenAI/Gemini HTTP stubs via `httpx.Client`; Ollama native shims via `OllamaClient` + `apply_context_budget`).
  - [x] Repaired PatchFlow backlog task source to be monkeypatch-friendly at `quentin.runtime.task_sources.PatchQueue`.
  - [x] Repaired Interactive shell tool API (start/write/poll/kill; disabled by default).
  - [x] Simplified SessionDeltaWriter throttling logic to match intended behavior and avoid dead code paths.
  - [x] Added API backend integration test for SystemEvents (`tests/integration/test_system_events_api_backend.py`).
  - [x] Added missing contract tests for request-style ToolCall handlers and prompt dialect injection.
  - [x] Updated TODO checkboxes for TaskSources/EventStore integration tests to match landed code.
  - [x] Added Context Snapshot test coverage (`tests/unit/test_context_snapshot_budgeting.py`, `tests/unit/test_file_tree_snapshot_bounds.py`, `tests/integration/test_prompt_contains_runtime_snapshot.py`).
  - [x] Added Tool Call Protocol test coverage (`tests/unit/test_tool_call_protocol_registry.py`, `tests/unit/test_json_fallback_protocol_parsing.py`, `tests/integration/test_executor_protocol_switching.py`).
  - [x] Implemented protocol chain fallback in executor path: native protocol errors now degrade to lower-priority protocols (e.g. `json_fallback`).
