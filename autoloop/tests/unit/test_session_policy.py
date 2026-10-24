from app.config import settings
from app.runners.session_policy import resolve_codex_session


def test_resolve_codex_session_uses_agent_spec_explicit(monkeypatch):
    monkeypatch.setattr(
        settings,
        "agent_specs_json",
        '{"dev":{"session_scope":"by_role_worktree","session_id":"dev-session-123"}}',
    )
    resolution = resolve_codex_session(
        role="dev",
        project_id="project-a",
        worktree_id="worktree-main",
        explicit_session_id="dev-session-123",
        global_fallback_session_id="global-fallback",
    )
    assert resolution.session_id == "dev-session-123"
    assert resolution.source == "agent_spec"
    assert resolution.scope == "by_role_worktree"
    assert "project-a:dev:worktree-main" in resolution.policy_key


def test_resolve_codex_session_uses_global_fallback(monkeypatch):
    monkeypatch.setattr(settings, "agent_specs_json", "")
    monkeypatch.setattr(settings, "codex_session_id", "")
    resolution = resolve_codex_session(
        role="reviewer",
        project_id="project-a",
        worktree_id="",
        explicit_session_id="",
        global_fallback_session_id="global-session-abc",
    )
    assert resolution.session_id == "global-session-abc"
    assert resolution.source == "global_fallback"
    assert resolution.scope == "by_role_project"


def test_resolve_codex_session_uses_env_override(monkeypatch):
    monkeypatch.setattr(settings, "agent_specs_json", "")
    resolution = resolve_codex_session(
        role="qa",
        project_id="project-a",
        worktree_id="wt-1",
        explicit_session_id="env-session-1",
        explicit_source="env",
        global_fallback_session_id="global-session-abc",
    )
    assert resolution.session_id == "env-session-1"
    assert resolution.source == "env"
