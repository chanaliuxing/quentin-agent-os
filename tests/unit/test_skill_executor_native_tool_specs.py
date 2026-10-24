def test_skill_executor_native_tool_specs_contains_shell_aliases():
    from quentin.execution.skill_executor import Executor

    specs = Executor._build_native_tool_specs()
    names = {s.get("function", {}).get("name") for s in specs if isinstance(s, dict)}

    # Core fs tools
    assert "fs.read_file" in names
    assert "fs.write_file" in names
    assert "fs.exists" in names

    # Shell aliases required for correct directory creation/listing
    assert "mkdir" in names
    assert "ls" in names
    assert "cat" in names
    assert "grep" in names
    assert "shell.run_command" in names

