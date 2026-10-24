# OpenClaw Planning Incremental Port (Quentin)

## Goal
- Incrementally port OpenClaw planning-layer engineering patterns into Quentin.
- Keep all hard constraints and fallback paths configurable via env for hot-pluggable provider/runtime switching.

## OpenClaw Planning File Mapping

### `payloads.ts` (reactive prompt matrix)
- Landed in Quentin:
  - `quentin/cognitive/planning_payload_matrix.py`
  - `quentin/cognitive/phase_payloads.py`
  - `quentin/cognitive/loop_planner.py`
- Behavior:
  - lifecycle stages: `initial` / `retry` / `stuck`
  - stage directives injected into planner system prompt + user prompt
  - stuck stage forces speculative probes

### `payloads.ts` deep parity increment (stage x failure x tool family)
- Landed in Quentin:
  - `quentin/cognitive/planning_payload_variants.py`
  - integration in `quentin/cognitive/loop_runtime_helpers.py`
  - prompt/hints/council payload injection in `quentin/cognitive/loop_planner.py`
  - repair/fallback enforcement in `quentin/cognitive/loop_plan_guards.py`
- Behavior:
  - derives variant by:
    - stage (`initial|retry|stuck`)
    - failure category (`environment_timeout_error`, `model_syntax_error`, ...)
    - tool family (`shell|browser|filesystem|generic`)
  - injects specialized directives and required prechecks
  - examples:
    - shell timeout retry -> `pwd/id/ls` diagnostics + avoid same command replay
    - browser failure -> page/selector readiness probe before click/type retry
  - tool-feedback turn sync:
    - when tool-only no-update turns reach threshold, planner lifecycle now sets `force_progress_sync`
    - repair layer injects a user-visible progress sync step before further tool calls

### `payloads.ts` subcategory increment (tool-error subtype)
- Landed in Quentin:
  - `quentin/cognitive/tool_error_subtypes.py`
  - wired in `quentin/cognitive/attempt_evaluator.py` (`error_subcategory`)
  - consumed by:
    - `quentin/cognitive/planning_payload_variants.py`
    - `quentin/cognitive/planning_strategy_patch.py`
- Subtypes currently mapped:
  - shell: `shell_permission_denied`, `shell_timeout`, `shell_command_not_found`
  - browser: `browser_selector_not_found`, `browser_navigation_timeout`, `browser_stale_element`
  - filesystem: `filesystem_path_not_found`, `filesystem_permission_denied`, `filesystem_validation_error`
- Effect:
  - same category can now trigger different required prechecks/avoid-actions by subtype.

### process-based observability surface
- Landed in Quentin:
  - planning trace diagnostics in `quentin/cognitive/loop_orchestration.py`
  - aggregated intelligence diagnostics in `quentin/observability/service.py`
- Captured fields:
  - `attempt_stage`
  - `failure_category`
  - `error_subcategory`
  - `strategy_patch_id`
  - `payload_variant_id`
  - `payload_tool_family`
  - `retry_delta_reason`
- Outcome:
  - process-level verification can now score whether planning strategy actually switched by subtype/variant, not only by final task result.

### process-based intelligence audit scoring
- Landed in Quentin:
  - `quentin/diagnostics/intelligence_auditor.py`
- Added `strategy_regression.strategy_switching` metrics:
  - `planning_diag_total`
  - `risky_without_diag`
  - `variant_coverage`
  - `strategy_patch_coverage`
  - `retry_delta_coverage`
  - `subcategory_alignment_rate`
  - `strategy_switch_effectiveness` (weighted score)
- This allows verify-system/evolution loops to penalize runs that "got result right" but failed to switch planning strategy properly.

### verify gate integration
- Landed in Quentin:
  - `verify_system.py`
- Added intelligence process gate:
  - reads `strategy_regression.strategy_switching` from intelligence audit
  - fails verification when `strategy_switch_effectiveness` is below threshold
  - fails verification when risky plans have no planning diagnostics
- Env:
  - `QUENTIN_VERIFY_INTELLIGENCE_AUDIT` (default `1`)
  - `QUENTIN_VERIFY_STRATEGY_SWITCH_MIN` (default `0.55`)

### reset gap closure
- Landed in Quentin:
  - `quentin/cognitive/loop_orchestration.py`
  - `quentin/cognitive/loop_planner.py`
- Behavior:
  - consecutive failures beyond threshold trigger planning reset:
    - clear `last_plan_result`
    - inject critical reset instruction ("forget previous failing decomposition, restart from Goal")
  - reset instruction now enters planner prompt/hints (previously this signal existed but was not injected)
- Env:
  - `QUENTIN_PLANNER_RESET_FAILURE_THRESHOLD` (default `3`)

### XML integrity gap closure (incremental)
- Landed in Quentin:
  - `quentin/cognitive/xml_integrity.py`
  - integration in `quentin/cognitive/attempt_response_parser.py`
  - integration in `quentin/cognitive/loop_planner.py`
- Behavior:
  - repairs unclosed `<think>/<final>/<answer>` tags on truncated outputs
  - parser and planner now prefer repaired `<final>` content before JSON extraction
  - reduces chain breakage from token-truncated XML wrappers

### attempt interrupt state machine + resilience gate
- Landed in Quentin:
  - `quentin/cognitive/loop_orchestration.py`
  - `quentin/diagnostics/intelligence_auditor.py`
  - `verify_system.py`
- Behavior:
  - configurable interrupt state machine: `warn -> interrupt -> hard_reset`
  - unified handling for repeated tool-call loop and model repetition signals
  - interrupt cooldown is adaptive by failure subtype/origin/repetition intensity, then enforced as bounded diagnostic-first attempts
  - process audit now gates on:
    - `interrupt_effectiveness`
    - `reset_recovery_rate`
    - `progress_sync_compliance`
    - `attempt_band_coverage`
- Env:
  - `QUENTIN_ATTEMPT_INTERRUPT_ENABLED`
  - `QUENTIN_ATTEMPT_INTERRUPT_REPEAT_THRESHOLD`
  - `QUENTIN_ATTEMPT_INTERRUPT_TOOL_LOOP_THRESHOLD`
  - `QUENTIN_ATTEMPT_INTERRUPT_COOLDOWN`
  - `QUENTIN_ATTEMPT_INTERRUPT_HARD_RESET_COOLDOWN`
  - `QUENTIN_ATTEMPT_INTERRUPT_COOLDOWN_MAX`
  - `QUENTIN_ATTEMPT_INTERRUPT_HARD_RESET_COOLDOWN_MAX`
  - `QUENTIN_VERIFY_INTERRUPT_EFFECTIVENESS_MIN`
  - `QUENTIN_VERIFY_RESET_RECOVERY_MIN`
  - `QUENTIN_VERIFY_PROGRESS_SYNC_COMPLIANCE_MIN`
  - `QUENTIN_VERIFY_ATTEMPT_BAND_COVERAGE_MIN`

### payload escalation / params / images / directive authz increments
- Attempt-indexed payload escalation:
  - `quentin/cognitive/planning_payload_matrix.py`
  - `quentin/cognitive/planning_payload_variants.py`
- Provider/model-aware param profile + failure-history downshift:
  - `quentin/infra/llm/parameter_scaler.py`
- Adaptive vision budgeting (task class + entropy aware):
  - `quentin/cognitive/vision_budget.py`
  - now includes feedback-closed adaptation from historical outcome signals
- Directive authz guard (role/session-aware):
  - `quentin/cognitive/input_preprocessor.py`
  - `quentin/cognitive/loop_entrypoints.py`
  - now covers `/thinking`, `/model`, `/tool` directives with env allowlists + authz policy

### planning benchmark + trend report
- Landed in Quentin:
  - `scripts/planning_process_benchmark.py`
  - `tests/integration/test_planning_process_benchmark.py`
- Behavior:
  - converts intelligence-audit process metrics into weighted `quality_score`
  - compares against previous report and emits trend fields (`improved_vs_previous`, `previous_score`)
  - appends benchmark history (`planning_process_benchmark_history.jsonl`) for longitudinal trend analysis
  - used by autoloop benchmark step via `benchmark_command`
  - verify gate can optionally auto-calibrate thresholds from benchmark history percentiles (`QUENTIN_VERIFY_AUTOCALIBRATE_FROM_HISTORY`)
  - calibration supports domain buckets (`global` + custom labels) with fallback to global when bucket sample is insufficient
  - threshold recommendation generator available:
    - `scripts/planning_threshold_recommendation.py`
    - outputs per-bucket suggested verify thresholds from history
  - `.env` patch artifact generator available:
    - `scripts/planning_threshold_env_patch.py`
    - converts recommendation report into reviewable threshold env patch
  - autoloop benchmark stage now chains:
    - benchmark report -> threshold recommendation -> env patch artifact
    - enabled/disabled by env switches:
      - `QUENTIN_THRESHOLD_RECOMMENDATION_ENABLED`
      - `QUENTIN_THRESHOLD_ENV_PATCH_ENABLED`
  - CI governance gate added:
    - workflow: `.github/workflows/planning-threshold-gate.yml`
    - script: `scripts/planning_threshold_ci_gate.py`
    - approval override file: `config/planning_threshold_gate_approval.json`
    - behavior: drift above `QUENTIN_THRESHOLD_GATE_MAX_DELTA` requires explicit approval artifact

### vision feedback closed loop
- Landed in Quentin:
  - `quentin/cognitive/vision_budget.py`
  - feedback write integration in `quentin/cognitive/loop_orchestration.py`
  - observability summary in `quentin/observability/service.py`
- Behavior:
  - records per-attempt vision budget + outcome score
  - blends heuristic outcome with judge/confidence signal into effective score (`QUENTIN_VISION_BUDGET_JUDGE_WEIGHT`)
  - uses historical domain/task-class outcomes to adapt ratio allocations
  - exports feedback aggregates in intelligence observability metrics

### benchmark long-tail replay expansion
- Landed in Quentin:
  - `tests/integration/test_planning_process_benchmark_longtail.py`
- Behavior:
  - 20 long-tail archetypes across shell/browser/filesystem/model/system failures
  - validates regression sensitivity by injecting degraded traces and asserting score drop

### autoloop recovery integration
- Landed in Quentin:
  - `scripts/brain_autoloop.py`
- Behavior:
  - parses verify output process issues for strategy-switch gate failures
  - loads intelligence audit `strategy_switching.examples`
  - infers current recovery focus (`tool_family`, `error_subcategory`)
  - injects subtype-specific recovery instructions into analyzer/fixer prompts
- Goal:
  - avoid generic retries; force planning-layer, subtype-aware recovery actions.

### `attempt.ts` (`evaluateResult`, weighted retries)
- Landed in Quentin:
  - `quentin/cognitive/attempt_evaluator.py`
  - `quentin/cognitive/attempt_budget.py`
  - `quentin/cognitive/loop_goal_flow.py`
- Behavior:
  - failure category + severity + origin classification
  - weighted retry budget consumption (not equal retries)
  - timeout/system errors consume higher retry cost

### planning retry strategy patches (category-driven)
- Landed in Quentin:
  - `quentin/cognitive/planning_strategy_patch.py`
  - integration in `quentin/cognitive/loop_runtime_helpers.py`
  - integration in `quentin/cognitive/loop_planner.py`
  - enforcement in `quentin/cognitive/loop_plan_guards.py`
- Behavior:
  - category-driven patches:
    - `environment_timeout_error`
    - `tool_execution_error`
    - `model_syntax_error`
    - `logic_path_error`
    - `mixed`
    - `system_error`
  - each patch defines:
    - directives
    - required prechecks
    - avoid-actions
    - planner prompt patch block
  - fallback patch for retry/stuck stage when category unknown

### retry delta serialization (previous vs current plan)
- Landed in Quentin:
  - `quentin/cognitive/planning_retry_delta.py`
  - integration in `quentin/cognitive/loop_runtime_helpers.py`
  - prompt injection in `quentin/cognitive/loop_planner.py`
  - trace payload in `quentin/cognitive/loop_orchestration.py`
- Behavior:
  - for retry attempts, emits structured delta payload with:
    - previous step count
    - dropped/reworked step ids
    - previous error + category
  - injects retry delta patch into planning prompt to enforce strategy change

### deterministic inline action bypass (command-like tools)
- Landed in Quentin:
  - parser+executor: `quentin/cognitive/input_preprocessor.py`
  - entry integration: `quentin/cognitive/loop_entrypoints.py`
- Behavior:
  - parse `/tool <tool_name> <json_args>` before planner/LLM
  - apply allowlist for tools/shell commands
  - execute deterministically when safe
  - fallback to planner path on block/error

### attempt guardrails (`attempt.ts` parity increment)
- Landed in Quentin:
  - `quentin/cognitive/attempt_response_parser.py`
  - integration in `quentin/cognitive/loop_executor.py`
  - repetition classification hook in `quentin/cognitive/attempt_evaluator.py`
- Behavior:
  - parse `<think>` and `<final>` blocks from model output
  - force `final_output` from `<final>` when present
  - detect repetition loops and inject guard signal for replanning

### params/images parity increments
- Params:
  - `quentin/infra/llm/parameter_scaler.py`
  - token-usage hedge wired from `quentin/cognitive/loop_goal_flow.py`
- Images:
  - `quentin/cognitive/vision_budget.py`
  - budget injection in `quentin/cognitive/loop_entrypoints.py`

## Environment Controls (Hot-pluggable + Fallback)
- `QUENTIN_PLANNER_PAYLOAD_MATRIX_ENABLED`
- `QUENTIN_PLANNER_PAYLOAD_VARIANTS_ENABLED`
- `QUENTIN_PLANNER_RETRY_THRESHOLD`
- `QUENTIN_PLANNER_STUCK_THRESHOLD`
- `QUENTIN_PLANNER_FORCE_SPECULATIVE_ON_STUCK`
- `QUENTIN_ATTEMPT_BUDGET`
- `QUENTIN_MAX_LOOPS`
- `QUENTIN_REFLECTION_FAILURE_THRESHOLD`
- `QUENTIN_PLANNER_STRATEGY_PATCH_ENABLED`
- `QUENTIN_PLANNER_STRATEGY_PATCH_TARGETS`
- `QUENTIN_PLANNER_STRATEGY_PATCH_FALLBACK_ENABLED`
- `QUENTIN_INPUT_DIRECTIVE_ALLOWLIST`
- `QUENTIN_INPUT_DIRECTIVE_PERSIST`
- `QUENTIN_INPUT_INLINE_ACTIONS_ENABLED`
- `QUENTIN_INPUT_INLINE_ACTION_TOOL_ALLOWLIST`
- `QUENTIN_INPUT_INLINE_ACTION_SHELL_ALLOWLIST`
- `QUENTIN_PARAM_SCALER_TOKEN_HEDGE_ENABLED`
- `QUENTIN_PARAM_SCALER_CONTEXT_WINDOW`
- `QUENTIN_PARAM_SCALER_HIGH_WATERMARK`
- `QUENTIN_VISION_BUDGET_ENABLED`
- `QUENTIN_VISION_BUDGET_TOTAL_TOKENS`
- `QUENTIN_VISION_BUDGET_TOTAL_TOKENS_MOBILE`
- `QUENTIN_VISION_BUDGET_TOTAL_TOKENS_WEB`
- `QUENTIN_VISION_BUDGET_TOTAL_TOKENS_DESKTOP`
- `QUENTIN_VISION_BUDGET_SCREENSHOT_RATIO`
- `QUENTIN_VISION_BUDGET_UI_TREE_RATIO`
- `QUENTIN_CODING_TOOL_PRIMARY`
- `QUENTIN_CODING_TOOL_FALLBACKS`

## Provider/Tool Plug-in Direction
- Current primary coding tool is env-driven (`QUENTIN_CODING_TOOL_PRIMARY`), default `gemini.code`.
- Fallback chain is env-driven (`QUENTIN_CODING_TOOL_FALLBACKS`), so future switch to `claude.code`/`codex` does not require planner code changes.
- Strategy patches and lifecycle matrix are tool/provider agnostic and only use normalized failure categories.

## Gap Assessment & Landing TODO
- Detailed quantified gap analysis and phased implementation checklist:
  - `docs/improve/openclaw_planning_gap_todo.md`

## Next Increment (Per-file style)
- Continue file-by-file parity for remaining OpenClaw planning components:
  - directive authorization policy with role/session-aware guards
  - inline action deterministic execution path (when command-like tools are fully unambiguous)
  - richer semantic delta scoring (plan-shape similarity + loop breaker signal)
