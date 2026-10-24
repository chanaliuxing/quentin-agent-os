# meta_agent/tools/code_tools.py
from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Dict, List, Optional
import os

from meta_agent.tools.cli_runner import JsonCliRunner, CliResult


@dataclass
class CodeChange:
    file_path: str
    diff: str
    rationale: str


@dataclass
class CodeRefactorResponse:
    tool_used: str
    changes: List[CodeChange]
    notes: str
    raw: Dict[str, Any]


class CodeToolBackend:
    def __init__(
        self,
        codex_cmd: Optional[str] = None,
        gemini_cmd: Optional[str] = None,
    ) -> None:
        self.codex_cmd = codex_cmd or os.environ.get("CODEX_CLI_CMD", "codex-cli")
        self.gemini_cmd = gemini_cmd or os.environ.get("GEMINI_CLI_CMD", "gemini-cli")
        self.codex_runner = JsonCliRunner(self.codex_cmd)
        self.gemini_runner = JsonCliRunner(self.gemini_cmd)

    def _run_tool(
        self,
        runner: JsonCliRunner,
        payload: Dict[str, Any],
        tool_name: str,
    ) -> Optional[CodeRefactorResponse]:
        req = {"tool": "code_refactor", "mode": "refactor", "payload": payload}
        res: CliResult = runner.run(req)
        if not res.ok or not res.result:
            return None

        raw = res.result
        changes_raw = raw.get("changes") or []
        changes = [CodeChange(**c) for c in changes_raw]

        return CodeRefactorResponse(
            tool_used=tool_name,
            changes=changes,
            notes=raw.get("notes", ""),
            raw=raw,
        )

    def refactor(
        self,
        *,
        intent: str,
        blueprint_snippet: str,
        gap_description: str,
        files: List[Dict[str, str]],
    ) -> Optional[CodeRefactorResponse]:
        payload = {
            "intent": intent,
            "blueprint_snippet": blueprint_snippet,
            "gap_description": gap_description,
            "files": files,
        }

        codex_resp = self._run_tool(self.codex_runner, payload, tool_name="codex")
        if codex_resp:
            return codex_resp

        gemini_resp = self._run_tool(self.gemini_runner, payload, tool_name="gemini")
        return gemini_resp
