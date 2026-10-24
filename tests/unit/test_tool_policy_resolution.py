from quentin.tools.manager import ToolPolicy, resolve_effective_tool_policy
from quentin.tools.manager import ToolCallContext
from quentin.bootstrap.container import Container
import pytest


def test_resolve_effective_tool_policy_merges_allow_deny_and_profile() -> None:
    global_policy = ToolPolicy(allow=None, deny=["danger.*"], profile="safe")
    stacked = [
        ToolPolicy(allow=["read*", "write*"], deny=None, profile=None),
        ToolPolicy(allow=["net*"], deny=["write_secrets"], profile="code"),
    ]
    eff = resolve_effective_tool_policy(global_policy=global_policy, stacked=stacked)
    assert eff.profile == "code"
    assert "danger.*" in (eff.deny or [])
    assert "write_secrets" in (eff.deny or [])
    assert eff.allow is not None
    assert "read*" in eff.allow
    assert "net*" in eff.allow


def test_shell_allowed_in_sandbox_with_guard(tmp_path) -> None:
    container = Container(repo_root=tmp_path)
    out = container.tool_manager.invoke(
        "shell.run_command",
        {"command": "echo hi"},
        ctx=ToolCallContext(metadata={"environment": "sandbox"}),
    )
    assert isinstance(out, dict)
    assert out.get("status") == "ok"


def test_shell_denied_in_prod_by_default_policy(tmp_path) -> None:
    container = Container(repo_root=tmp_path)
    with pytest.raises(PermissionError):
        container.tool_manager.invoke(
            "shell.run_command",
            {"command": "echo hi"},
            ctx=ToolCallContext(metadata={"environment": "prod"}),
        )


def test_executor_tool_call_not_blocked_by_conflicting_defaults(tmp_path) -> None:
    container = Container(repo_root=tmp_path)
    out = container.tool_manager.invoke(
        "shell.run_command",
        {"command": "printf 'ok'"},
        ctx=ToolCallContext(metadata={"environment": "sandbox", "role": "executor", "actor": "executor"}),
    )
    assert out.get("status") == "ok"
