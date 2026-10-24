from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Dict, Any, Tuple, List, Optional, Iterable
from quentin.tools.schemas import ToolSpec

class ToolPack(ABC):
    """
    OpenClaw-style ToolPack: A collection of logically related tools.
    """
    @property
    @abstractmethod
    def domain(self) -> str:
        """The namespace for this pack (e.g. 'fs', 'shell')."""
        pass

    @abstractmethod
    def get_tools(self) -> List[Tuple[ToolSpec, Any]]:
        """Returns a list of (Spec, Handler) pairs."""
        pass

class ToolPackRegistry:
    """
    Registry for managing pluggable tool pack bootstrapping.

    Supports two pack shapes:
    1) Bootstrap packs (preferred): {id, priority, enabled(container), register(tool_manager, repo_root, container)}
    2) Legacy ToolPack: {domain, get_tools()} which is registered via ToolManager.register_pack().
    """
    def __init__(self, container: Any = None) -> None:
        self.container = container
        self._packs: Dict[str, Any] = {}

    def register(self, pack: Any) -> None:
        pack_id = getattr(pack, "id", None) or getattr(pack, "domain", None) or type(pack).__name__
        self._packs[str(pack_id)] = pack

    def list_ids(self) -> List[str]:
        def _priority(p: Any) -> int:
            try:
                return int(getattr(p, "priority", 0) or 0)
            except Exception:
                return 0

        items = sorted(self._packs.items(), key=lambda kv: (-_priority(kv[1]), str(kv[0])))
        return [k for k, _ in items]

    @dataclass(frozen=True)
    class PackRunReport:
        pack_id: str
        reason: str = "ok"

    def run(self, tool_manager: Any, repo_root: Any, container: Any) -> Any:
        """
        Bootstrap all registered packs into the tool manager.
        """
        reports: List[ToolPackRegistry.PackRunReport] = []
        for pack_id in self.list_ids():
            pack = self._packs[pack_id]
            try:
                enabled_fn = getattr(pack, "enabled", None)
                if callable(enabled_fn) and not bool(enabled_fn(container=container)):
                    reports.append(ToolPackRegistry.PackRunReport(pack_id=pack_id, reason="disabled"))
                    continue

                reg_fn = getattr(pack, "register", None)
                if callable(reg_fn):
                    reg_fn(tool_manager=tool_manager, repo_root=repo_root, container=container)
                elif isinstance(pack, ToolPack):
                    tool_manager.register_pack(pack)
                else:
                    raise TypeError(f"unknown pack type: {pack!r}")
                reports.append(ToolPackRegistry.PackRunReport(pack_id=pack_id, reason="ok"))
            except Exception as e:
                reports.append(ToolPackRegistry.PackRunReport(pack_id=pack_id, reason=f"error:{e}"))
        return reports

    def load_bootstrap_hooks_from_env(self) -> None:
        # Placeholder for future: allow env-driven pack injection.
        return
