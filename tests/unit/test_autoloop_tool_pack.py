from __future__ import annotations

from pathlib import Path

from quentin.tools.autoloop import autoloop_run
from quentin.tools.packs.autoloop_pack import AutoloopToolPack


def test_autoloop_pack_registers_run_tool() -> None:
    pack = AutoloopToolPack()
    names = [spec.name for spec, _ in pack.get_tools()]
    assert "autoloop.run" in names


def test_autoloop_run_dry_run_returns_command() -> None:
    out = autoloop_run({"prd_path": "blueprint.md", "dry_run": True})
    assert out.get("status") == "ok"
    assert out.get("dry_run") is True
    assert isinstance(out.get("command"), list)
    assert "app.main" in " ".join([str(x) for x in out.get("command", [])])


def test_autoloop_run_errors_on_missing_prd() -> None:
    out = autoloop_run({"prd_path": str(Path("does_not_exist_prd.md").resolve()), "dry_run": True})
    assert out.get("status") == "error"
    assert out.get("error") == "prd_not_found"
