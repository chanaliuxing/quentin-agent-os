# Blueprint v3 (`blueprint.md`) vs Codebase Audit

Date: 2026-02-07

Purpose:
- Compare `blueprint.md` v3 narrative requirements against the current repository implementation.
- Record “what is landed” vs “what is still research/placeholder”.
- Produce a concrete, verifiable TODO list (kept in `docs/TODO_BLUEPRINT_V3_CHECKLIST.md`).

Notes:
- This audit treats “landed” as: has a stable module location + can run offline + has trace/experiment evidence hooks.
- Some components are intentionally conservative: external providers require env keys, and offline defaults are used for CI.

## Section 1: Architecture (L0-L3) + Runtime Resilience

Blueprint says L0/L1 must provide: Lanes, Abort, Session write lock, Context budget/Compaction, AuthProfiles/Failover, Tool governance.

Current code landing points (all exist):
- Lanes: `quentin/infra/concurrency/lanes.py`
- Abort/Cancellation: `quentin/infra/concurrency/cancellation.py`, `quentin/infra/subprocess_utils.py`
- Session write lock: `quentin/runtime/session_write_lock.py`
- Context budget/Compaction: `quentin/llm/context_budget.py`, `quentin/llm/compaction.py`
- AuthProfiles/Failover: `quentin/llm/auth_profiles.py`, `quentin/llm/provider_failover.py`, `quentin/llm/failover.py`, `quentin/llm/client.py`
- Tool governance (policy + hooks + schema transformer): `quentin/tools/manager.py`, `quentin/tools/schema_transformer.py`
- SafetyKernel guard + auditing: `quentin/kernel/safety.py`, `quentin/kernel/policy.py`, `quentin/kernel/budget.py`

Residual gaps:
- “Runtime emits evidence by itself” is partial: we keep deterministic evidence emission for CI (`qctl blueprint-scan --emit-evidence`) and only add real runtime traces where they are low-risk.

## Section 2: Memory Fabric (Continual Memory)

Landed:
- STS/MTS/LTS tiers + record schema: `quentin/memory/models.py`
- Remember/recall with hybrid recall support: `quentin/memory/fabric.py`
- Optional local vector backend: `quentin/memory/store_sqlite_vec.py`
- Embedding fallback + health snapshot: `quentin/infra/llm/embeddings.py`
- Safe forgetting + consolidation hooks: `quentin/memory/*`, `quentin/sleep/*`
- Promotion “apply to runtime defaults” (offline): `quentin/memory/recall_defaults.py`, `quentin/memory/fabric.py`

Residual gaps (research-grade):
- Large-scale index swap/reindex workflows beyond sqlite-vec (Postgres CONCURRENTLY, etc.) are not fully production-hardened.

## Section 3: Core Loops (Cognitive / Immune / Sleep / Skill Evolution)

Landed (canonical runtime is runnable offline):
- Cognitive loop: `quentin/runtime/cognitive_loop.py` (and core loop impl exists at `quentin/cognitive/loop_impl.py`)
- Immune loop: `quentin/loops/immune_loop.py`
- Sleep loop: `quentin/loops/sleep_loop.py`
- Skill evolution: `quentin/skills/evolution.py`, `scripts/run_skill_evolution.py`

Residual gaps:
- Some loop implementations exist in multiple historical locations; canonical routing is documented in `docs/TODO_BLUEPRINT_V3_CHECKLIST.md`.

## Section 4: Self-Programming (Verifiable)

Landed (offline + deterministic mode supported):
- Engine v2: `meta_agent/self_programming/engine_v2.py`
- Deterministic coder backend: `meta_agent/tools/coder/deterministic_backend.py`
- PatchFlow minimal pipeline: `meta_agent/patchflow/orchestrator.py`
- Governance hooks + trace evidence: `meta_agent/self_programming/*`

Residual gaps:
- Stronger “real-world canary” integration exists as hooks/config, but still requires environment-specific wiring.

## Section 5: Multi-Agent & Data-Driven Routing

Landed:
- CouncilManager (multi-role council driven by ModelRouter): `quentin/council/manager.py`
- MultiAICouncil (simple committee mode) supports offline `stub` provider: `quentin/llm/multi_council.py`, `quentin/llm/types.py`
- ModelRouter with rules + logging: `quentin/routing/model_router.py`, `quentin/router/metrics.py`

Residual gaps:
- “Bandit/RL data-driven routing” exists as building blocks but is not fully wired into routing decisions for production.

## Section 7: Research-Friendly + Visualization

Landed:
- ResearchInterfaceV3 + ExperimentOrchestrator: `quentin/l3/research/interface.py`, `quentin/l3/research/experiment_orchestrator.py`
- Offline eval harness with built-in evaluators: `quentin/l3/research/eval_harness.py`
- Observability overview: `quentin/observability/service.py`

Residual gaps:
- A unified interactive dashboard (beyond JSON overview) is still optional / partial (depends on how you want to deploy UI).

