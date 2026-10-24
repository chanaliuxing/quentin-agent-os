import pytest
from app.runners import create_runner, CodexRunner, GeminiRunner, ClaudeRunner, MockRunner
from app.config import settings


def test_create_mock_runner(mock_settings):
    runner = create_runner("mock")
    assert isinstance(runner, MockRunner)


def test_create_codex_runner(mock_settings, monkeypatch):
    monkeypatch.setattr(settings, "codex_session_id", "test-codex-session")
    runner = create_runner("codex")
    assert isinstance(runner, CodexRunner)
    assert runner.session_id == "test-codex-session"


def test_create_gemini_runner(mock_settings, monkeypatch):
    monkeypatch.setattr(settings, "gemini_session_id", "test-gemini-session")
    runner = create_runner("gemini")
    assert isinstance(runner, GeminiRunner)
    assert runner.session_id == "test-gemini-session"


def test_create_claude_runner(mock_settings, monkeypatch):
    monkeypatch.setattr(settings, "claude_session_id", "test-claude-session")
    runner = create_runner("claude")
    assert isinstance(runner, ClaudeRunner)
    assert runner.session_id == "test-claude-session"


def test_create_runner_invalid_type():
    with pytest.raises(ValueError, match="Unknown runner type"):
        create_runner("invalid")


def test_create_runner_from_settings(mock_settings, monkeypatch):
    monkeypatch.setattr(settings, "agent_runner_type", "mock")
    runner = create_runner()
    assert isinstance(runner, MockRunner)


def test_codex_runner_without_session_id():
    runner = CodexRunner({})
    assert runner.session_id == ""
    assert runner.runner_type == "codex"


def test_gemini_runner_without_session_id():
    runner = GeminiRunner({})
    assert runner.session_id == ""
    assert runner.runner_type == "gemini"


def test_claude_runner_without_session_id():
    runner = ClaudeRunner({})
    assert runner.session_id == ""
    assert runner.runner_type == "claude"
