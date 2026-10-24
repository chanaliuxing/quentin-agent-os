from __future__ import annotations

import os
from pathlib import Path

from quentin.bootstrap.container import Container


def test_container_tool_packs_smoke_registers_core_tools(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("QUENTIN_TOOL_PACKS_ENABLED", "1")
    c = Container(repo_root=tmp_path)
    tm = c.tool_manager
    assert tm.get("fs.write_file") is not None
    assert tm.get("shell.run_command") is not None
    assert tm.get("shell.interactive") is not None
    assert tm.get("memory-recall") is not None

