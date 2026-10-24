from __future__ import annotations

from typing import Any, List, Tuple

from quentin.tools.autoloop import autoloop_run
from quentin.tools.packs.base import ToolPack
from quentin.tools.schemas import ToolSpec


class AutoloopToolPack(ToolPack):
    @property
    def domain(self) -> str:
        return "autoloop"

    def get_tools(self) -> List[Tuple[ToolSpec, Any]]:
        spec = ToolSpec(
            name="autoloop.run",
            description="Run autoloop pipeline for a PRD as an external engineering tool.",
            domain="ops",
            risk_level="high",
            input_schema={
                "type": "object",
                "properties": {
                    "prd_path": {"type": "string", "description": "Absolute path or repo-relative PRD file path."},
                    "mode": {"type": "string", "enum": ["graph", "temporal"], "default": "temporal"},
                    "profile": {"type": "string", "enum": ["dev", "prod"], "default": "dev"},
                    "project_id": {"type": "string"},
                    "dry_run": {"type": "boolean", "default": True},
                    "timeout_seconds": {"type": "integer", "minimum": 1, "default": 1800},
                },
                "required": ["prd_path"],
                "additionalProperties": False,
            },
        )
        return [(spec, autoloop_run)]
