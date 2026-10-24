from __future__ import annotations

import json
from functools import lru_cache
from typing import Literal

from pydantic import BaseModel, Field

from app.config import settings

SessionScope = Literal["ephemeral", "by_role", "by_role_project", "by_role_worktree"]


class AgentSpec(BaseModel):
    role: str
    model_profile: str = "codex_balanced"
    session_scope: SessionScope = "by_role_project"
    resume_policy: Literal["disabled", "role_session_only", "worktree_bound"] = "role_session_only"
    handoff_policy: Literal["summary_only", "summary_plus_artifacts", "artifacts_only"] = "summary_only"
    session_id: str = ""


class SessionResolveInput(BaseModel):
    env: str
    project_id: str
    role: str
    worktree_id: str = ""
    memory_version: str = "v1"


class SessionResolution(BaseModel):
    session_id: str = ""
    source: Literal["agent_spec", "env", "global_fallback", "none"] = "none"
    scope: SessionScope = "by_role_project"
    policy_key: str = ""
    role: str = ""


def _default_agent_specs() -> dict[str, AgentSpec]:
    specs = {
        "planner": AgentSpec(role="planner", session_scope="by_role_project"),
        "reviewer": AgentSpec(role="reviewer", session_scope="by_role_project"),
        "dev": AgentSpec(role="dev", session_scope="by_role_worktree", resume_policy="worktree_bound"),
        "qa": AgentSpec(role="qa", session_scope="by_role_worktree", resume_policy="worktree_bound"),
        "lead": AgentSpec(role="lead", session_scope="by_role_project"),
    }
    return specs


@lru_cache(maxsize=1)
def _load_agent_specs_cached(raw: str) -> dict[str, AgentSpec]:
    specs = _default_agent_specs()
    payload = str(raw or "").strip()
    if not payload:
        return specs
    try:
        data = json.loads(payload)
    except Exception:
        return specs
    if not isinstance(data, dict):
        return specs
    for role, cfg in data.items():
        if not isinstance(cfg, dict):
            continue
        role_key = str(role).strip().lower()
        if not role_key:
            continue
        base = specs.get(role_key, AgentSpec(role=role_key))
        merged = base.model_dump()
        merged.update(cfg)
        merged["role"] = role_key
        try:
            specs[role_key] = AgentSpec.model_validate(merged)
        except Exception:
            continue
    return specs


def get_agent_specs() -> dict[str, AgentSpec]:
    return _load_agent_specs_cached(str(settings.agent_specs_json or ""))


def _scope_key(spec: AgentSpec, data: SessionResolveInput) -> str:
    if spec.session_scope == "ephemeral":
        return "ephemeral"
    if spec.session_scope == "by_role":
        return data.role
    if spec.session_scope == "by_role_project":
        return f"{data.project_id}:{data.role}"
    worktree = str(data.worktree_id or "").strip() or "default"
    return f"{data.project_id}:{data.role}:{worktree}"


def resolve_codex_session(
    *,
    role: str,
    project_id: str,
    worktree_id: str,
    explicit_session_id: str = "",
    explicit_source: Literal["agent_spec", "env"] = "agent_spec",
    global_fallback_session_id: str = "",
) -> SessionResolution:
    role_key = str(role).strip().lower() or "unknown"
    specs = get_agent_specs()
    spec = specs.get(role_key, AgentSpec(role=role_key))
    data = SessionResolveInput(
        env=str(settings.execution_profile or "dev"),
        project_id=str(project_id or "autoloop-project"),
        role=role_key,
        worktree_id=str(worktree_id or ""),
        memory_version="v1",
    )
    policy_key = f"{data.env}:{_scope_key(spec, data)}:{data.memory_version}"
    explicit = str(explicit_session_id).strip()
    if explicit:
        return SessionResolution(
            session_id=explicit,
            source=explicit_source,
            scope=spec.session_scope,
            policy_key=policy_key,
            role=role_key,
        )
    fallback = str(global_fallback_session_id).strip()
    if fallback:
        return SessionResolution(
            session_id=fallback,
            source="global_fallback",
            scope=spec.session_scope,
            policy_key=policy_key,
            role=role_key,
        )
    return SessionResolution(
        session_id="",
        source="none",
        scope=spec.session_scope,
        policy_key=policy_key,
        role=role_key,
    )
