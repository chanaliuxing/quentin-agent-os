from __future__ import annotations

from quentin.cognitive.prompt_factory import build_system_prompt, RuntimeInfo


def test_build_full_mode_includes_expected_sections() -> None:
    out = build_system_prompt(
        mode="full",
        identity="IDENTITY",
        safety_rules=["SAFE_A", "SAFE_B"],
        enabled_tools={"fs.read_file": "read file", "shell.run_command": "run shell"},
        skill_context="SKILL_CTX",
        memory_context="MEM_CTX",
        project_context="PROJECT_CTX",
        runtime_info=RuntimeInfo(
            agent_id="agent-x",
            workspace="/tmp/ws",
            os_name="darwin",
            model="qwen",
            budget_remaining="85%",
        ),
        hints=["HINT_1"],
    )
    assert "IDENTITY" in out
    assert "Safety:" in out
    assert "Tools (short summaries):" in out
    assert "Skills:" in out
    assert "Memory:" in out
    assert "Runtime: agent=agent-x" in out
    assert "HINT_1" in out


def test_build_minimal_mode_omits_tools_skills_memory() -> None:
    out = build_system_prompt(
        mode="minimal",
        identity="IDENTITY",
        safety_rules=["SAFE_A"],
        enabled_tools={"fs.read_file": "read file"},
        skill_context="SKILL_CTX",
        memory_context="MEM_CTX",
        project_context="PROJECT_CTX",
        runtime_info=RuntimeInfo(agent_id="agent-min", workspace=".", os_name="linux", model="mini"),
    )
    assert "IDENTITY" in out
    assert "Safety:" in out
    assert "Runtime: agent=agent-min" in out
    assert "Tools (short summaries):" not in out
    assert "Skills:" not in out
    assert "Memory:" not in out


def test_prompt_section_order_is_stable() -> None:
    out = build_system_prompt(
        mode="full",
        identity="IDENTITY",
        safety_rules=["SAFE_A"],
        enabled_tools={"tool_a": "a"},
        runtime_info=RuntimeInfo(agent_id="agent", workspace=".", os_name="x", model="m"),
    )
    pos_identity = out.find("IDENTITY")
    pos_safety = out.find("Safety:")
    pos_tools = out.find("Tools (short summaries):")
    pos_runtime = out.find("Runtime: agent=agent")
    assert -1 not in (pos_identity, pos_safety, pos_tools, pos_runtime)
    assert pos_identity < pos_safety < pos_tools < pos_runtime

