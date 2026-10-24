from __future__ import annotations

import os
import asyncio
from pathlib import Path

from quentin.execution.skill_executor import Executor as SkillExecutor
from quentin.skills.manager import SkillManager
from quentin.tools.manager import ToolManager
from quentin.tools.packs.filesystem_pack import FileSystemToolPack


class _DummyCfg:
    provider = "stub"
    name = "stub-model"
    model = "stub-model"


class _DummyRouter:
    def route(self, *args, **kwargs):  # noqa: ANN001, D401
        return _DummyCfg()


def test_json_fallback_ends_step_after_successful_tool_call(tmp_path: Path, monkeypatch) -> None:
    """
    Regression test:
    legacy JSON executor path must end the step after a successful one-shot tool call,
    instead of looping until repeated_tool_call_loop triggers.
    """
    monkeypatch.setenv("LLM_PROVIDER", "stub")
    monkeypatch.setenv("LLM_MODEL", "stub-model")
    monkeypatch.setenv("QUENTIN_LLM_FORCE_STUB", "1")
    monkeypatch.setenv("QUENTIN_TOOL_CALL_PROTOCOLS", "0")  # force legacy JSON mode

    # Filesystem tools resolve repo_root from CWD today.
    monkeypatch.chdir(tmp_path)

    # Ensure PathGuard allows writes in this isolated repo root.
    monkeypatch.setenv("QUENTIN_PATH_GUARD_EXTRA_ALLOWED_ROOTS", "generated")

    tm = ToolManager()
    tm.set_repo_root(str(tmp_path))
    tm.register_pack(FileSystemToolPack())

    ex = SkillExecutor(
        repo_root=str(tmp_path),
        model_router=_DummyRouter(),
        skill_manager=SkillManager(repo_root=tmp_path),
        tool_manager=tm,
    )

    step = {"step_id": "s1", "description": "BENCH_STEP: write_success_file", "skill_id": None, "notes": ""}

    async def _run():
        goal = type("G", (), {"domain": "core", "environment": "sandbox"})()
        return await ex._execute_step(step=step, goal=goal, context={"environment": "sandbox", "session_id": "t"})

    rec = asyncio.run(_run())
    assert rec.success is True
    assert isinstance(rec.result, dict)
    assert rec.result.get("error") != "repeated_tool_call_loop"

    out_path = tmp_path / "generated" / "benchmarks" / "bench_done_marker.txt"
    assert out_path.exists()
    assert "BENCH_DONE" in out_path.read_text(encoding="utf-8", errors="ignore")
