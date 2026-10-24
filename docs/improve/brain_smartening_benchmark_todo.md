# Brain Smartening Benchmark TODO

Updated: 2026-02-21

Goal:
- Use benchmark as a behavior diagnosis tool to make the brain smarter across modules.
- Prioritize real capability gains over score chasing.

## A. Perception Consistency

- [x] A1. Ensure sensing evidence index can resolve nested/legacy shapes robustly.
- [x] A2. Add explicit audit metric for sensing evidence coverage (`evidence_found / evidence_expected`).
- [x] A3. Add issue rule when evidence coverage is low and risky actions exist.
- [x] A4. Add unit tests for nested sensing report parsing and coverage metrics.

## B. Planning-Execution Consistency

- [x] B1. Add strategy consistency metric based on planning diagnostics completeness:
  - payload variant presence
  - strategy patch presence
  - retry delta presence
- [x] B2. Add issue rule when strategy diagnostics exist but remain mostly generic/legacy inferred.
- [x] B3. Add unit tests for consistency metric and issue triggering.

## C. Dynamic Correction Ability

- [x] C1. Add dynamic correction proxy metric:
  - interrupt effectiveness
  - reset recovery
  - cooldown recurrence
  - progress sync compliance
- [x] C2. Add issue rule for repeated loop risk under high recurrence.
- [x] C3. Add unit tests for recurrence-driven issue detection.

## D. Protocol Robustness

- [x] D1. Add protocol robustness metric from audit traces:
  - parse failure count
  - format salvage count
  - protocol fallback count
- [x] D2. Add issue rule when protocol failure rate exceeds threshold.
- [x] D3. Add unit tests for protocol robustness extraction.

## E. Process Gate Quality

- [x] E1. Extend benchmark issue report with severity, suggested fix, and sample evidence.
- [x] E2. Keep strict mode available, but relax only for legacy data with explicit reason.
- [x] E3. Add tests for strict/legacy threshold path.

## F. Capability Radar Output

- [x] F1. Output capability radar section in benchmark report:
  - perception_consistency
  - planning_consistency
  - dynamic_correction
  - protocol_robustness
  - process_completeness
- [x] F2. Add prioritized top weaknesses list (`top_weaknesses`).
- [x] F3. Add tests to verify radar fields are present and stable.

## Done Criteria

- [x] D0. Related unit/integration tests pass.
- [x] D1. Local benchmark on current traces runs successfully.
- [x] D2. Benchmark report includes actionable weaknesses with no ambiguous failures.

## G. Phase 2: Planning Consistency Intelligence

- [x] G1. Normalize legacy tool aliases (`ls`, `mkdir`, `cat`, `find`) into tool families to avoid false mismatch penalties.
- [x] G2. Upgrade plan-vs-execution matcher:
  - explicit tool id matching (exact)
  - family-level compatibility matching (coarse)
  - blended consistency score (family + exact when samples exist)
- [x] G3. Expose exact-match metrics in strategy switching diagnostics.
- [x] G4. Add issue rule for exact tool alignment degradation (only when sample size is sufficient).
- [x] G5. Add/adjust unit tests for alias normalization, exact-match metrics, and new issue rule.
- [x] G6. Re-run benchmark and verify weakest capability signal is now less noisy/more actionable.

## H. Phase 3: Plan-Tool Alignment Enforcement

- [x] H1. Add executor-side explicit tool alignment guard for step descriptions (env-controlled).
- [x] H2. Add auto-rewrite path for common misalignment (`shell.run_command cat` -> `fs.read_file`) with fallback policy.
- [x] H3. Add hard-constraint + staged fallback controls:
  - `QUENTIN_PLAN_TOOL_ALIGNMENT_HARD_BLOCK`
  - `QUENTIN_PLAN_TOOL_ALIGNMENT_ALLOW_FALLBACK`
  - `QUENTIN_PLAN_TOOL_ALIGNMENT_FALLBACK_AFTER_ITER`
- [x] H4. Extend error subtype classification to detect `plan_execution_misalignment` from execution feedback.
- [x] H5. Inject misalignment overlays into planning strategy patch / payload variant.
- [x] H6. Strengthen planner prompt instruction: explicit tool names in plan steps must stay executable-aligned.
- [x] H7. Add unit tests for alignment rewrite/block logic and new subtype/patch variant behavior.
- [x] H8. Promote `plan_execution_misalignment` to first-class attempt category with stronger retry cost and earlier stuck-mode escalation.
- [x] H9. Emit plan-tool alignment signals as unified trace events and expose them in benchmark dimension components.

## I. Phase 4: Structured Plan Intent & Pre-Alignment

- [x] I1. Planner emits per-step `tool_intent` (`expected_tool`, `allowed_fallback_families`, `why`).
- [x] I2. Planner prompt/schema requires explicit tool intent and verification note per step.
- [x] I3. Executor consumes `tool_intent` and enforces alignment before execution paths (fast-path/protocol/native/json).
- [x] I4. Alignment compatibility supports configured fallback families from plan intent.
- [x] I5. Add unit tests for tool intent normalization and alignment fallback behavior.

## J. Phase 5: Process Intelligence Metrics & Plan Lint

- [x] J1. Add plan-publish lint normalization in plan guards:
  - normalize/enforce `tool_intent` for each step
  - inject verify-condition note for verification steps
- [x] J2. Add recovery-efficiency metrics in intelligence audit:
  - `misalignment_eval_total`
  - `misalignment_recovered_within_2(_rate)`
  - `misalignment_recurred_within_2(_rate)`
- [x] J3. Wire efficiency metrics into benchmark dimension components and scoring inputs.
- [x] J4. Add benchmark issue rules for poor misalignment recovery / high recurrence.
- [x] J5. Add unit tests for lint + recovery metrics + benchmark issue triggers.

## K. Phase 6: Exact Alignment Uplift (From Live Benchmark)

- [x] K1. Expand exact-tool matcher alias table for real traces:
  - add legacy ids observed in traces
  - add cross-runtime aliases (`shell.run_command` read/list/write intents)
- [x] K2. Add benchmark issue for missing alignment trace telemetry when planning samples are sufficient.
- [x] K3. Add replay fixture to validate exact-alignment scoring against realistic mixed traces.
- [x] K4. Raise `plan_execution_exact_match_rate` baseline from ~0.24 to >= 0.30 on local benchmark traces.
- [x] K5. Re-run benchmark + regression tests and lock report snapshot in `generated/benchmarks/`.

Phase 6 evidence snapshot:
- planning report: `generated/benchmarks/planning_process_benchmark_report_20260221_224322.json`
  - `plan_execution_exact_match_rate`: `0.4878`
- planning report (latest local): `generated/benchmarks/planning_process_benchmark_report_local.json`
  - `plan_execution_exact_match_rate`: `0.4667`
- L3 offline benchmark: `generated/benchmarks/brain_l3_20260221_224327_5a20b68d/report.json`
  - `pass_rate`: `1.0`
