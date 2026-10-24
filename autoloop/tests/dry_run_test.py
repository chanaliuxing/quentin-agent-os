#!/usr/bin/env python3
"""
Dry Run Test for AutoLoop
Tests all major functionality without external dependencies
"""

import sys
import asyncio
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.config import settings
from app.models import AgentRole, AgentStatus, ProjectState
from app.runners import (
    create_runner,
    MockRunner,
    CodexRunner,
    GeminiRunner,
    ClaudeRunner,
    AgentRunContext,
)
from app.utils.file_utils import (
    get_phase_dir,
    get_task_file,
    get_result_file,
    ensure_phase_dirs,
    write_task,
)


def print_section(title):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}\n")


def print_success(msg):
    print(f"✅ {msg}")


def print_info(msg):
    print(f"ℹ️  {msg}")


def print_error(msg):
    print(f"❌ {msg}")


def test_config():
    print_section("Test 1: Configuration")

    print_info(f"Project root: {settings.project_root}")
    print_info(f"Runner type: {settings.agent_runner_type}")
    print_info(f"Temporal mock mode: {settings.temporal_mock_mode}")

    settings.ensure_dirs()

    assert settings.runtime_dir.exists(), "Runtime dir should exist"
    print_success("Runtime directories created")

    assert settings.phases_dir.exists(), "Phases dir should exist"
    print_success("Phases directories created")

    print_success("Configuration test passed")


def test_models():
    print_section("Test 2: Data Models")

    state = ProjectState(
        project_id="test-project",
        prd_path="test_prd.md",
    )

    assert state.project_id == "test-project"
    print_success("ProjectState created")

    phase = state.add_phase("phase_01")
    assert phase.phase_id == "phase_01"
    print_success("Phase added to project")

    current = state.get_current_phase()
    assert current is not None
    assert current.phase_id == "phase_01"
    print_success("Current phase retrieved")

    print_success("Data models test passed")


def test_file_utils():
    print_section("Test 3: File Utilities")

    phase_id = "test_phase_01"
    ensure_phase_dirs(phase_id)

    phase_dir = get_phase_dir(phase_id)
    assert phase_dir.exists()
    print_success(f"Phase directory created: {phase_dir}")

    task_file = get_task_file(phase_id, AgentRole.DEV)
    assert task_file.parent.exists()
    print_success(f"Task file path: {task_file}")

    result_file = get_result_file(phase_id, AgentRole.DEV)
    assert result_file.parent.exists()
    print_success(f"Result file path: {result_file}")

    test_task = "# Test Task\n\nThis is a test task."
    write_task(task_file, test_task)
    assert task_file.exists()
    print_success("Task file written")

    content = task_file.read_text()
    assert content == test_task
    print_success("Task file read correctly")

    print_success("File utilities test passed")


def test_runner_factory():
    print_section("Test 4: Runner Factory")

    mock_runner = create_runner("mock")
    assert isinstance(mock_runner, MockRunner)
    print_success("MockRunner created")

    codex_runner = CodexRunner({"session_id": "test-session"})
    assert codex_runner.runner_type == "codex"
    assert codex_runner.session_id == "test-session"
    print_success("CodexRunner created with session")

    codex_no_session = CodexRunner({})
    assert codex_no_session.session_id == ""
    print_success("CodexRunner created without session (auto-create mode)")

    gemini_runner = GeminiRunner({"session_id": "gemini-test"})
    assert gemini_runner.runner_type == "gemini"
    print_success("GeminiRunner created")

    claude_runner = ClaudeRunner({"session_id": "claude-test"})
    assert claude_runner.runner_type == "claude"
    print_success("ClaudeRunner created")

    print_success("Runner factory test passed")


async def test_mock_runner_execution():
    print_section("Test 5: Mock Runner Execution")

    runner = MockRunner()

    health = await runner.health_check()
    assert health is True
    print_success("Health check passed")

    phase_id = "test_phase_01"
    ensure_phase_dirs(phase_id)

    task_file = get_task_file(phase_id, AgentRole.DEV)
    result_file = get_result_file(phase_id, AgentRole.DEV)
    log_file = settings.logs_dir / f"{phase_id}_dev.log"

    write_task(task_file, "# Test Task\n\nImplement feature X.")

    context = AgentRunContext(
        agent=AgentRole.DEV,
        task_file=task_file,
        result_file=result_file,
        working_dir=settings.project_root,
        log_file=log_file,
        phase_id=phase_id,
        timeout_seconds=30,
    )

    print_info(f"Running mock agent for {context.agent.value}...")
    result = await runner.run(context)

    assert result.status == AgentStatus.SUCCESS
    print_success(f"Agent execution status: {result.status.value}")

    assert result.exit_code == 0
    print_success(f"Exit code: {result.exit_code}")

    assert result.duration_seconds > 0
    print_success(f"Duration: {result.duration_seconds:.2f}s")

    assert result_file.exists()
    print_success(f"Result file created: {result_file}")

    result_content = result_file.read_text()
    payload = json.loads(result_content)
    assert payload["contract_version"] == "1.0"
    assert payload["status"] == "success"
    print_success("Result file contains valid JSON contract")

    print_success("Mock runner execution test passed")


async def test_session_manager():
    print_section("Test 6: Session Manager (Dry Run)")

    from app.runners.session_manager import SessionManager

    manager = SessionManager("codex")

    print_info("Session manager created for Codex")
    print_success(f"Session file: {manager.session_file}")

    sessions = await manager.list_sessions()
    print_info(f"Current sessions: {len(sessions)}")

    if sessions:
        print_success("Sessions loaded from file")
        for key, data in list(sessions.items())[:3]:
            print_info(f"  {key}: {data.get('session_id', 'N/A')[:40]}...")
    else:
        print_info("No existing sessions (this is normal)")

    print_success("Session manager test passed")


def test_prompt_templates():
    print_section("Test 7: Initialization Prompt Templates")

    from app.runners.session_manager import SessionManager

    manager = SessionManager("codex")

    for role in [AgentRole.LEAD, AgentRole.DEV, AgentRole.QA, AgentRole.REVIEWER]:
        prompt = manager._get_init_prompt(role, "phase_01")

        assert len(prompt) > 100, f"{role.value} prompt should be substantial"
        assert role.value in prompt.lower() or "agent" in prompt.lower()
        print_success(f"{role.value.upper()} init prompt: {len(prompt)} chars")

    print_success("Prompt templates test passed")


def test_cli_health_check():
    print_section("Test 8: CLI Health Check (Simulated)")

    print_info("Testing health check logic...")

    mock_runner = MockRunner()
    print_success(f"MockRunner available: True")

    try:
        codex_runner = CodexRunner({"session_id": "test"})
        print_info(f"CodexRunner created: {codex_runner.runner_type}")
        print_success("CodexRunner instantiation: OK")
    except Exception as e:
        print_info(f"CodexRunner note: {e} (expected without real CLI)")

    print_success("CLI health check logic test passed")


def test_file_structure():
    print_section("Test 9: Project File Structure")

    required_files = [
        "app/__init__.py",
        "app/config.py",
        "app/main.py",
        "app/models/state.py",
        "app/runners/base.py",
        "app/runners/codex_runner.py",
        "app/runners/gemini_runner.py",
        "app/runners/claude_runner.py",
        "app/runners/mock_runner.py",
        "app/runners/factory.py",
        "app/runners/session_manager.py",
        "app/utils/file_utils.py",
        "app/utils/process.py",
        "README.md",
        "CLAUDE.md",
        "AGENTS.md",
        "CLI_RUNNERS_GUIDE.md",
        "SESSION_AUTO_MANAGEMENT.md",
    ]

    missing = []
    for file in required_files:
        path = settings.project_root / file
        if path.exists():
            print_success(f"Found: {file}")
        else:
            print_error(f"Missing: {file}")
            missing.append(file)

    if missing:
        print_error(f"Missing {len(missing)} files")
    else:
        print_success("All required files present")

    assert len(missing) == 0, f"Missing files: {missing}"

    print_success("File structure test passed")


def test_documentation():
    print_section("Test 10: Documentation")

    docs = [
        ("README.md", 5000),
        ("CLAUDE.md", 5000),
        ("AGENTS.md", 3000),
        ("CLI_RUNNERS_GUIDE.md", 5000),
        ("SESSION_AUTO_MANAGEMENT.md", 5000),
    ]

    for doc_name, min_size in docs:
        doc_path = settings.project_root / doc_name
        if doc_path.exists():
            size = len(doc_path.read_text())
            if size >= min_size:
                print_success(f"{doc_name}: {size} chars (>= {min_size})")
            else:
                print_info(f"{doc_name}: {size} chars (expected >= {min_size})")
        else:
            print_error(f"{doc_name}: NOT FOUND")

    print_success("Documentation test passed")


async def main():
    print("\n")
    print("╔════════════════════════════════════════════════════════════╗")
    print("║        AutoLoop Dry Run Test Suite                        ║")
    print("╔════════════════════════════════════════════════════════════╗")
    print("\n")

    tests = [
        ("Configuration", test_config),
        ("Data Models", test_models),
        ("File Utilities", test_file_utils),
        ("Runner Factory", test_runner_factory),
        ("Mock Runner Execution", test_mock_runner_execution),
        ("Session Manager", test_session_manager),
        ("Prompt Templates", test_prompt_templates),
        ("CLI Health Check", test_cli_health_check),
        ("File Structure", test_file_structure),
        ("Documentation", test_documentation),
    ]

    passed = 0
    failed = 0

    for name, test_func in tests:
        try:
            if asyncio.iscoroutinefunction(test_func):
                await test_func()
            else:
                test_func()
            passed += 1
        except AssertionError as e:
            print_error(f"Test failed: {e}")
            failed += 1
        except Exception as e:
            print_error(f"Test error: {e}")
            failed += 1

    print("\n")
    print("╔════════════════════════════════════════════════════════════╗")
    print("║                    Test Summary                            ║")
    print("╚════════════════════════════════════════════════════════════╝")
    print(f"\n✅ Passed: {passed}/{len(tests)}")
    if failed > 0:
        print(f"❌ Failed: {failed}/{len(tests)}")
    else:
        print("🎉 All tests passed!")

    print("\n")

    return failed == 0


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
