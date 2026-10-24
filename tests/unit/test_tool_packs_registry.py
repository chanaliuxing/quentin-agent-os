from __future__ import annotations

from dataclasses import dataclass

import pytest

from quentin.tools.packs.base import ToolPackRegistry


@dataclass(frozen=True)
class _Pack:
    id: str
    priority: int
    on: bool = True

    def enabled(self, *, container) -> bool:
        return bool(self.on)

    def register(self, *, tool_manager, repo_root, container) -> None:
        tool_manager.append(self.id)


def test_tool_pack_registry_orders_by_priority_and_id() -> None:
    reg = ToolPackRegistry()
    reg.register(_Pack(id="b", priority=10))
    reg.register(_Pack(id="a", priority=10))
    reg.register(_Pack(id="z", priority=100))
    assert reg.list_ids() == ["z", "a", "b"]


def test_tool_pack_registry_skips_disabled_packs() -> None:
    reg = ToolPackRegistry()
    reg.register(_Pack(id="on", priority=0, on=True))
    reg.register(_Pack(id="off", priority=10, on=False))

    tool_manager: list[str] = []
    reports = reg.run(tool_manager=tool_manager, repo_root=".", container=object())
    assert tool_manager == ["on"]
    assert {r.pack_id: r.reason for r in reports}["off"] == "disabled"

