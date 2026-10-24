# Blueprint Gap Analysis (v3): Codebase vs `blueprint.md`

Date: 2026-02-06  
Scope: Repository state at analysis time (local workspace)  
Blueprint reference: `blueprint.md` (《Meta-Agent 工程落地蓝皮书 v3》)

This document validates and corrects the earlier Gemini gap analysis, then provides a final, code-evidenced gap analysis against `blueprint.md`.

## 2026-02-06 refresh (post P0/P1.4A implementation)

- Layer alignment snapshot (engineering estimate):
  - L0: ~90% (lanes/abort/session lock/context budget and core safety gates are on main path).
  - L1: ~85% (hybrid memory recall, tool policy stacking/hooks, embedding fallback are landed).
  - L2: ~70% (eval/self-improvement/immune are connected, but release gating from research is still weak).
  - L3: ~55% (experiment APIs + shadow/canary placeholders exist; decision-to-promotion automation is incomplete).
- Remaining high-impact closure gaps:
  - Memory automation closure: `promotion_rule/decay_rule/consolidation_batch` scheduling + budgeted batch runner.
  - Patch release closure: self-programming result -> shadow/canary metrics -> rollback/freeze gate.
  - Research final-mile closure: A/B result -> promote decision -> online config rollout under `SafetyKernel` + domain policy.

## Status taxonomy (used throughout)

- **Implemented**: Feature exists and has a plausible “main path” integration.
- **Partial**: Core skeleton exists, but important blueprint requirements are missing.
- **Fragmented**: Multiple overlapping implementations exist; no single canonical pipeline is enforced.
- **Missing**: No meaningful implementation found in the repository.

## Corrections to the Gemini analysis (what was inaccurate or overstated)

1) **“Missing a SafetyKernel” is inaccurate**
- Evidence: `quentin/kernel/safety.py:SafetyKernel`, `quentin/kernel/policy.py:PolicyEngine`, `quentin/kernel/budget.py:BudgetController`, `quentin/kernel/path_guard.py:PathGuard`.
- True gap: the safety kernel is **not enforced end-to-end** (not “non-bypassable”), and rollback/audit/permission controls are not unified across all high-impact actions.

2) **“Knowledge Graph lacks multi-hop queries” is inaccurate**
- Evidence: `quentin/knowledge_graph/service.py:GraphService` has `get_neighbors(depth=...)`, `explain_link(max_depth=...)`, `export_subgraph(...)`.
- True gap: graph features frequently degrade to `NullGraphStore` (availability), and missing are research-grade UX pieces (visualization/export tooling, LLM-backed explanations aligned to agent traces, etc.).

3) **Tooling maturity improved, but not full production governance yet**
- Evidence: `quentin/tools/manager.py:ToolManager` now includes policy stacking, before-hooks, lifecycle flags, safety guard integration, and trace/audit hooks.
- True gap: rollout governance is still incomplete (domain hard gates, canary-aware disablement, and richer auto-remediation).

4) **Policy/Governance needs to be split by layer**
- L0 kernel policy is not a placeholder: `quentin/kernel/policy.py:PolicyEngine` is a working static-policy + council escalation + decision logging component.
- L3 research policy is lightweight/near-placeholder: `quentin/research/policy.py:PolicyAndGovernance`.

## Layer-by-layer gap analysis (L0–L3)

### L0 — Infra & Kernel

**Current state**
- **Implemented (core components exist)**:
  - Safety gating: `quentin/kernel/safety.py`
  - Constitutional policy: `quentin/kernel/policy.py`
  - Budget control: `quentin/kernel/budget.py`
  - Path allowlist guard: `quentin/kernel/path_guard.py`
  - Git sandbox mechanism (self-programming infra): `meta_agent/self_programming/infra/git_ops.py:GitSafetyLayer`
- **Implemented (storage primitives exist, but uneven maturity)**:
  - SQLite memory store: `quentin/memory/store_sqlite.py:SqliteMemoryStore`
  - KV store is SQLite-backed persistent storage: `quentin/infra/storage/kv_store.py:KVStore`

**Key gaps vs blueprint**
- **Non-bypassable SafetyKernel** (Partial)
  - Blueprint intent: “任何重要动作必须先经过安全内核（权限/限流/回滚/审计）”。
  - Repo reality: SafetyKernel exists, but there is no global enforcement that all LLM calls, tool calls, code patches, experiments, and deployments go through it.
- **Unified rollback semantics** (Partial)
  - GitSafetyLayer and ad-hoc `.bak` backups exist in some pipelines, but rollback is not unified across environments (sandbox/staging/prod) and not coupled to immune actions.
- **Auditability and environment separation** (Partial)
  - Some decision logs exist (policy decisions JSONL), but “system-wide, consistent audit trail” is incomplete.
- **KV/metrics persistence** (Implemented/Partial)
  - Persistent KV is landed; remaining work is schema normalization and retention/compaction policy across modules.

### L1 — Base Layer (Orchestrator / Planner / Executor / Memory / Tools / Critic / Router)

**Current state**
- **Implemented**:
  - Cognitive loop core pipeline exists: `quentin/cognitive/loop_impl.py:CognitiveLoop`
  - Basic ModelRouter exists with usage stats: `quentin/models/router.py:ModelRouter`
- **Partial**:
  - Planner & Critic still have placeholder fallback paths: `quentin/planning/echo_planner.py:EchoPlanner`, `quentin/critic/rule_based.py:RuleBasedCritic`
  - ToolManager has governance skeleton but not full production closure: `quentin/tools/manager.py:ToolManager`

**Key gaps vs blueprint**
- **Hierarchical planning** (Missing/Partial)
  - Blueprint requires hierarchical planner with long/short horizon plans and research-friendly swapping; current defaults do not meet it.
- **Executor/tool governance** (Partial)
  - There is an execution stack, but tool lifecycle, safety gating, and robust retries/degradation policies are not implemented at the blueprint level.
- **Task router/orchestrator canonical path** (Fragmented)
  - Multiple orchestrator implementations exist; integration path is unclear, risking “feature exists but not used”.

### L2 — Meta Layer (Metrics / Eval / Self-Improvement / Multi-Agent)

**Current state**
- **Implemented**:
  - Eval harness (async, persisted results): `quentin/research/eval_harness.py:EvalHarness`
  - Immune loop with anomaly detection and immune-case storage, research interface hook: `quentin/immune/loop.py:ImmuneLoop`
  - Blueprint scanning skeleton: `quentin/blueprint/capability_scanner.py:CapabilityScanner`
- **Partial**:
  - Multi-agent role scaffolding exists but role agents are currently placeholders (no real LLM calls): `quentin/agents/roles.py`
  - Self-improvement management exists but is fragmented: `quentin/self_improvement/manager.py` vs `quentin/meta/self_improvement.py` etc.

**Key gaps vs blueprint**
- **Deep multi-agent integration** (Partial)
  - Blueprint wants fixed roles + experimental composition with measurable outcomes; current implementation is mainly interface scaffolding.
- **Online evaluation / A/B / shadow / canary** (Partial/Missing)
  - Offline eval works; blueprint’s online/shadow/canary gates are not implemented as a unified mechanism.
- **Self-improvement manager as a canonical scheduler** (Fragmented)
  - Multiple managers/paths exist; unclear which one is the “system truth”.

### L3 — Research & Evolution Layer (Experiments / Evolution Strategy / Budget / Governance)

**Current state**
- **Implemented**:
  - Experiment orchestrator (async, runs variants through EvalHarness): `quentin/research/experiment_orchestrator.py:ExperimentOrchestrator`
  - Evolution strategy manager (heuristic scoring over tasks/gaps/stats): `quentin/research/evolution.py:EvolutionStrategyManager`
- **Partial**:
  - Research governance is very lightweight: `quentin/research/policy.py:PolicyAndGovernance`
  - Budget control exists but duplicated across layers: `quentin/research/budget.py` vs `quentin/kernel/budget.py`

**Key gaps vs blueprint**
- **Research-grade policy/governance** (Partial)
  - Needs hard constraints for domains (trading/legal), concurrency, budget gates, required reviews, etc., unified with L0 kernel.
- **Algorithmic evolution strategy** (Partial)
  - Blueprint mentions bandit/RL/learning-based optimization; current implementation is mostly rule-based scoring.
- **Experiment system fragmentation** (Fragmented)
  - Multiple `ExperimentOrchestrator` implementations exist (see “Cross-cutting issues”); this undermines reliability and research reproducibility.

## Memory Fabric gaps (Continual memory requirements)

**Implemented**
- Tiered memory + embedding injection + SQLite store: `quentin/memory/fabric.py`, `quentin/memory/models.py`, `quentin/memory/store_sqlite.py`.
- Intelligent consolidation loop (cluster → distill → dedup → MTS insert/merge → STS archive): `quentin/memory/sleep_loop.py`.
- KG hooks for memory relations: `quentin/memory/fabric.py` + `quentin/knowledge_graph/service.py`.

**Key gaps vs blueprint**
- **Explicit `update_policy` fields and enforceable rules** (Missing/Partial)
  - Blueprint requires promotion/decay/consolidation batch policies as first-class fields; current schema doesn’t expose them.
- **Procedural memory + training pairs output** (Partial/Missing)
  - Blueprint requires procedural skills and “failure→success / bad-plan→good-plan” training pairs; current sleep loop focuses on semantic consolidation.
- **Graph availability and export UX** (Partial)
  - Graph falls back to `NullGraphStore` if PG unavailable; missing visualization and research-friendly export pipelines.

## Evolution loops (Cognitive / Immune / Sleep / Skill & Code Evolution)

### Cognitive loop
- **Implemented (core pipeline)**: `quentin/cognitive/loop_impl.py`
- **Gaps**:
  - Planner/Critic maturity is insufficient (placeholders).
  - SafetyKernel “no-trace no-run / important actions gated” is not enforced globally.

### Immune loop
- **Implemented**: `quentin/immune/loop.py`, anomaly detection, immune cases, and research interface hook.
- **Gaps**:
  - Automated rollback/degrade is mostly advisory (`ImmuneAction`) rather than an executed runtime policy with environment rollback.

### Sleep loop
- **Implemented (memory consolidation)**: `quentin/memory/sleep_loop.py`
- **Gaps**:
  - Missing procedural memory output and training-pair datasets.
  - Scheduling/quotas are local to configs and not system-enforced across runtimes.

### Skill & code evolution loop
- **Implemented (candidate generation)**: `quentin/skills/miner.py:SkillMiner`, registry infrastructure under `quentin/skills/`.
- **Gaps (major)**:
  - The full pipeline “miner → candidate → tests → eval harness comparison → register/supersedes” is not reliably automated.
  - Pattern mining across multiple traces/tasks is underdeveloped (current approach is closer to “single successful run distillation”).

## Self-programming engine gaps (verifiable self-programming)

**What exists**
- Robust-ish engine with tests + lightweight static checks: `meta_agent/self_programming/engine_v2.py:SelfProgrammingEngineV2`.
- Additional self-programming implementations exist in `quentin/`:
  - `quentin/selfprog/engine.py:SelfProgrammingEngine` (SafetyKernel + patch gate council + writes `.bak`)
  - `quentin/self_programming/engine.py:SelfProgrammingEngine` (research+coder router based; also contains placeholder `BlueprintGap`)

**Key gaps vs blueprint**
- **Boundary enforcement** (Partial/Fragmented)
  - Blueprint requires “only `/mutable/` + `auto_updatable`”, forbid kernel/schema edits. Pieces exist (PathGuard, kernel policy), but enforcement is not guaranteed across all self-prog entry points.
- **Standardized Patch Report** (Partial)
  - Tests and some checks exist, but structured reporting (coverage, perf regression, risk diffs, metrics deltas) is not unified.
- **Blueprint-driven gap loop** (Partial)
  - Capability scanning exists, but end-to-end “read blueprint → derive actionable gaps → run self-prog → evaluate → govern → merge/deploy” is not a stable canonical pipeline.

## Model routing & multi-agent strategy gaps

**Implemented**
- Base model routing with usage stats: `quentin/models/router.py`
- Offline optimizer writes rules: `quentin/llm/router_optimize.py`
- Four blueprint roles are defined: `quentin/agents/roles.py`

**Key gaps**
- **Data-driven routing closure** (Partial)
  - Optimizer can write rules, but it’s unclear that the live router consumes learned policies in a consistent main path.
- **Real multi-agent deliberation integration** (Partial)
  - Role agents are placeholders; research A/B hooks exist but are not wired into the decision backbone.

## Observability & research APIs gaps

**Implemented**
- Observability service skeleton: `quentin/observability/service.py`
- Dashboard collector exists but has TODO/simplified collectors: `quentin/observability/dashboard.py`
- Eval results persisted to JSONL: `quentin/research/eval_harness.py`

**Key gaps**
- **“Must visualize” requirement** (Partial)
  - Current state is closer to “data exists”, but not a stable research dashboard with the blueprint’s required panels and exports.

## Cross-cutting engineering gaps (high impact)

### 1) Implementation fragmentation (multiple overlapping versions)

This is a practical blocker: even if features exist, the runtime may call a different (placeholder) implementation.

Examples (non-exhaustive):
- `SleepLoop`: `quentin/memory/sleep_loop.py`, `quentin/sleep/loop.py`, `quentin/loops/sleep_loop.py`, `quentin/runtime/sleep_loop.py`, `meta_agent/evolution/sleep_loop.py`, etc.
- `ExperimentOrchestrator`: `quentin/research/experiment_orchestrator.py`, `quentin/research/orchestrator.py`, `quentin/research/experiments.py`, `quentin/experiments/orchestrator.py`
- `EvalHarness`: `quentin/research/eval_harness.py`, `quentin/eval/harness.py`, `quentin/evaluation/harness.py`
- `CognitiveLoop`: `quentin/cognitive/loop.py`, `quentin/runtime/cognitive_loop.py`, `meta_agent/evolution/cognitive_loop.py`
- `ImmuneLoop`: multiple definitions across `quentin/immune/*`, `quentin/loops/*`, `quentin/runtime/*`, `meta_agent/evolution/*` (the legacy `quentin/core/*` directory is removed).

### 2) Durable stores and long-running operation

- `KVStore` is in-memory; long-running “research platform” needs persistence for metrics, experiments, council decisions, etc.

### 3) Domain coverage

- `quentin/domain` currently contains `desktop` only; blueprint also expects `legal` and `trading` domain integration patterns.

## Prioritized major gaps (recommended focus order)

1) **Make SafetyKernel non-bypassable** for all high-impact actions (LLM/tool/patch/experiment/deploy), with consistent auditing and rollback semantics.
2) **Choose and enforce canonical main paths** (reduce fragmentation) for Cognitive/Sleep/Research/Eval/Self-Programming, so “implemented” actually means “used”.
3) **Complete Skill & Code Evolution loop** end-to-end: candidate generation → tests → eval harness comparison → governance → promotion/supersedes.
4) **Strengthen L3 governance and experiment infrastructure**: unified create/run/compare/export and domain-sensitive gating (legal/trading).
5) **Close the data-driven model routing loop**: stats → optimizer → policy consumption → periodic re-optimization.
6) **Extend SleepLoop outputs** to procedural memories and training pairs, with budgeted scheduling and stable artifacts.
