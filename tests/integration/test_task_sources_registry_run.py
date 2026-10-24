from __future__ import annotations

import os

import pytest

from quentin.runtime.task_sources import run_task_sources_once


@pytest.mark.asyncio
async def test_task_sources_registry_mode_emits_per_source_reports(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "data").mkdir(parents=True, exist_ok=True)
    (tmp_path / "data" / "tasks").mkdir(parents=True, exist_ok=True)

    os.environ["QUENTIN_TASK_SOURCES_REGISTRY"] = "1"
    os.environ["QUENTIN_TASK_SOURCE_BLUEPRINT"] = "0"
    os.environ["QUENTIN_TASK_SOURCE_PATCHFLOW"] = "0"
    os.environ["QUENTIN_TASK_SOURCE_OBS"] = "0"

    report = await run_task_sources_once(repo_root=".")
    assert report.enqueued == 0
    assert len(report.sources) >= 3
    ids = {s.source_id for s in report.sources}
    assert {"blueprint", "patchflow", "obs"}.issubset(ids)
    for s in report.sources:
        if s.source_id in {"blueprint", "patchflow", "obs"}:
            assert s.reason in {"disabled", "cooldown", "budget_exhausted", "no_candidates", "error"}

