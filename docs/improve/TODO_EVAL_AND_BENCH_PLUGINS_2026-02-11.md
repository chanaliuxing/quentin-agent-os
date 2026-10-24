# TODO: Eval + Bench Plugins

Date: 2026-02-11
Scope: `meta_agent/self_programming/evaluator.py`, `quentin/observability/*`, `scripts/*`, `tests/*`

Problem:
- Evaluation harnesses and benches are currently extended by editing core code.
- Blueprint wants consistent evidence generation; new evaluators should be pluggable.

Goal:
- Introduce `EvaluatorPlugin` registry:
  - add a new evaluator without modifying core harness
- Provide a plugin discovery pattern similar to tool/skill plugins (manifest + logic).

Non-goals:
- Do not change existing evaluator scoring semantics.

Design (proposal):
- `EvaluatorPlugin`:
  - `id`, `target_type`, `run(repo_root, config) -> EvalResult`
- Config:
  - `QUENTIN_EVAL_PLUGINS_ENABLED=1`

Implementation Steps:
- [x] Add `quentin/self_programming/eval_plugins/` with base + registry.
- [x] Migrate `SkillPatchEvaluator` logic as an example plugin.
- [x] Integrate plugin running in `PatchEvaluator.evaluate`.
- [x] Tests:
  - [x] `tests/manual/test_eval_plugins_smoke.py`.

Acceptance Criteria:
- New evaluator can be added as a plugin directory.
- Harness can list and run evaluator plugins deterministically.

Rollback:
- `QUENTIN_EVAL_PLUGINS_ENABLED=0`.

