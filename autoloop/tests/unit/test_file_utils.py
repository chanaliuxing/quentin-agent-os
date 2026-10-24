import pytest
from pathlib import Path
from app.models import AgentRole
from app.utils.file_utils import (
    get_phase_dir,
    get_task_file,
    get_result_file,
    ensure_phase_dirs,
    read_task,
    write_result,
)


def test_get_phase_dir(mock_settings):
    phase_dir = get_phase_dir("phase_01")
    assert phase_dir.name == "phase_01"
    assert "phases" in str(phase_dir)


def test_get_task_file(mock_settings):
    task_file = get_task_file("phase_01", AgentRole.DEV)
    assert task_file.name == "dev.md"
    assert "tasks" in str(task_file)


def test_get_task_file_with_module(mock_settings):
    task_file = get_task_file("phase_01", AgentRole.DEV, "auth")
    assert task_file.name == "auth_dev.md"


def test_get_result_file(mock_settings):
    result_file = get_result_file("phase_01", AgentRole.QA)
    assert result_file.name == "qa.md"
    assert "results" in str(result_file)


def test_ensure_phase_dirs(mock_settings):
    ensure_phase_dirs("phase_01")
    phase_dir = get_phase_dir("phase_01")
    assert (phase_dir / "tasks").exists()
    assert (phase_dir / "results").exists()


def test_read_task_nonexistent(mock_settings):
    task_file = get_task_file("phase_99", AgentRole.DEV)
    content = read_task(task_file)
    assert content == ""


def test_write_and_read_task(mock_settings):
    task_file = get_task_file("phase_01", AgentRole.DEV)
    content = "# Test Task\n\nThis is a test."
    from app.utils.file_utils import write_task

    write_task(task_file, content)
    read_content = read_task(task_file)
    assert read_content == content


def test_write_result(mock_settings):
    result_file = get_result_file("phase_01", AgentRole.DEV)
    content = "# Test Result\n\nSuccess"
    write_result(result_file, content)
    assert result_file.exists()
    assert result_file.read_text() == content
