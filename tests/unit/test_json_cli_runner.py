import pytest
from unittest.mock import patch, AsyncMock
import asyncio

from quentin.infra.json_cli_runner import JsonCliRunner, CliResult

# Mock the run_subprocess function
@pytest.fixture
def mock_run_subprocess():
    # Patch run_subprocess where it's imported by JsonCliRunner
    with patch("quentin.infra.json_cli_runner.run_subprocess") as mock:
        yield mock

@pytest.fixture
def json_cli_runner():
    return JsonCliRunner(cwd="/tmp", default_timeout=1) # Use a short default timeout for tests

@pytest.mark.asyncio
async def test_run_normal_json_output(json_cli_runner, mock_run_subprocess):
    cmd = ["echo", '{"status": "ok", "data": 123}']
    expected_stdout = '{"status": "ok", "data": 123}\n' # subprocess often adds a newline
    mock_run_subprocess.return_value = (0, expected_stdout, "")

    result = await json_cli_runner.run(cmd)

    mock_run_subprocess.assert_awaited_once_with(cmd, cwd=json_cli_runner.cwd, timeout=json_cli_runner.default_timeout)
    assert result.ok is True
    assert result.return_code == 0
    assert result.raw_stdout == expected_stdout
    assert result.parsed_json == {"status": "ok", "data": 123}
    assert result.error_message is None

@pytest.mark.asyncio
async def test_run_non_zero_exit_code(json_cli_runner, mock_run_subprocess):
    cmd = ["false"]
    expected_stderr = "Error message from cli\n"
    mock_run_subprocess.return_value = (1, "", expected_stderr)

    result = await json_cli_runner.run(cmd)

    mock_run_subprocess.assert_awaited_once_with(cmd, cwd=json_cli_runner.cwd, timeout=json_cli_runner.default_timeout)
    assert result.ok is False
    assert result.return_code == 1
    assert result.raw_stdout == ""
    assert result.raw_stderr == expected_stderr
    assert "non-zero code 1" in result.error_message
    assert result.parsed_json is None

@pytest.mark.asyncio
async def test_run_non_json_output(json_cli_runner, mock_run_subprocess):
    cmd = ["echo", "plain text output"]
    expected_stdout = "plain text output\n"
    mock_run_subprocess.return_value = (0, expected_stdout, "")

    result = await json_cli_runner.run(cmd)

    mock_run_subprocess.assert_awaited_once_with(cmd, cwd=json_cli_runner.cwd, timeout=json_cli_runner.default_timeout)
    assert result.ok is False
    assert result.return_code == 0
    assert result.raw_stdout == expected_stdout
    assert "not valid JSON" in result.error_message
    assert result.parsed_json is None

@pytest.mark.asyncio
async def test_run_command_timeout(json_cli_runner, mock_run_subprocess):
    cmd = ["sleep", "100"]
    mock_run_subprocess.side_effect = asyncio.TimeoutError

    result = await json_cli_runner.run(cmd, timeout=0.1)

    mock_run_subprocess.assert_awaited_once_with(cmd, cwd=json_cli_runner.cwd, timeout=0.1)
    assert result.ok is False
    assert result.return_code == -1
    assert "timed out" in result.error_message
    assert result.raw_stderr == "Command timed out."
    assert result.timeout == 0.1
    assert result.parsed_json is None

@pytest.mark.asyncio
async def test_run_command_execution_error(json_cli_runner, mock_run_subprocess):
    cmd = ["nonexistent_command"]
    mock_run_subprocess.side_effect = FileNotFoundError("Command not found")

    result = await json_cli_runner.run(cmd)

    mock_run_subprocess.assert_awaited_once_with(cmd, cwd=json_cli_runner.cwd, timeout=json_cli_runner.default_timeout)
    assert result.ok is False
    assert result.return_code == -2
    assert "Failed to execute command" in result.error_message
    assert "Command not found" in result.raw_stderr
    assert result.parsed_json is None
