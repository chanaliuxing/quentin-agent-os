import asyncio
from pathlib import Path
from unittest.mock import patch

import pytest

from app.models import AgentRole, AgentStatus
from app.runners.base import AgentRunContext
from app.runners.codex_runner import CodexRunner


@pytest.mark.asyncio
async def test_codex_runner_without_session_uses_exec(mock_settings, temp_project_dir: Path):
    task_file = temp_project_dir / "task.md"
    result_file = temp_project_dir / "result.md"
    log_file = temp_project_dir / "run.log"
    task_file.write_text("# task", encoding="utf-8")

    context = AgentRunContext(
        agent=AgentRole.DEV,
        task_file=task_file,
        result_file=result_file,
        working_dir=temp_project_dir,
        log_file=log_file,
        phase_id="phase_01",
    )

    runner = CodexRunner({})

    async def fake_run_subprocess_with_timeout(**kwargs):
        assert kwargs["cmd"][0:2] == ["codex", "exec"]
        assert "resume" not in kwargs["cmd"]
        return {"returncode": 0, "stdout": "{}", "stderr": ""}

    with patch("app.runners.codex_runner.settings.agent_specs_json", ""):
        with patch("app.runners.codex_runner.run_subprocess_with_timeout", side_effect=fake_run_subprocess_with_timeout):
            with patch.object(runner, "_get_latest_commit", return_value="abc123"):
                result = await runner.run(context)

    assert result.status == AgentStatus.SUCCESS
    assert result.commit_sha == "abc123"


@pytest.mark.asyncio
async def test_codex_runner_with_session_uses_resume(mock_settings, temp_project_dir: Path):
    task_file = temp_project_dir / "task.md"
    result_file = temp_project_dir / "result.md"
    log_file = temp_project_dir / "run.log"
    task_file.write_text("# task", encoding="utf-8")

    context = AgentRunContext(
        agent=AgentRole.DEV,
        task_file=task_file,
        result_file=result_file,
        working_dir=temp_project_dir,
        log_file=log_file,
        phase_id="phase_01",
    )

    runner = CodexRunner({"session_id": "session-123"})
    seen_resume = {"value": False}

    async def fake_run_subprocess_with_timeout(**kwargs):
        if kwargs["cmd"][0:3] == ["codex", "exec", "resume"]:
            seen_resume["value"] = True
            assert "session-123" in kwargs["cmd"]
        return {"returncode": 0, "stdout": "{}", "stderr": ""}

    with patch("app.runners.codex_runner.settings.codex_prefer_ephemeral", False):
        with patch("app.runners.codex_runner.settings.agent_specs_json", ""):
            with patch.object(runner, "_probe_state_db", return_value=False):
                with patch.object(runner, "_resume_health_check", return_value={"healthy": True, "reason": "ok"}):
                    with patch("app.runners.codex_runner.run_subprocess_with_timeout", side_effect=fake_run_subprocess_with_timeout):
                        with patch.object(runner, "_get_latest_commit", return_value="abc123"):
                            result = await runner.run(context)

    assert result.status == AgentStatus.SUCCESS
    assert seen_resume["value"] is True


@pytest.mark.asyncio
async def test_codex_runner_falls_back_to_ephemeral_on_state_db_fatal_signal(mock_settings, temp_project_dir: Path):
    task_file = temp_project_dir / "task.md"
    result_file = temp_project_dir / "result.md"
    log_file = temp_project_dir / "run.log"
    task_file.write_text("# task", encoding="utf-8")

    context = AgentRunContext(
        agent=AgentRole.DEV,
        task_file=task_file,
        result_file=result_file,
        working_dir=temp_project_dir,
        log_file=log_file,
        phase_id="phase_01",
    )

    runner = CodexRunner({"session_id": "session-123"})
    calls: list[list[str]] = []

    async def fake_run_subprocess_with_timeout(**kwargs):
        calls.append(kwargs["cmd"])
        cmd = kwargs["cmd"]
        if cmd[0:3] == ["codex", "exec", "resume"]:
            return {"returncode": 0, "stdout": "{}", "stderr": "failed to open state db: migration 19 was previously applied but is missing"}
        if "--ephemeral" in cmd:
            return {"returncode": 0, "stdout": "{}", "stderr": ""}
        return {"returncode": 0, "stdout": "{}", "stderr": "failed to open state db: migration 19 was previously applied but is missing"}

    with patch("app.runners.codex_runner.settings.codex_prefer_ephemeral", False):
        with patch.object(runner, "_probe_state_db", return_value=False):
            with patch.object(runner, "_resume_health_check", return_value={"healthy": True, "reason": "ok"}):
                with patch("app.runners.codex_runner.run_subprocess_with_timeout", side_effect=fake_run_subprocess_with_timeout):
                    with patch.object(runner, "_get_latest_commit", return_value="abc123"):
                        result = await runner.run(context)

    assert result.status == AgentStatus.SUCCESS
    assert result.artifacts["execution_mode"] == "ephemeral"
    assert len(calls) >= 3


@pytest.mark.asyncio
async def test_codex_runner_keeps_resume_on_state_db_fallback_warning_only(mock_settings, temp_project_dir: Path):
    task_file = temp_project_dir / "task.md"
    result_file = temp_project_dir / "result.md"
    log_file = temp_project_dir / "run.log"
    task_file.write_text("# task", encoding="utf-8")

    context = AgentRunContext(
        agent=AgentRole.DEV,
        task_file=task_file,
        result_file=result_file,
        working_dir=temp_project_dir,
        log_file=log_file,
        phase_id="phase_01",
    )

    runner = CodexRunner({"session_id": "session-123"})

    async def fake_run_subprocess_with_timeout(**kwargs):
        cmd = kwargs["cmd"]
        if cmd[0:3] == ["codex", "exec", "resume"]:
            return {"returncode": 0, "stdout": "{}", "stderr": "state db record_discrepancy falling_back"}
        return {"returncode": 0, "stdout": "{}", "stderr": ""}

    with patch("app.runners.codex_runner.settings.codex_prefer_ephemeral", False):
        with patch.object(runner, "_probe_state_db", return_value=False):
            with patch.object(runner, "_resume_health_check", return_value={"healthy": True, "reason": "ok"}):
                with patch("app.runners.codex_runner.run_subprocess_with_timeout", side_effect=fake_run_subprocess_with_timeout):
                    with patch.object(runner, "_get_latest_commit", return_value="abc123"):
                        result = await runner.run(context)

    assert result.status == AgentStatus.SUCCESS
    assert result.artifacts["execution_mode"] == "resume"


@pytest.mark.asyncio
async def test_codex_runner_uses_attempt_timeout_budget(mock_settings, temp_project_dir: Path, monkeypatch):
    task_file = temp_project_dir / "task.md"
    result_file = temp_project_dir / "result.md"
    log_file = temp_project_dir / "run.log"
    task_file.write_text("# task", encoding="utf-8")

    context = AgentRunContext(
        agent=AgentRole.DEV,
        task_file=task_file,
        result_file=result_file,
        working_dir=temp_project_dir,
        log_file=log_file,
        phase_id="phase_01",
        timeout_seconds=1200,
    )
    monkeypatch.setattr("app.runners.codex_runner.settings.codex_attempt_timeout_seconds", 111)

    runner = CodexRunner({})
    captured_timeouts: list[int] = []

    async def fake_run_subprocess_with_timeout(**kwargs):
        captured_timeouts.append(kwargs["timeout"])
        return {"returncode": 0, "stdout": "{}", "stderr": ""}

    with patch("app.runners.codex_runner.settings.agent_specs_json", ""):
        with patch("app.runners.codex_runner.run_subprocess_with_timeout", side_effect=fake_run_subprocess_with_timeout):
            with patch.object(runner, "_get_latest_commit", return_value="abc123"):
                await runner.run(context)

    assert captured_timeouts
    assert all(value == 111 for value in captured_timeouts if value != 20)


@pytest.mark.asyncio
async def test_codex_runner_stops_on_usage_limit_signal(mock_settings, temp_project_dir: Path):
    task_file = temp_project_dir / "task.md"
    result_file = temp_project_dir / "result.md"
    log_file = temp_project_dir / "run.log"
    task_file.write_text("# task", encoding="utf-8")

    context = AgentRunContext(
        agent=AgentRole.DEV,
        task_file=task_file,
        result_file=result_file,
        working_dir=temp_project_dir,
        log_file=log_file,
        phase_id="phase_01",
    )

    runner = CodexRunner({"session_id": "session-123"})
    calls: list[list[str]] = []

    async def fake_run_subprocess_with_timeout(**kwargs):
        calls.append(kwargs["cmd"])
        return {
            "returncode": 1,
            "stdout": "",
            "stderr": "You've hit your usage limit. Please try again later.",
        }

    with patch("app.runners.codex_runner.settings.codex_prefer_ephemeral", False):
        with patch("app.runners.codex_runner.settings.agent_specs_json", ""):
            with patch.object(runner, "_probe_state_db", return_value=False):
                with patch.object(runner, "_resume_health_check", return_value={"healthy": True, "reason": "ok"}):
                    with patch("app.runners.codex_runner.run_subprocess_with_timeout", side_effect=fake_run_subprocess_with_timeout):
                        with patch.object(runner, "_get_latest_commit", return_value="abc123"):
                            result = await runner.run(context)

    assert result.status == AgentStatus.FAILED
    assert result.artifacts["error_class"] == "usage_limit"
    assert len(calls) == 1
    assert calls[0][0:3] == ["codex", "exec", "resume"]


@pytest.mark.asyncio
async def test_codex_runner_skips_resume_when_rollout_missing(mock_settings, temp_project_dir: Path):
    task_file = temp_project_dir / "task.md"
    result_file = temp_project_dir / "result.md"
    log_file = temp_project_dir / "run.log"
    task_file.write_text("# task", encoding="utf-8")

    context = AgentRunContext(
        agent=AgentRole.DEV,
        task_file=task_file,
        result_file=result_file,
        working_dir=temp_project_dir,
        log_file=log_file,
        phase_id="phase_01",
    )

    runner = CodexRunner({"session_id": "missing-session"})
    calls: list[list[str]] = []

    async def fake_run_subprocess_with_timeout(**kwargs):
        calls.append(kwargs["cmd"])
        return {"returncode": 0, "stdout": "{}", "stderr": ""}

    with patch("app.runners.codex_runner.settings.codex_prefer_ephemeral", False):
        with patch("app.runners.codex_runner.settings.agent_specs_json", ""):
            with patch.object(runner, "_find_rollout_path", return_value=None):
                with patch("app.runners.codex_runner.run_subprocess_with_timeout", side_effect=fake_run_subprocess_with_timeout):
                    with patch.object(runner, "_get_latest_commit", return_value="abc123"):
                        result = await runner.run(context)

    assert result.status == AgentStatus.SUCCESS
    assert all(cmd[0:3] != ["codex", "exec", "resume"] for cmd in calls)


@pytest.mark.asyncio
async def test_codex_runner_resume_probe_exception_is_nonblocking(mock_settings, temp_project_dir: Path):
    task_file = temp_project_dir / "task.md"
    result_file = temp_project_dir / "result.md"
    log_file = temp_project_dir / "run.log"
    task_file.write_text("# task", encoding="utf-8")

    context = AgentRunContext(
        agent=AgentRole.DEV,
        task_file=task_file,
        result_file=result_file,
        working_dir=temp_project_dir,
        log_file=log_file,
        phase_id="phase_01",
    )

    runner = CodexRunner({"session_id": "session-123"})
    calls: list[list[str]] = []

    async def fake_run_subprocess_with_timeout(**kwargs):
        calls.append(kwargs["cmd"])
        return {"returncode": 0, "stdout": "{}", "stderr": ""}

    with patch("app.runners.codex_runner.settings.codex_prefer_ephemeral", False):
        with patch.object(runner, "_probe_state_db", return_value=False):
            with patch.object(runner, "_resume_health_check", return_value={"healthy": True, "reason": "resume_probe_exception_nonblocking"}):
                with patch("app.runners.codex_runner.run_subprocess_with_timeout", side_effect=fake_run_subprocess_with_timeout):
                    with patch.object(runner, "_get_latest_commit", return_value="abc123"):
                        result = await runner.run(context)

    assert result.status == AgentStatus.SUCCESS
    assert result.artifacts["execution_mode"] == "resume"


@pytest.mark.asyncio
async def test_codex_runner_planner_falls_back_from_resume_on_os_env_panic(mock_settings, temp_project_dir: Path):
    task_file = temp_project_dir / "task.md"
    result_file = temp_project_dir / "result.md"
    log_file = temp_project_dir / "run.log"
    task_file.write_text("# task", encoding="utf-8")

    context = AgentRunContext(
        agent=AgentRole.PLANNER,
        task_file=task_file,
        result_file=result_file,
        working_dir=temp_project_dir,
        log_file=log_file,
        phase_id="phase_01",
    )

    runner = CodexRunner({"session_id": "session-123"})
    calls: list[list[str]] = []
    panic_stderr = (
        "WARNING: proceeding, even though we could not update PATH: Operation not permitted (os error 1)\n"
        "ERROR codex_core::skills::manager: failed to install system skills\n"
        "thread 'reqwest-internal-sync-runtime' panicked at "
        "/Users/runner/.cargo/registry/src/index.crates.io-1949cf8c6b5b557f/"
        "system-configuration-0.6.1/src/dynamic_store.rs:154:1"
    )

    async def fake_run_subprocess_with_timeout(**kwargs):
        calls.append(kwargs["cmd"])
        cmd = kwargs["cmd"]
        if cmd[0:3] == ["codex", "exec", "resume"]:
            return {"returncode": 1, "stdout": "", "stderr": panic_stderr}
        return {"returncode": 0, "stdout": "{}", "stderr": ""}

    with patch("app.runners.codex_runner.settings.codex_prefer_ephemeral", False):
        with patch.object(runner, "_probe_state_db", return_value=False):
            with patch.object(runner, "_resume_health_check", return_value={"healthy": True, "reason": "ok"}):
                with patch("app.runners.codex_runner.run_subprocess_with_timeout", side_effect=fake_run_subprocess_with_timeout):
                    with patch.object(runner, "_get_latest_commit", return_value="abc123"):
                        result = await runner.run(context)

    assert result.status == AgentStatus.SUCCESS
    assert result.artifacts["execution_mode"] == "standard"
    assert len(calls) >= 2
    assert calls[0][0:3] == ["codex", "exec", "resume"]


@pytest.mark.asyncio
async def test_codex_runner_non_planner_does_not_mask_os_env_panic(mock_settings, temp_project_dir: Path):
    task_file = temp_project_dir / "task.md"
    result_file = temp_project_dir / "result.md"
    log_file = temp_project_dir / "run.log"
    task_file.write_text("# task", encoding="utf-8")

    context = AgentRunContext(
        agent=AgentRole.DEV,
        task_file=task_file,
        result_file=result_file,
        working_dir=temp_project_dir,
        log_file=log_file,
        phase_id="phase_01",
    )

    runner = CodexRunner({"session_id": "session-123"})
    calls: list[list[str]] = []
    panic_stderr = (
        "WARNING: proceeding, even though we could not update PATH: Operation not permitted (os error 1)\n"
        "ERROR codex_core::skills::manager: failed to install system skills\n"
        "thread 'reqwest-internal-sync-runtime' panicked at "
        "/Users/runner/.cargo/registry/src/index.crates.io-1949cf8c6b5b557f/"
        "system-configuration-0.6.1/src/dynamic_store.rs:154:1"
    )

    async def fake_run_subprocess_with_timeout(**kwargs):
        calls.append(kwargs["cmd"])
        return {"returncode": 1, "stdout": "", "stderr": panic_stderr}

    with patch("app.runners.codex_runner.settings.codex_prefer_ephemeral", False):
        with patch.object(runner, "_probe_state_db", return_value=False):
            with patch.object(runner, "_resume_health_check", return_value={"healthy": True, "reason": "ok"}):
                with patch("app.runners.codex_runner.run_subprocess_with_timeout", side_effect=fake_run_subprocess_with_timeout):
                    with patch.object(runner, "_get_latest_commit", return_value="abc123"):
                        result = await runner.run(context)

    assert result.status == AgentStatus.FAILED
    assert result.artifacts["execution_mode"] == "resume"
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_probe_state_db_exception_is_not_treated_as_degraded(mock_settings, temp_project_dir: Path):
    runner = CodexRunner({"session_id": "session-123"})
    context = AgentRunContext(
        agent=AgentRole.DEV,
        task_file=temp_project_dir / "task.md",
        result_file=temp_project_dir / "result.md",
        working_dir=temp_project_dir,
        log_file=temp_project_dir / "run.log",
        phase_id="phase_01",
    )

    async def raise_timeout(**kwargs):
        raise asyncio.TimeoutError()

    with patch("app.runners.codex_runner.run_subprocess_with_timeout", side_effect=raise_timeout):
        degraded = await runner._probe_state_db(context=context)

    assert degraded is False
