# Real LLM Execution Plan (Opt-in, Sandbox First)

Date: 2026-02-08

Goal:
- Make the "AI brain" actually call a real external LLM end-to-end.
- Keep default developer/CI runs fully offline and deterministic.
- Preserve SafetyKernel + budget + trace/audit semantics.

Status:
- Remote chat providers are supported via `quentin/llm/client.py:call_llm` (opt-in via env).
- A smoke script exists: `scripts/run_real_llm_smoke.py`.
- A real-network integration test exists but is opt-in: `REAL_LLM_SMOKE=1`.

## Principles

1. Default offline: no real outbound calls unless explicitly configured.
2. No secrets in repo: all keys come from env vars or AuthProfile `secret_ref`.
3. Guard everything: real LLM calls still go through `SafetyKernel.guard_action`.
4. Trace/audit always: LLM call start/success/error are appended to audit JSONL.

## Provider Matrix (Chat)

- `openai`: OpenAI Chat Completions compatible API (`/v1/chat/completions`)
- `deepseek`: OpenAI-compatible API (default base: `https://api.deepseek.com/v1`)
- `openrouter`: OpenAI-compatible API (uses `OPENAI_*` envs by default)
- `gemini`: Google Generative Language API v1beta (`:generateContent`)

## Quick Start (Smoke)

1. OpenAI:

```bash
export LLM_PROVIDER=openai
export LLM_MODEL=gpt-4o-mini
export OPENAI_API_KEY=...            # required
export OPENAI_BASE_URL=https://api.openai.com/v1
python scripts/run_real_llm_smoke.py --prompt "Say 'pong' only."
```

2. Gemini:

```bash
export LLM_PROVIDER=gemini
export LLM_MODEL=gemini-2.5-flash
export GEMINI_API_KEY=...            # required
export GEMINI_BASE_URL=https://generativelanguage.googleapis.com/v1beta
python scripts/run_real_llm_smoke.py --prompt "Say 'pong' only."
```

## End-to-End (CognitiveLoop)

```bash
export LLM_PROVIDER=openai
export LLM_MODEL=gpt-4o-mini
export OPENAI_API_KEY=...
export LLM_STUB=0
python -m quentin.cli.qctl run-task --input-text "Write a short checklist for setting up pytest."
```

Notes:
- `quentin/bootstrap/container.py` now registers the default model with the correct provider/kind derived from `LLM_PROVIDER` or model id.
- `CouncilManager` uses `ModelRouter.route(...)` and passes `provider/model_name` into `call_llm`, so the same env config applies to planner/done/reflection councils.

## Auth Profiles (Key Rotation / Cooldown)

Optional: configure multiple keys for the same provider by writing `data/auth_profiles.json`.

Example (OpenAI rotation):

```json
{
  "profiles": {
    "openai_key_1": {"profile_id": "openai_key_1", "provider": "openai", "mode": "api_key", "secret_ref": "OPENAI_API_KEY_1", "label": "primary"},
    "openai_key_2": {"profile_id": "openai_key_2", "provider": "openai", "mode": "api_key", "secret_ref": "OPENAI_API_KEY_2", "label": "backup"}
  },
  "usage_stats": {}
}
```

```bash
export OPENAI_API_KEY_1=...
export OPENAI_API_KEY_2=...
```

Behavior:
- If a request fails with a classified failover reason (rate_limit/timeout/billing/auth/context_overflow/format),
  the profile is cooled down or disabled, and the next profile is tried.

## Safety / Budget / Observability

- SafetyKernel + PolicyEngine: `quentin/kernel/safety.py`, `quentin/kernel/policy.py`
- Audit log: `data/audit_events.jsonl` (gitignored via `/data/`)
- LLM timeouts: `LLM_REMOTE_TIMEOUT` (seconds; default 60)

## Opt-in Real Network Test

```bash
export REAL_LLM_SMOKE=1
pytest tests/integration/test_real_llm_smoke_env_gated.py -q
```

This is intentionally disabled by default so CI/offline runs remain stable.

