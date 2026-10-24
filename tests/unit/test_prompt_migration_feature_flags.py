from __future__ import annotations

import json

from meta_agent.config.feature_flags import (
    PROMPT_MIGRATION_FLAGS,
    PROMPT_MIGRATION_M1_SYSTEM_FACTORY,
    PROMPT_MIGRATION_M8_CONTEXT_PRUNING,
    PROMPT_MIGRATION_SYSTEM_EVENT_ENQUEUED,
    PROMPT_MIGRATION_SYSTEM_EVENT_INJECTED,
    PROMPT_MIGRATION_TRACE_PREFIX,
    FeatureFlagManager,
)


def test_prompt_migration_flags_registry_is_complete() -> None:
    assert PROMPT_MIGRATION_M1_SYSTEM_FACTORY in PROMPT_MIGRATION_FLAGS
    assert PROMPT_MIGRATION_M8_CONTEXT_PRUNING in PROMPT_MIGRATION_FLAGS
    assert len(PROMPT_MIGRATION_FLAGS) == 8


def test_prompt_migration_env_override(monkeypatch, tmp_path) -> None:
    manager = FeatureFlagManager(flags_root=tmp_path)
    monkeypatch.setenv("QUENTIN_FF_PROMPT_MIGRATION_M4_TOOL_SUMMARY", "1")
    enabled = manager.is_prompt_migration_enabled("PROMPT_MIGRATION_M4_TOOL_SUMMARY", default=False)
    assert enabled is True


def test_prompt_migration_runtime_file_fallback(tmp_path) -> None:
    manager = FeatureFlagManager(flags_root=tmp_path)
    flags_dir = tmp_path / "feature_flags"
    flags_dir.mkdir(parents=True, exist_ok=True)
    (flags_dir / "runtime_flags.json").write_text(
        json.dumps({"PROMPT_MIGRATION_M6_SOP_SKILLS": True}, ensure_ascii=False),
        encoding="utf-8",
    )
    enabled = manager.is_prompt_migration_enabled("PROMPT_MIGRATION_M6_SOP_SKILLS", default=False)
    assert enabled is True


def test_prompt_migration_trace_actions_use_prefix() -> None:
    assert PROMPT_MIGRATION_SYSTEM_EVENT_ENQUEUED.startswith(PROMPT_MIGRATION_TRACE_PREFIX)
    assert PROMPT_MIGRATION_SYSTEM_EVENT_INJECTED.startswith(PROMPT_MIGRATION_TRACE_PREFIX)
