# Planning Tier-1 Gap Closure TODO

Updated: 2026-02-22

Goal:
- Make planning intelligence robust across new repos and noisy runtime traces.
- Prioritize real capability gains (generalization, recovery, observability) over score-only optimization.

## L. Runtime Evidence Reliability

- [x] L1. Add execution evidence quality metrics in intelligence audit:
  - `plan_execution_expected_steps`
  - `plan_execution_observed_coverage`
  - `plan_execution_call_tool_coverage`
- [x] L2. Add benchmark issue gate for low observed execution coverage under sufficient samples.
- [x] L3. Add unit tests for coverage metrics and issue trigger.

## M. Cross-Repo Generalization

- [x] M1. Build a small replay suite with mixed repositories/tasks (file ops + shell + browser-like traces).
- [x] M2. Add domain-bucket breakdown dashboard fields in benchmark report for per-domain failures.
- [x] M3. Add failure clustering summary (`top mismatch patterns`) for faster corrective tuning.

## N. Online Adaptation Loop

- [x] N1. Add adaptive alias cache from recent successful tool calls (bounded, env-controlled).
- [x] N2. Add safety guardrails to prevent overfitting to one session (TTL + min support).
- [x] N3. Add benchmark A/B mode to compare static mapping vs adaptive mapping.

## O. Long-Horizon Planning Stability

- [x] O1. Add explicit "goal re-anchoring" signal metric after reset/replan.
- [x] O2. Add issue rule for repeated plan oscillation (`reset->same path->reset`).
- [x] O3. Add regression tests for 10+ attempt trajectories with recovery expectations.

## P. Protocol Resilience Under Truncation

- [x] P1. Add partial-response recovery metric (parse salvage success after truncation).
- [x] P2. Add parser fallback quality score (semantic completeness, not just parse success).
- [x] P3. Add fuzz tests for malformed tool payloads and mixed XML/JSON fragments.

## Exit Criteria

- [x] E1. No high-severity benchmark issues on representative multi-domain traces.
- [x] E2. Exact alignment >= target threshold across at least 3 domain buckets.
- [x] E3. Recovery metrics stable for two consecutive benchmark runs.

## Evidence Snapshot

- Multi-domain benchmark runs:
  - `generated/benchmarks/planning_tier1_maintenance_run1.json`
  - `generated/benchmarks/planning_tier1_research_run1.json`
  - `generated/benchmarks/planning_tier1_global_run1.json`
  - `generated/benchmarks/planning_tier1_maintenance_run2.json`
  - `generated/benchmarks/planning_tier1_research_run2.json`
  - `generated/benchmarks/planning_tier1_global_run2.json`
  - `generated/benchmarks/planning_tier1_maintenance_run4.json`
  - `generated/benchmarks/planning_tier1_research_run4.json`
  - `generated/benchmarks/planning_tier1_global_run4.json`
- Domain breakdown present with 3 buckets (`maintenance`, `research`, `global`) in run2 reports.
- Adaptive A/B snapshot (`planning_tier1_global_run2.json`):
  - `exact_match_rate_static`: `0.4667`
  - `exact_match_rate_adaptive`: `0.7333`
- Current run4 issues: `[]` (no warn/fail).
