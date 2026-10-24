# Time Consistency Policy (Quentin Brain)

> Date: 2026-02-10  
> Scope: Quentin brain runtime + self-programming + skills mainline.

## 1) Canonical Internal Time
- Internal canonical clock is **UTC**.
- Internal timestamps must be **timezone-aware ISO** (`+00:00`), not naive `datetime.utcnow().isoformat()`.

## 2) Input Time Normalization
- External input timestamps should be normalized via `normalize_to_utc_iso(...)`.
- If input has no timezone, treat it as UTC by default.
- If input has timezone offset (e.g. `-05:00`), convert to UTC before storage/comparison.

## 3) Output Time
- Default output uses UTC (`now_iso()` -> UTC).
- Local display is opt-in (`now_display_iso()` + `QUENTIN_LOG_LOCAL_TIME=1`).
- Avoid mixing UTC and local timestamps in the same payload unless both are explicitly labeled.

## 4) Current Status
- Core modules migrated to UTC-aware ISO:
  - `quentin/cognitive/loop_impl.py`
  - `quentin/execution/skill_executor.py`
  - `quentin/runtime/system_events.py`
  - `quentin/goals/schema.py`
  - `quentin/goals/manager.py`
  - `quentin/goals/done_definition.py`
  - `quentin/traces/execution_trace.py`
  - `quentin/router/metrics.py`
  - `quentin/utils/time.py`

- Mainline + side-chain modules migrated in this phase:
  - `quentin/runtime/cognitive_loop.py`
  - `quentin/runtime/immune_loop.py`
  - `quentin/runtime/loop_scheduler.py`
  - `quentin/orchestrator/daemon.py`
  - `quentin/orchestrator/models.py`
  - `quentin/self_programming/*` (mainline + legacy apply/models/engine)
  - `quentin/skills/*` (schema/registry/models/evolution/promotion/registrar)
  - `quentin/experiments/orchestrator.py`
  - `quentin/planning/memory_helpers.py`
  - `quentin/memory/consolidation.py`
  - `quentin/blueprint/*` selected runtime trackers
  - `quentin/evolution/*` selected runtime loops
  - `quentin/diagnostics/dashboard.py`
  - `quentin/l3/research/*` selected runtime evaluators

## 5) Remaining Sweep
- `quentin/` now has no remaining `datetime.utcnow()`/naive `datetime.now()` generation in business code (except local display helper in `quentin/utils/time.py` by design).
- `meta_agent/` main paths are now migrated away from naive `datetime.utcnow()/datetime.now().isoformat()` as well.
- Remaining direct `datetime.now(...)` in `meta_agent/` are timezone-aware (`timezone.utc`) and therefore internally consistent.
