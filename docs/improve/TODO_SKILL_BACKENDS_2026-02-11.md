# TODO: Skill Backends (Modular Skill Storage + Discovery)

Date: 2026-02-11
Scope: `quentin/skills/*`, `tests/*`, `docs/*`

Problem:
- Skills exist in multiple forms (registry python skills, markdown SOPs, exec skill plugins).
- There is no single "skill backend" abstraction for discovery + loading.
- Adding a new skill store (sqlite, remote, MCP) would require edits across multiple files.

Goal:
- Introduce a `SkillBackend` interface and a backend registry.
- Keep current implementations as backends:
  - Legacy python registry backend
  - Markdown SOP backend (lazy index)
  - Exec-skill plugins backend
- Provide a single "skill inventory" surface to the planner/executor.

Non-goals:
- Do not change existing skill execution semantics in Executor.
- Do not remove existing paths; only wrap them.

Design (proposal):
- `SkillBackend`:
  - `id`
  - `list_skills() -> List[SkillSpec]` (metadata only)
  - `load_exec_callable(skill_id) -> Callable|None`
  - `load_sop_text(skill_id) -> str|None`
- `SkillBackendRegistry`:
  - ordering and merging rules (prefer exec over sop over legacy, or explicit)
- Config:
  - `QUENTIN_SKILL_BACKEND=default` (or `legacy_only`, `markdown_only`, etc).

Implementation Steps:
- [x] Add `quentin/skills/backends/base.py` + registry.
- [x] Implement backends:
  - [x] `legacy_registry_backend.py`
  - [x] `filesystem_sop.py` (was `markdown_sop_backend.py`) - supports both structured and flat markdown.
  - [x] `exec_plugin.py` (was `exec_plugin_backend.py`)
- [x] Update `quentin/skills/manager.py` to route through backend registry (minimal changes).
- [x] Tests:
  - [x] `tests/manual/test_skill_backends_smoke.py`.

Acceptance Criteria:
- Planner/executor sees a unified skill inventory with consistent metadata.
- Backend switching does not break existing skills.

Rollback:
- Set `QUENTIN_SKILL_BACKEND=legacy_only`.

