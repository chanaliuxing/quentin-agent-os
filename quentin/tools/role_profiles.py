from __future__ import annotations
from typing import Dict, List, Set

class RoleProfiles:
    """
    P5: Ported from OpenClaw's role-based gating.
    Defines which tool groups are physically available to each role.
    """
    
    GROUPS = {
        "read_only": {"ls", "cat", "grep", "find", "pwd", "fs.read_file", "fs.exists"},
        "file_edit": {"fs.write_file", "fs.search_replace", "mkdir", "rm", "touch"},
        "shell_exec": {"shell.run_command", "shell.send_input", "shell.poll_results", "shell.send_signal"},
        "browser_full": {"browser.navigate", "browser.click", "browser.type", "browser.observe"},
        "memory_full": {"memory.search", "memory.remember", "memory.forget"},
        "comms_ops": {
            "discord.actions",
            "slack.actions",
            "telegram.actions",
            "whatsapp.actions",
            "channels.listener",
            "cron.tool",
            "session.status",
            "sessions.announce_target",
            "web.readability",
            "image.tool",
            "tts.tool",
            "canvas.tool",
            "agents.list",
            "nodes.tool",
        },
    }

    # Predefined Roles
    ROLES = {
        "researcher": ["read_only", "memory_full", "browser_full"],
        "developer": ["read_only", "file_edit", "shell_exec", "memory_full", "comms_ops"],
        "admin": ["read_only", "file_edit", "shell_exec", "browser_full", "memory_full", "comms_ops"],
        "minimal": ["read_only"]
    }

    @classmethod
    def get_allowed_tools(cls, role_name: str) -> Set[str]:
        """
        Returns the set of tool names allowed for a specific role.
        """
        role = cls.ROLES.get(role_name.lower(), cls.ROLES["minimal"])
        allowed = set()
        for group_key in role:
            allowed.update(cls.GROUPS.get(group_key, set()))
        return allowed
