# TODO: Modular Tool Packs (Builtin Tools as Pluggable Packs)

Date: 2026-02-11
Scope: `quentin/bootstrap/container.py`, `quentin/tools/*`, `tests/*`

Problem:
- Builtin tool registration is currently hardcoded in `quentin/bootstrap/container.py`.
- Adding/removing builtin tools requires editing Container code and risks merge conflicts.
- Tool registration is conceptually a "pack" (filesystem, shell, memory helpers, MCP, plugins) but is not modeled.

Goal:
- Introduce a `ToolPack` interface and a pack registry.
- Convert builtin tool registrations into packs (filesystem pack, shell pack, interactive shell pack, aliases pack, etc).
- Keep `extensions/tools/*` plugin loader as-is; packs are for builtin wiring.

Non-goals:
- Do not change ToolManager semantics or safety kernel behavior.

Design (proposal):
- `ToolPack` interface:
  - `id: str`
  - `register(tool_manager, *, repo_root, container) -> None`
  - optional `enabled(container/settings/env) -> bool`
- `ToolPackRegistry`:
  - ordered by priority
  - registers packs and runs them at container bootstrap
- Feature flag:
  - `QUENTIN_TOOL_PACKS_ENABLED=1` to enable pack bootstrap.
  - when disabled, use current hardcoded registration.

Implementation Steps:
- [x] Add `quentin/tools/packs/base.py` for `ToolPack` + registry.
- [x] Add builtin packs:
  - [x] `quentin/tools/packs/filesystem_pack.py`
  - [x] `quentin/tools/packs/shell_pack.py`
  - [x] `quentin/tools/packs/interactive_shell_pack.py` (kept always-registered; tool enforces runtime gating)
  - [x] `quentin/tools/packs/plugins_pack.py` (calls `register_tool_plugins`)
  - [x] `quentin/tools/packs/mcp_pack.py` (config gated)
  - [x] `quentin/tools/packs/usage_sinks_pack.py` (ToolKnowledgeUsageSink)
- [x] Update `quentin/bootstrap/container.py`:
  - [x] In `tool_manager` factory: if packs enabled, call registry to register all packs.
  - [x] Preserve current registration path as fallback.
- [x] Tests:
  - [x] `tests/unit/test_tool_packs_registry.py` (order, enable rules).
  - [x] `tests/unit/test_container_tool_packs_smoke.py` (container starts, key tools registered).

Acceptance Criteria:
- Container tool wiring is declarative (packs) and does not require editing Container for new builtin tool sets.
- Pack enable/disable does not break existing tools.

Rollback:
- `QUENTIN_TOOL_PACKS_ENABLED=0` reverts to hardcoded wiring.
