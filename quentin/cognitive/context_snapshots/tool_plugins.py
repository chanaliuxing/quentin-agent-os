from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

from quentin.cognitive.context_snapshots.base import ContextSnapshotProvider, SnapshotBlock

class ToolPluginsSnapshotProvider(ContextSnapshotProvider):
    @property
    def id(self) -> str:
        return "tool_plugins"

    @property
    def priority(self) -> int:
        return 40

    def collect(self, repo_root: Path, context: Dict[str, Any]) -> Optional[SnapshotBlock]:
        content = (
            "Tool plugins live under:\n"
            "- extensions/tools/<plugin_dir>/manifest.yaml + logic.py\n"
            "- quentin/mutable/extensions/tools/<plugin_dir>/ (alternate dev root)\n"
            "\n"
            "CRITICAL MANIFEST RULES:\n"
            "1. manifest.yaml MUST contain ALL these fields exactly as shown (id, name, description, entrypoint, kind, domain, risk_level, output_trust, permissions):\n"
            "```yaml\n"
            "id: \"my_tool_id\"\n"
            "name: \"Tool Name\"\n"
            "description: \"Detailed description\"\n"
            "entrypoint: \"logic:run\"\n"
            "kind: \"external\"\n"
            "domain: \"extensions\"\n"
            "risk_level: \"low\"\n"
            "output_trust: \"untrusted\"\n"
            "permissions: []\n"
            "```\n"
            "\n"
            "CRITICAL LOGIC.PY RULES:\n"
            "1. NEVER 'import shell'. It does not exist in the Python path.\n"
            "2. Use 'import subprocess' for CLI calls.\n"
            "3. The entrypoint function MUST match the manifest (e.g., 'def run(payload, ctx=None):').\n"
            "\n"
            "Example logic.py:\n"
            "```python\n"
            "import subprocess\n"
            "import json\n"
            "def run(payload, ctx=None):\n"
            "    query = payload.get(\"query\")\n"
            "    res = subprocess.run([\"echo\", query], capture_output=True, text=True)\n"
            "    return {\"status\": \"ok\", \"output\": res.stdout}\n"
            "```\n"
        )
        return SnapshotBlock(
            id=self.id,
            title="Tool Plugin Manifest Schema & Constraints",
            content=content,
            ttl_sec=300,
            meta={"source": "quentin.tools.plugin_schema.ToolPluginManifest"},
        )
