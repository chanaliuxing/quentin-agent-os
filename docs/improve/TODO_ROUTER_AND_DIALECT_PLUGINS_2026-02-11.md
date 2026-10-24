# TODO: Router Policies + Dialect Plugins

Date: 2026-02-11
Scope: `quentin/models/router.py`, `quentin/llm/model_dialect.py`, `quentin/llm/client.py`, `tests/*`

Problem:
- Routing decisions and prompt dialect are embedded logic; swapping strategy is hard.
- For mixed-model systems, we want a pluggable policy stack:
  - simple tasks -> small model
  - complex refactor -> strong model
  - provider-specific prompt shaping

Goal:
- Introduce registries:
  - `RoutingPolicy` plugins (select model/provider)
  - `PromptDialect` plugins (transform system/user prompts)
- Keep current behavior as default policy + default dialect.

Non-goals:
- Do not force external provider usage; keep offline defaults.

Design (proposal):
- `RoutingPolicy`:
  - `id`, `priority`
  - `route(mode, task_type, metadata) -> ModelInfo`
- `PromptDialect`:
  - `id`, `priority`
  - `transform(provider, model_name, system_prompt, user_prompt, metadata) -> (sp, up, meta)`
- Config:
  - `QUENTIN_ROUTING_POLICY=default`
  - `QUENTIN_PROMPT_DIALECT=default`
  - Optional: `QUENTIN_ROUTING_POLICY=multi_agent` (delegates to `quentin/multi_agent/coordinator.py`)

Implementation Steps:
- [x] Add registries under `quentin/models/routing_policies/` and `quentin/llm/dialects/`.
- [x] Wrap existing router logic as `DefaultRoutingPolicy`.
- [x] Wrap `apply_model_dialect()` as `DefaultPromptDialect`.
- [x] Update `ModelRouter.route` and `call_llm` to apply plugins.
- [x] Tests:
  - [x] `tests/manual/test_router_dialect_plugins_smoke.py`.
  - [x] `tests/unit/test_routing_policy_multi_agent.py`.

Acceptance Criteria:
- Can add a new routing policy without editing router core.
- Dialect behavior is consistent across executor/council/self-prog call sites.

Rollback:
- Set policy/dialect to `default`.
