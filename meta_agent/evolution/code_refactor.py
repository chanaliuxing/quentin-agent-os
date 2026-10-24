# meta_agent/evolution/code_refactor.py
from __future__ import annotations
from dataclasses import dataclass
from typing import List, Dict, Any, Optional
from pathlib import Path
import textwrap
import json

from meta_agent.llm.cli_clients import make_codex_cli_client
from quentin.traces.core import JsonlTraceRecorder

trace = JsonlTraceRecorder(repo_root=".")


@dataclass
class CodeRefactorTarget:
    path: str
    start_marker: str = ""
    end_marker: str = ""


@dataclass
class CodeRefactorTask:
    intent: str
    description: str
    blueprint_snippet: str
    gap_description: str
    targets: List[CodeRefactorTarget]
    prefer_unified_diff: bool = True


class CodeRefactorWorker:
    def __init__(self, repo_root: str | Path = ".") -> None:
        self.repo_root = Path(repo_root).resolve()
        self.llm = make_codex_cli_client()

    def run(self, task: CodeRefactorTask) -> Dict[str, Any]:
        trace.record_event(event_type="code_refactor_start", trace_id=task.intent[:64] or "code_refactor", payload={"task": task.__dict__})

        context_files = self._load_target_files(task.targets)
        prompt = self._build_prompt(task, context_files)
        raw = self.llm.generate(
            system="You are a senior Python engineer, expert in self-iterating AI systems. Provide code refactoring suggestions.",
            user=prompt,
        )

        parsed = self._parse_response(raw, task, context_files)

        trace.record_event(event_type="code_refactor_done", trace_id=task.intent[:64] or "code_refactor", payload={"task": task.__dict__, "patch_preview": str(parsed)[:800]})
        return parsed

    def _load_target_files(self, targets: List[CodeRefactorTarget]) -> Dict[str, str]:
        out: Dict[str, str] = {}
        for t in targets:
            path = (self.repo_root / t.path).resolve()
            try:
                content = path.read_text(encoding="utf-8")
            except Exception as e:
                trace.record_event(event_type="code_refactor_read_error", trace_id=t.path, payload={"path": str(path), "error": repr(e)})
                continue
            out[t.path] = content
        return out

    def _build_prompt(self, task: CodeRefactorTask, context_files: Dict[str, str]) -> str:
        files_block = []
        for rel, content in context_files.items():
            snippet = content[:6000]
            files_block.append(f"FILE: {rel}\nCONTENT:\n{snippet}\n---\n")
        code_context = "\n".join(files_block)

        user = f"""
# Intent of change
{task.intent}

# Natural language explanation
{task.description}

# Related blueprint snippet
{task.blueprint_snippet}

# Existing GAP / problem description
{task.gap_description}

# Existing code snippet
{code_context}

Please:
1. Analyze the gap between the current implementation and the blueprint objective.
2. Propose a reasonable code change (can involve refactoring, adding parameters, adding logs, etc.).
3. Output the change as {'unified diff' if task.prefer_unified_diff else 'JSON patch description'}.
"""
        return textwrap.dedent(user).strip()

    def _parse_response(self, raw: str, task: CodeRefactorTask, context_files: Dict[str, str]) -> Dict[str, Any]:
        raw_stripped = raw.strip()
        if "```diff" in raw_stripped:
            try:
                start = raw_stripped.index("```diff") + len("```diff")
                end = raw_stripped.index("```", start)
                diff_body = raw_stripped[start:end].strip()
                return {"format": "unified_diff", "diff": diff_body, "raw": raw_stripped}
            except Exception: pass
        
        try:
            start = raw_stripped.index("{")
            end = raw_stripped.rindex("}") + 1
            frag = raw_stripped[start:end]
            return {"format": "json_patch", "patch": json.loads(frag), "raw": raw_stripped}
        except Exception: pass

        return {"format": "raw_text", "raw": raw_stripped}
