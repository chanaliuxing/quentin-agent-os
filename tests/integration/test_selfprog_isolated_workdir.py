from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from meta_agent.self_programming.engine_v2 import (
    CouncilDecision,
    GapLike,
    SelfProgrammingConfig,
    SelfProgrammingEngineV2,
)
from meta_agent.tools.coder.base import CodeGenerationResult


def test_selfprog_isolated_workdir_does_not_modify_main_repo(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    target = tmp_path / "sample.py"
    target.write_text("value = 1\n", encoding="utf-8")

    gap = GapLike(
        id="gap1",
        title="Update sample",
        description="Change value to 2",
        category="core",
        priority=1,
        target_file="sample.py",
    )

    cfg = SelfProgrammingConfig(
        enable_research=False,
        allow_auto_apply=False,
        proposal_only=True,
        isolated_workdir=True,
    )
    engine = SelfProgrammingEngineV2(config=cfg)

    def _fake_generate(*_args: Any, **_kwargs: Any) -> CodeGenerationResult:
        payload = {
            "implementation_code": "value = 2\n",
            "verification_test_code": "def test_ok():\n    assert True\n",
        }
        return CodeGenerationResult(success=True, code=json.dumps(payload))

    async def _fake_council(*_args: Any, **_kwargs: Any) -> CouncilDecision:
        return CouncilDecision(should_apply=True, risk_level="low", reason="ok")

    monkeypatch.setattr(engine, "_generate_code_for_gap", _fake_generate)
    monkeypatch.setattr(engine, "_run_static_checks", lambda *_args, **_kwargs: (True, ""))
    monkeypatch.setattr(engine.test_runner, "run_in_sandbox", lambda *_args, **_kwargs: {"success": True, "stdout": "", "stderr": ""})
    monkeypatch.setattr(engine._council, "decide_on_patch", _fake_council)

    engine.run_for_gaps([gap], backend="dummy")

    assert target.read_text(encoding="utf-8") == "value = 1\n"
    patches = Path("data") / "patches.json"
    assert patches.exists()
