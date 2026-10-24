from __future__ import annotations

from typing import Any

from quentin.tools.packs.base import ToolPackRegistry
from quentin.tools.packs.filesystem_pack import FileSystemToolPack
from quentin.tools.packs.shell_pack import ShellToolPack
from quentin.tools.packs.interactive_shell_pack import InteractiveShellToolPack
from quentin.tools.packs.aliases_pack import AliasesToolPack
from quentin.tools.packs.middleware_pack import ToolMiddlewarePack
from quentin.tools.packs.policies_pack import ToolPoliciesPack
from quentin.tools.packs.plugins_pack import PluginsToolPack
from quentin.tools.packs.coder_pack import CoderToolPack
from quentin.tools.packs.usage_sinks_pack import UsageSinksToolPack
from quentin.tools.packs.mcp_pack import MCPToolPack
from quentin.tools.packs.execution_parity_pack import ExecutionParityToolPack
from quentin.tools.packs.autoloop_pack import AutoloopToolPack


def build_builtin_tool_packs_registry(*, container: Any) -> ToolPackRegistry:
    reg = ToolPackRegistry()
    # Base core tools first
    reg.register(UsageSinksToolPack())
    reg.register(FileSystemToolPack())
    reg.register(ShellToolPack())
    reg.register(InteractiveShellToolPack())
    reg.register(CoderToolPack())
    reg.register(ExecutionParityToolPack())
    reg.register(AutoloopToolPack())
    reg.register(AliasesToolPack())
    reg.register(ToolMiddlewarePack())
    reg.register(ToolPoliciesPack())
    reg.register(PluginsToolPack())
    reg.register(MCPToolPack())
    try:
        reg.load_bootstrap_hooks_from_env()
    except Exception:
        pass
    return reg
