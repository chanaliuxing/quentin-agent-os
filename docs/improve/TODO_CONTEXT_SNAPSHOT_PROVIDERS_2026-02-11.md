# TODO: Context Snapshot Providers (Environment Awareness Without GUI)

Date: 2026-02-11
Scope: `quentin/cognitive/prompt_layers.py`, `quentin/execution/skill_executor.py`, `quentin/runtime/*`, `tests/*`

Problem:
- The brain/executor often guesses file paths or tool availability.
- There is no systematic "what is in the workspace right now" snapshot injected into context.
- This causes hallucinated actions like `nano` or guessed download URLs, leading to try-loops.

Goal:
- Provide a modular set of "context snapshot providers" that produce small, bounded, text-only snapshots:
  - file tree (bounded depth)
  - git status summary (bounded)
  - tool inventory summary (from ToolManager)
  - recent errors / blocked actions summary
- Inject snapshots into prompts in a consistent, provider-aware way (dialect-friendly).

Non-goals:
- Do not index the whole repo by default (must be bounded and cheap).
- No UI rendering, no screenshots.

Design (proposal):
- `ContextSnapshotProvider`:
  - `id`, `priority`
  - `collect(repo_root, runtime_state) -> SnapshotBlock`
- `SnapshotBlock`:
  - `title`, `content`, `ttl_sec`, `size_bytes`, `meta`
- Feature flag:
  - `QUENTIN_CONTEXT_SNAPSHOT_PROVIDERS=1` enables snapshot injection.
  - Provide per-provider toggles for expensive snapshots (tree depth, max lines).

Implementation Steps:
- [x] Add `quentin/cognitive/context_snapshots/`:
  - [x] `base.py` + registry + size budget enforcement.
  - [x] `file_tree.py` (bounded `rg --files` / os.walk with depth).
  - [x] `git_status.py` (short porcelain summary; only if git).
  - [x] `tool_inventory.py` (ToolManager specs summary map).
- [x] Wire into prompt building:
  - [x] `quentin/execution/skill_executor.py` should assemble snapshot blocks into a single "Runtime Snapshot" section.
- [x] Tests:
  - [x] `tests/unit/test_context_snapshot_budgeting.py`.
  - [x] `tests/unit/test_file_tree_snapshot_bounds.py`.
  - [x] `tests/integration/test_prompt_contains_runtime_snapshot.py` (env-gated).

Acceptance Criteria:
- Executor is less likely to hallucinate paths/tools in cold start.
- Snapshot content is bounded by bytes/lines and respects TTL.

Rollback:
- `QUENTIN_CONTEXT_SNAPSHOT_PROVIDERS=0` disables snapshot injection.
