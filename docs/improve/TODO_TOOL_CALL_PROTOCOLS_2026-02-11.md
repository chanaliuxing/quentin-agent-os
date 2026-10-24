# TODO: Tool Call Protocol Adapters (Execution Fidelity)

Date: 2026-02-11
Scope: `quentin/llm/client.py`, `quentin/execution/skill_executor.py`, `quentin/tools/schemas.py`, `tests/*`

Problem:
- Quentin supports native tool calling in some paths, but fallback relies on parsing JSON from model text.
- Small/local models often output broken JSON, causing parse loops and repeated retries.
- The protocol selection logic is embedded inside the executor, not pluggable.

Goal:
- Introduce a pluggable "tool call protocol" layer:
  - Native function/tool calling (provider supports it).
  - JSON-in-text fallback protocol (robust parser).
  - Optional "strict schema" protocol for models that can follow it.
- Centralize protocol selection so the executor is simpler and loop behavior is more predictable.

Non-goals:
- Do not remove JSON fallback; it remains critical for local models.

Design (proposal):
- `ToolCallProtocol`:
  - `id`, `priority`
  - `supports(provider, model_name, tool_manager, config) -> bool`
  - `next_action(system_prompt, user_prompt, tools, state) -> ProtocolDecision`
- `ProtocolDecision`:
  - `kind`: `tool_call` | `final` | `error`
  - `tool_call`: normalized `{tool_name, args}`
  - `final_text` or `error`
  - `meta`: includes `protocol_id`, `retryable`, `confidence`
- Feature flag:
  - `QUENTIN_TOOL_CALL_PROTOCOLS=1` to enable protocol registry mode.
  - Keep current executor internal logic as fallback path.

Implementation Steps:
- [x] Add `quentin/llm/tool_call_protocols/base.py` + registry.
- [x] Add protocols:
  - [x] `native_tools_protocol.py` (wrap `call_llm_with_tools`).
  - [x] `json_fallback_protocol.py` (wrap `_robust_json_parse` behavior).
  - [x] `noop_protocol.py` (final answer only; for non-tool steps).
- [x] Refactor `quentin/execution/skill_executor.py`:
  - [x] Replace inline selection logic with protocol registry.
  - [x] Ensure repeated-tool-call loop detection remains.
- [x] Tests:
  - [x] `tests/unit/test_tool_call_protocol_registry.py`.
  - [x] `tests/unit/test_json_fallback_protocol_parsing.py`.
  - [x] `tests/integration/test_executor_protocol_switching.py` (simulate native failure => fallback).

Acceptance Criteria:
- Protocol selection is deterministic and testable.
- Executor reports which protocol was used and why.
- Loop behavior (repeated tool calls, no progress) produces an actionable self-awareness note.

Rollback:
- `QUENTIN_TOOL_CALL_PROTOCOLS=0` uses current executor logic.
