# TODO: Plugin Runtime Isolation (Skills/Tools)

Date: 2026-02-11
Scope: `quentin/tools/plugin_loader.py`, `quentin/skills/exec_plugin_loader.py`, `tests/*`

Problem:
- Python plugin loading can pollute module namespace (import caching).
- Skills/tools plugins may interfere with each other if they share global state.
- Capability gating should prevent plugins from silently escalating to unsafe operations.

Goal:
- Provide isolation mechanisms:
  - module namespace isolation (unique module names per plugin instance)
  - per-plugin capability declaration (manifest permissions)
  - optional sandboxed execution context (limited builtins) for pure-python plugins

Non-goals:
- Do not attempt OS-level sandboxing in Python in this block.

Design (proposal):
- Each plugin manifest includes:
  - `permissions: [fs_read, fs_write, shell_safe, network_none, ...]`
  - `requires_env: [...]`
- Loader enforces:
  - permissions are checked against `SafetyKernel` policies
  - disabled if requirements missing
- Feature flag:
  - `QUENTIN_PLUGIN_RUNTIME_ISOLATION=1`

Implementation Steps:
- [x] Update plugin schema to include permissions + required env.
- [x] Update tool/skill plugin loaders to:
  - [x] validate manifest requirements (`requires_env`) and implement runtime gating.
  - [x] attach permissions metadata to `ToolSpec`.
- [x] Tests:
  - [x] `tests/manual/test_plugin_isolation_smoke.py`.

Acceptance Criteria:
- Two plugins with same internal module names do not conflict.
- Plugin permissions show up in traces and can be denied deterministically.

Rollback:
- `QUENTIN_PLUGIN_RUNTIME_ISOLATION=0` (legacy import behavior).

