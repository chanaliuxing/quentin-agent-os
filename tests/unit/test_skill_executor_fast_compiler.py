from unittest.mock import MagicMock


def test_skill_executor_fast_compiler_common_steps(tmp_path, monkeypatch):
    from quentin.execution.skill_executor import Executor

    monkeypatch.setenv("LLM_MODEL", "qwen3-vl:latest")
    ex = Executor(repo_root=tmp_path, tool_manager=MagicMock())

    tc = ex._infer_fast_tool_call_from_description("Create the directory 'extensions/tools/gemini_cli/'")
    assert tc == {"tool_name": "mkdir", "args": {"path": "extensions/tools/gemini_cli/"}}

    tc2 = ex._infer_fast_tool_call_from_description("Check if the directory `extensions/tools/gemini_cli/` exists.")
    assert tc2 == {"tool_name": "ls", "args": {"path": "extensions/tools/gemini_cli/"}}

    tc2b = ex._infer_fast_tool_call_from_description("Read the target source file `extensions/tools/gemini_cli/logic.py` using fs.read_file.")
    assert tc2b == {"tool_name": "fs.read_file", "args": {"path": "extensions/tools/gemini_cli/logic.py"}}

    tc3 = ex._infer_fast_tool_call_from_description("Verify tool registration using gemini --help and capture output.")
    assert tc3 == {"tool_name": "shell.run_command", "args": {"command": "gemini --help"}}

    tc4 = ex._infer_fast_tool_call_from_description(
        'Write the exact report file `generated/brain_real_run_report.txt` using fs.write_file with JSON content "RUN_OK\\nAGENTS_PRESENT=yes\\nPYPROJECT_PRESENT=yes".'
    )
    assert tc4 == {
        "tool_name": "fs.write_file",
        "args": {
            "path": "generated/brain_real_run_report.txt",
            "content": "RUN_OK\nAGENTS_PRESENT=yes\nPYPROJECT_PRESENT=yes",
        },
    }


def test_skill_executor_fast_compiler_blocks_disallowed_mkdir(tmp_path, monkeypatch):
    from quentin.execution.skill_executor import Executor

    monkeypatch.setenv("LLM_MODEL", "qwen3-vl:latest")
    monkeypatch.delenv("QUENTIN_PATH_GUARD_EXTRA_ALLOWED_ROOTS", raising=False)
    ex = Executor(repo_root=tmp_path, tool_manager=MagicMock())

    tc = ex._infer_fast_tool_call_from_description("Create the directory 'quentin/execution/'")
    assert tc is None


def test_skill_executor_rewrites_directory_read_to_ls(tmp_path, monkeypatch):
    from quentin.execution.skill_executor import Executor

    monkeypatch.setenv("LLM_MODEL", "qwen3-vl:latest")
    ex = Executor(repo_root=tmp_path, tool_manager=MagicMock())

    dir_path = tmp_path / "extensions" / "tools" / "gemini_cli"
    dir_path.mkdir(parents=True, exist_ok=True)
    (dir_path / "logic.py").write_text("print('ok')\n", encoding="utf-8")

    repaired, reason = ex._repair_tool_call_for_paths(
        {"tool_name": "fs.read_file", "args": {"path": "extensions/tools/gemini_cli/"}}
    )
    assert repaired == {"tool_name": "ls", "args": {"path": "extensions/tools/gemini_cli"}}
    assert reason == "directory_read_rewritten_to_ls"

    unchanged, reason2 = ex._repair_tool_call_for_paths(
        {"tool_name": "fs.read_file", "args": {"path": "extensions/tools/gemini_cli/logic.py"}}
    )
    assert unchanged == {"tool_name": "fs.read_file", "args": {"path": "extensions/tools/gemini_cli/logic.py"}}
    assert reason2 is None


def test_skill_executor_aligns_shell_cat_to_fs_read_file(tmp_path, monkeypatch):
    from quentin.execution.skill_executor import Executor

    monkeypatch.setenv("LLM_MODEL", "qwen3-vl:latest")
    monkeypatch.setenv("QUENTIN_PLAN_TOOL_ALIGNMENT_ENABLED", "1")
    monkeypatch.setenv("QUENTIN_PLAN_TOOL_ALIGNMENT_AUTO_REWRITE", "1")
    ex = Executor(repo_root=tmp_path, tool_manager=MagicMock())

    aligned, event = ex._align_tool_call_with_step_intent(
        desc="Use fs.read_file to inspect extensions/tools/gemini_cli/logic.py",
        tool_call={"tool_name": "shell.run_command", "args": {"command": "cat extensions/tools/gemini_cli/logic.py"}},
        iteration=1,
    )
    assert aligned == {"tool_name": "fs.read_file", "args": {"path": "extensions/tools/gemini_cli/logic.py"}}
    assert isinstance(event, dict)
    assert event.get("type") == "tool_alignment_rewrite"


def test_skill_executor_aligns_shell_ls_to_fs_list_dir(tmp_path, monkeypatch):
    from quentin.execution.skill_executor import Executor

    monkeypatch.setenv("LLM_MODEL", "qwen3-vl:latest")
    monkeypatch.setenv("QUENTIN_PLAN_TOOL_ALIGNMENT_ENABLED", "1")
    monkeypatch.setenv("QUENTIN_PLAN_TOOL_ALIGNMENT_AUTO_REWRITE", "1")
    ex = Executor(repo_root=tmp_path, tool_manager=MagicMock())

    aligned, event = ex._align_tool_call_with_step_intent(
        desc="Use fs.list_dir to inspect extensions/tools/gemini_cli/",
        tool_call={"tool_name": "shell.run_command", "args": {"command": "ls -la extensions/tools/gemini_cli/"}},
        iteration=1,
    )
    assert aligned == {"tool_name": "ls", "args": {"path": "extensions/tools/gemini_cli/"}}
    assert isinstance(event, dict)
    assert event.get("type") == "tool_alignment_rewrite"


def test_skill_executor_aligns_shell_mkdir_to_fs_mkdir(tmp_path, monkeypatch):
    from quentin.execution.skill_executor import Executor

    monkeypatch.setenv("LLM_MODEL", "qwen3-vl:latest")
    monkeypatch.setenv("QUENTIN_PLAN_TOOL_ALIGNMENT_ENABLED", "1")
    monkeypatch.setenv("QUENTIN_PLAN_TOOL_ALIGNMENT_AUTO_REWRITE", "1")
    ex = Executor(repo_root=tmp_path, tool_manager=MagicMock())

    aligned, event = ex._align_tool_call_with_step_intent(
        desc="Use fs.mkdir to create extensions/tools/gemini_cli/",
        tool_call={"tool_name": "shell.run_command", "args": {"command": "mkdir -p extensions/tools/gemini_cli/"}},
        iteration=1,
    )
    assert aligned == {"tool_name": "mkdir", "args": {"path": "extensions/tools/gemini_cli/"}}
    assert isinstance(event, dict)
    assert event.get("type") == "tool_alignment_rewrite"


def test_skill_executor_aligns_shell_ls_to_fs_exists(tmp_path, monkeypatch):
    from quentin.execution.skill_executor import Executor

    monkeypatch.setenv("LLM_MODEL", "qwen3-vl:latest")
    monkeypatch.setenv("QUENTIN_PLAN_TOOL_ALIGNMENT_ENABLED", "1")
    monkeypatch.setenv("QUENTIN_PLAN_TOOL_ALIGNMENT_AUTO_REWRITE", "1")
    ex = Executor(repo_root=tmp_path, tool_manager=MagicMock())

    aligned, event = ex._align_tool_call_with_step_intent(
        desc="Use fs.exists to check extensions/tools/gemini_cli/manifest.yaml",
        tool_call={"tool_name": "shell.run_command", "args": {"command": "ls extensions/tools/gemini_cli/manifest.yaml"}},
        iteration=1,
    )
    assert aligned == {"tool_name": "fs.exists", "args": {"path": "extensions/tools/gemini_cli/manifest.yaml"}}
    assert isinstance(event, dict)
    assert event.get("type") == "tool_alignment_rewrite"


def test_skill_executor_blocks_misaligned_tool_before_fallback(tmp_path, monkeypatch):
    from quentin.execution.skill_executor import Executor

    monkeypatch.setenv("LLM_MODEL", "qwen3-vl:latest")
    monkeypatch.setenv("QUENTIN_PLAN_TOOL_ALIGNMENT_ENABLED", "1")
    monkeypatch.setenv("QUENTIN_PLAN_TOOL_ALIGNMENT_AUTO_REWRITE", "0")
    monkeypatch.setenv("QUENTIN_PLAN_TOOL_ALIGNMENT_HARD_BLOCK", "1")
    monkeypatch.setenv("QUENTIN_PLAN_TOOL_ALIGNMENT_ALLOW_FALLBACK", "1")
    monkeypatch.setenv("QUENTIN_PLAN_TOOL_ALIGNMENT_FALLBACK_AFTER_ITER", "2")
    ex = Executor(repo_root=tmp_path, tool_manager=MagicMock())

    _, event_first = ex._align_tool_call_with_step_intent(
        desc="Use fs.read_file to inspect config",
        tool_call={"tool_name": "shell.run_command", "args": {"command": "echo hi"}},
        iteration=1,
    )
    assert isinstance(event_first, dict)
    assert event_first.get("blocked") is True

    _, event_second = ex._align_tool_call_with_step_intent(
        desc="Use fs.read_file to inspect config",
        tool_call={"tool_name": "shell.run_command", "args": {"command": "echo hi"}},
        iteration=2,
    )
    assert isinstance(event_second, dict)
    assert event_second.get("blocked") is False


def test_skill_executor_allows_configured_fallback_family(tmp_path, monkeypatch):
    from quentin.execution.skill_executor import Executor

    monkeypatch.setenv("LLM_MODEL", "qwen3-vl:latest")
    ex = Executor(repo_root=tmp_path, tool_manager=MagicMock())
    call, event = ex._align_tool_call_with_step_intent(
        desc="Use fs.read_file to inspect config",
        tool_call={"tool_name": "shell.run_command", "args": {"command": "ls -la"}},
        iteration=1,
        expected_tool="fs.read_file",
        allowed_fallback_families=["shell"],
    )
    assert call["tool_name"] == "shell.run_command"
    assert event is None


def test_skill_executor_emits_alignment_trace_event(tmp_path, monkeypatch):
    from quentin.execution.skill_executor import Executor

    monkeypatch.setenv("LLM_MODEL", "qwen3-vl:latest")
    ex = Executor(repo_root=tmp_path, tool_manager=MagicMock())

    class _Recorder:
        def __init__(self):
            self.events = []

        def record_event(self, event):
            self.events.append(event)

    rec = _Recorder()
    ex._emit_alignment_trace_event(
        context={"trace_id": "trace_test", "trace_recorder": rec},
        step_id="s1",
        iteration=2,
        event={
            "type": "tool_alignment_violation",
            "reason": "plan_execution_misalignment",
            "expected_tool": "fs.read_file",
            "actual_tool": "shell.run_command",
            "blocked": True,
        },
    )
    assert len(rec.events) == 1
    payload = rec.events[0].payload
    assert payload.get("signal") == "plan_tool_alignment"
    assert payload.get("reason") == "plan_execution_misalignment"
    assert payload.get("blocked") is True
