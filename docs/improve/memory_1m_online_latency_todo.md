# 1M Online Latency Closure TODO (Intelligence-Preserving)

## Goal
- Primary: keep intelligence quality stable at 1M (`task_success`, `first_hit`, `recurrence`, `pollution`).
- Constraint: bring hybrid online latency from 20s+ class to sub-second/low-second class tiered targets.

## Baseline (Observed)
- [x] Record isolated 1M result (quality strong, latency SLO fail).
- [x] Confirm 30k/100k isolated runs pass latency + quality.
- [x] Confirm concurrency contamination risk and add benchmark lock.

## P0 - Query Path Optimization
- [x] Add hybrid fast path: vector-seeded candidate pool + lexical rerank (avoid full-table text scan by default).
- [x] Add guarded fallback to full text retrieval only when seeded lexical confidence is low.
- [x] Add knobs for seed size / fallback threshold / fallback enable.
- [x] Add observability fields to recall debug payload (`hybrid_fast_path_used`, `seed_candidates`, `fallback_used`).

## P1 - Text Retrieval Efficiency
- [x] Prefer FTS in online hybrid/text-only path when available.
- [x] Keep LIKE path as compatibility fallback.
- [x] Add startup/health warning when running large corpus without FTS/indexed text path.

## P1 - Write-Path Cost Control
- [x] Gate access-count write amplification (batch/deferred updates for hot queries).
- [x] Add env knob to disable per-hit writeback in benchmark mode.

## P2 - Tiered Serving Strategy
- [x] Define online/offline tier policy: 1M offline-grade by default, online uses bounded active window.
- [x] Add optional active-window prefilter for hybrid online path.

## Testing
- [x] Unit tests for hybrid fast path correctness and fallback behavior.
- [x] Integration benchmark at 100k (hybrid) to verify latency reduction without quality loss.
- [x] Integration smoke for 1M with low-case run to verify no quality regression.

## Acceptance
- [x] 100k hybrid: quality stable and p95 materially reduced vs baseline.
- [x] 1M hybrid: quality stable and p95 improved enough to justify next optimization stage.
- [x] Updated docs/gap log with measured deltas and rollout guidance.
