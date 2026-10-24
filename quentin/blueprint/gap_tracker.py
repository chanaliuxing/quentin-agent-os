from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional
import json

from quentin.blueprint.spec import BlueprintSpec, BlueprintCapability
from quentin.utils.time import now_iso


@dataclass
class CapabilityStatus:
    """
    当前系统对某个蓝皮书能力的实现状态。

    status:
      - "unknown": 未评估
      - "missing": 明确没有实现
      - "partial": 部分实现
      - "done": 已实现（满足 v1 要求）
    """
    capability_id: str
    status: str = "unknown"
    evidence: Optional[str] = None
    last_update_ts: str = ""
    notes: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> CapabilityStatus:
        return CapabilityStatus(
            capability_id=data["capability_id"],
            status=data.get("status", "unknown"),
            evidence=data.get("evidence"),
            last_update_ts=data.get("last_update_ts", ""),
            notes=data.get("notes"),
        )


class CapabilitiesRegistry:
    """
    能力状态注册表：cap_id -> CapabilityStatus。

    持久化在 data/blueprint/capabilities.json 里，
    方便人工或 LLM 工具链更新“我们做到哪儿了”。
    """

    def __init__(self, *, repo_root: str | Path = ".") -> None:
        self.repo_root = Path(repo_root).resolve()
        self.storage_path = self.repo_root / "data" / "blueprint" / "capabilities.json"
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)

        self._items: Dict[str, CapabilityStatus] = {}
        self._load()

    def _load(self) -> None:
        if not self.storage_path.exists():
            return
        try:
            with self.storage_path.open("r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            return
        for item in data.get("capabilities", []):
            try:
                status = CapabilityStatus.from_dict(item)
                self._items[status.capability_id] = status
            except Exception:
                continue

    def _save(self) -> None:
        data = {
            "capabilities": [s.to_dict() for s in self._items.values()],
        }
        tmp = self.storage_path.with_suffix(".tmp")
        with tmp.open("w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        tmp.replace(self.storage_path)

    # --------------------------------------------------
    # 对外 API
    # --------------------------------------------------
    def get(self, capability_id: str) -> Optional[CapabilityStatus]:
        return self._items.get(capability_id)

    def set_status(
        self,
        capability_id: str,
        status: str,
        *,
        evidence: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> CapabilityStatus:
        """
        手动/自动更新某个能力的状态。
        """
        now = now_iso()
        cs = self._items.get(capability_id) or CapabilityStatus(
            capability_id=capability_id,
        )
        cs.status = status
        cs.evidence = evidence
        cs.notes = notes
        cs.last_update_ts = now
        self._items[capability_id] = cs
        self._save()
        return cs

    def export(self) -> Dict[str, Any]:
        return {
            "capabilities": [s.to_dict() for s in self._items.values()],
        }


@dataclass
class CapabilityGap:
    """
    单条能力的“差距视图”：蓝皮书定义 + 当前实现状态。
    """
    capability: BlueprintCapability
    status: CapabilityStatus

    @property
    def gap_status(self) -> str:
        """
        用一个统一的 gap 标签：
          - "missing": 未实现但 required=True
          - "partial": 部分实现
          - "ok": 已实现
          - "unknown": 没有状态记录
        """
        s = self.status.status
        if s == "done":
            return "ok"
        if s == "partial":
            return "partial"
        if s == "missing":
            return "missing"
        return "unknown"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "capability": self.capability.to_dict(),
            "status": self.status.to_dict(),
            "gap_status": self.gap_status,
        }


@dataclass
class BlueprintGapReport:
    """
    蓝皮书整体 diff 报告。

    按 gap_status 分类列出所有能力项，并统计数量。
    """
    spec_version: str
    missing: List[CapabilityGap]
    partial: List[CapabilityGap]
    ok: List[CapabilityGap]
    unknown: List[CapabilityGap]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "spec_version": self.spec_version,
            "missing": [g.to_dict() for g in self.missing],
            "partial": [g.to_dict() for g in self.partial],
            "ok": [g.to_dict() for g in self.ok],
            "unknown": [g.to_dict() for g in self.unknown],
            "stats": {
                "missing": len(self.missing),
                "partial": len(self.partial),
                "ok": len(self.ok),
                "unknown": len(self.unknown),
            },
        }

# Compatibility alias for older imports
BlueprintScanReport = BlueprintGapReport


class BlueprintGapTracker:
    """
    蓝皮书差距追踪器：

      - 输入：BlueprintSpec + CapabilitiesRegistry
      - 输出：BlueprintGapReport（哪些已实现、缺失、部分实现）

    未来你可以：
      - 用一个 LLM agent 去扫描代码/文件，自动更新 CapabilitiesRegistry，
        再用这个 tracker 做“总结”。
    """

    def __init__(
        self,
        *,
        spec: BlueprintSpec,
        registry: CapabilitiesRegistry,
        # Added repo_root and spec_path arguments to maintain compatibility with previous usage in run_self_evolution_cycle.py
        repo_root: Optional[Any] = None,
        spec_path: Optional[Any] = None,
    ) -> None:
        self.spec = spec
        self.registry = registry
        # If repo_root/spec_path provided but not used here, we just ignore or store if needed in future.
        # The previous implementation loaded spec from file. This new one takes spec object. 
        # But wait, run_self_evolution_cycle.py calls BlueprintImprover which creates a GapTracker.
        # BlueprintImprover.__init__ in 100.md creates GapTracker(repo_root=...).
        # GapTracker.__init__ in 98.md took repo_root and spec_path.
        # This new implementation takes spec and registry objects.
        # I must ensure compatibility or update BlueprintImprover.
        # Since I'm overwriting gap_tracker.py, I should probably include the loading logic from 98.md OR update BlueprintImprover in the next step.
        # But I am instructed to use this file.
        # To avoid breaking the existing BlueprintImprover which instantiates GapTracker with repo_root, 
        # I will adapt __init__ to load default spec and registry if not provided, using repo_root.
        
        if repo_root:
            self.repo_root = Path(repo_root).resolve()
        else:
            self.repo_root = Path(".")
            
        if self.spec is None:
             # Fallback to loading default spec if not provided
             from quentin.blueprint.spec import load_default_spec_v3
             self.spec = load_default_spec_v3()
             
        if self.registry is None:
             # Fallback to creating registry from repo_root
             self.registry = CapabilitiesRegistry(repo_root=self.repo_root)

    def scan(self) -> BlueprintGapReport:
        missing: List[CapabilityGap] = []
        partial: List[CapabilityGap] = []
        ok: List[CapabilityGap] = []
        unknown: List[CapabilityGap] = []

        for cap in self.spec.capabilities:
            cs = self.registry.get(cap.id) or CapabilityStatus(
                capability_id=cap.id,
                status="unknown",
                evidence=None,
                last_update_ts="",
                notes=None,
            )
            gap = CapabilityGap(capability=cap, status=cs)
            gs = gap.gap_status

            if gs == "ok":
                ok.append(gap)
            elif gs == "partial":
                partial.append(gap)
            elif gs == "missing":
                # 只统计 required=True 的 missing，非 required 可以放到 partial/unknown
                if cap.required:
                    missing.append(gap)
                else:
                    partial.append(gap)
            else:
                unknown.append(gap)

        return BlueprintGapReport(
            spec_version=self.spec.version,
            missing=missing,
            partial=partial,
            ok=ok,
            unknown=unknown,
        )
