from __future__ import annotations

from types import SimpleNamespace

import pytest

from quentin.tools.manager import ToolCallContext, ToolManager, ToolPolicy


class _CapturingKernel:
    def __init__(self) -> None:
        self.last_action = None

    def guard_action(self, action):  # type: ignore[no-untyped-def]
        self.last_action = action
        return SimpleNamespace(allow=True, reason="ok")


def test_tool_guard_includes_command_head_and_flags_without_full_command() -> None:
    tm = ToolManager()
    tm.set_global_policy(ToolPolicy(allow=["*"]))

    kernel = _CapturingKernel()
    tm.set_safety_kernel(kernel)

    def tool_fn(params, ctx):  # type: ignore[no-untyped-def]
        _ = (params, ctx)
        return {"status": "ok"}

    tm.register("shell.run_command", tool_fn)

    cmd = "rm -rf /tmp/somewhere --preserve-root=all"
    out = tm.invoke("shell.run_command", {"command": cmd}, ctx=ToolCallContext(metadata={"environment": "sandbox"}))
    assert out["status"] == "ok"

    assert kernel.last_action is not None
    md = getattr(kernel.last_action, "metadata", {}) or {}
    risk = md.get("risk_summary") or {}

    assert risk.get("command_head") == "rm"
    assert "-rf" in (risk.get("command_flags") or [])
    assert risk.get("is_destructive_candidate") is True

    # Do not log full command text in the action metadata.
    assert "command" not in md
    assert "command" not in risk
    assert "/tmp/somewhere" not in str(md)


def test_tool_guard_includes_target_path_summary_when_present() -> None:
    tm = ToolManager()
    tm.set_global_policy(ToolPolicy(allow=["*"]))

    kernel = _CapturingKernel()
    tm.set_safety_kernel(kernel)

    tm.register("fs.write_file", lambda params, ctx: {"status": "ok"})  # type: ignore[arg-type]
    tm.invoke("fs.write_file", {"path": "mutable/x.py", "content": "x=1"}, ctx=ToolCallContext(metadata={"environment": "sandbox"}))

    assert kernel.last_action is not None
    md = getattr(kernel.last_action, "metadata", {}) or {}
    risk = md.get("risk_summary") or {}

    assert risk.get("target_path") == "mutable/x.py"
    assert risk.get("target_path_key") == "path"

