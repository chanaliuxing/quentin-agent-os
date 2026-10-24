from __future__ import annotations
from typing import List, Tuple, Any
from quentin.tools.packs.base import ToolPack
from quentin.tools.schemas import ToolSpec

class ShellToolPack(ToolPack):
    @property
    def domain(self) -> str:
        return "shell"

    def get_tools(self) -> List[Tuple[ToolSpec, Any]]:
        from quentin.tools.shell import (
            shell_run_command, 
            interactive_shell_tool, 
            shell_ls, 
            shell_mkdir, 
            shell_grep, 
            shell_cat,
            shell_poll_results,
            shell_send_input,
            shell_send_signal,
        )
        import os
        
        # P5: Sandbox Integration
        # ... (keep existing sandbox comments)

        run_spec = ToolSpec(
            name="shell.run_command",
            description="Execute a non-interactive shell command. Use for one-off tasks.",
            domain="shell"
        )
        
        ls_spec = ToolSpec(
            name="ls",
            description="List directory contents.",
            domain="shell"
        )
        
        mkdir_spec = ToolSpec(
            name="mkdir",
            description="Create a directory. Use -p flag implicitly if using this tool.",
            domain="shell"
        )
        
        grep_spec = ToolSpec(
            name="grep",
            description="Search for patterns in files.",
            domain="shell"
        )
        
        cat_spec = ToolSpec(
            name="cat",
            description="Read file contents to stdout.",
            domain="shell"
        )

        interactive_spec = ToolSpec(
            name="shell.interactive",
            description="Start or interact with a persistent shell session. Use for long-running processes or stateful terminal work.",
            domain="shell",
            risk_level="high"
        )
        poll_spec = ToolSpec(
            name="shell.poll_results",
            description="Poll running background shell process output/status by proc_id.",
            domain="shell",
            risk_level="medium",
        )
        send_input_spec = ToolSpec(
            name="shell.send_input",
            description="Send stdin input to a background shell process by proc_id.",
            domain="shell",
            risk_level="medium",
        )
        send_signal_spec = ToolSpec(
            name="shell.send_signal",
            description="Forward Unix signals (SIGINT/SIGTERM/SIGKILL) to a background shell process by proc_id.",
            domain="shell",
            risk_level="high",
        )

        return [
            (run_spec, shell_run_command),
            (ls_spec, shell_ls),
            (mkdir_spec, shell_mkdir),
            (grep_spec, shell_grep),
            (cat_spec, shell_cat),
            (interactive_spec, interactive_shell_tool)
            ,
            (poll_spec, shell_poll_results),
            (send_input_spec, shell_send_input),
            (send_signal_spec, shell_send_signal),
        ]
