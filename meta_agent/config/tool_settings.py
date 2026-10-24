# meta_agent/config/tool_settings.py
from __future__ import annotations
from dataclasses import dataclass
import os


@dataclass
class ToolSettings:
    usage_truncate_len: int = 2000

    @classmethod
    def from_env(cls) -> "ToolSettings":
        return cls(
            usage_truncate_len=int(os.environ.get("TOOL_USAGE_TRUNCATE_LEN", "2000")),
        )


tool_settings = ToolSettings.from_env()
