# TODO: Self-Programming Backends (Runner/Applier/Store Adapters)

Date: 2026-02-11
Scope: `meta_agent/self_programming/*`, `meta_agent/patches/*`, `tests/*`

Problem:
- SelfProgrammingEngineV2 contains logic for:
  - coder backend selection
  - patch apply
  - test runner
  - artifact store
- Swapping one piece (e.g. test runner, git adapter, patch store) requires touching engine code.

Goal:
- Introduce backend adapters for self-programming:
  - `CoderBackend` (already partially exists via config; formalize)
  - `TestRunnerBackend`
  - `PatchStoreBackend`
  - `RepoAdapter` (git operations, diff, apply)
- Keep current behavior as default backend set.

Non-goals:
- Do not redesign the self-programming flow; only modularize components.

Design (proposal):
- `SelfProgBackendBundle`:
  - `coder`, `test_runner`, `patch_store`, `repo_adapter`
- Config:
  - `QUENTIN_SELFPROG_BACKEND=default` (or `no_tests`, `fast_unit_only`, etc)
- Trace:
  - emit `selfprog_backend_id`, per-component IDs.

Implementation Steps:
- [x] Add `meta_agent/self_programming/backends/`:
  - [x] `base.py` (protocols + bundle)
  - [x] `default.py` mapping to current implementations
- [x] Refactor `meta_agent/self_programming/engine_v2.py` to accept a bundle (default constructed).
- [x] Refactor `meta_agent/self_programming/test_runner.py` to be a backend implementation.
- [x] Tests:
  - [x] `tests/manual/test_selfprog_backend_mock.py`.

Acceptance Criteria:
- You can swap test runner strategy without editing engine code.
- Engine reports backend IDs in traces.

Rollback:
- `QUENTIN_SELFPROG_BACKEND=default` (or unset).

