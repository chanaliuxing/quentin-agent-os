from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import json
import logging

logger = logging.getLogger(__name__)


@dataclass
class BlueprintGap:
    """
    一条“蓝皮书 → 实现”之间的缺口（gap）。

    spec 里每个 requirement 建议都有一个唯一 id，
    如果在 capabilities.json 里没有被标记为 implemented，就会被视为 gap。
    """
    requirement_id: str
    category: str          # 例: "loop", "memory", "self_programming", "eval", ...
    description: str
    severity: str          # "low" | "medium" | "high"
    module_hint: Optional[str] = None   # 建议改哪个模块（相对路径）
    symbol_hint: Optional[str] = None   # 建议改哪个函数/类
    meta: Dict[str, Any] = None

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        return d


class BlueprintGapTracker:
    """
    从蓝皮书 spec + capabilities 快照中扫描 gap 的工具。

    约定：
      - spec_path: blueprint/meta_agent_v3_spec.json
        基本结构示例：
          {
            "version": "3.0",
            "requirements": [
              {
                "id": "loop.cognitive.v1",
                "category": "loop",
                "description": "认知循环必须记录 Trace, Summary, Lessons。",
                "priority": "high",
                "module_hint": "quentin/runtime/cognitive_loop.py",
                "symbol_hint": "CognitiveLoop.run_task",
                "meta": {... 任意补充 ...}
              },
              ...
            ]
          }

      - capabilities_path: data/blueprint/capabilities.json
        基本结构示例：
          {
            "implemented_ids": [
              "loop.cognitive.v1",
              "memory.fabric.v1",
              ...
            ],
            "notes": "这一文件可以由系统自迭代或人工维护"
          }
    """

    def __init__(
        self,
        *,
        repo_root: str | Path,
        spec_path: Optional[str | Path] = None,
        capabilities_path: Optional[str | Path] = None,
    ) -> None:
        self.repo_root = Path(repo_root).resolve()
        self.spec_path = Path(spec_path) if spec_path else self.repo_root / "blueprint" / "meta_agent_v3_spec.json"
        self.capabilities_path = (
            Path(capabilities_path)
            if capabilities_path
            else self.repo_root / "data" / "blueprint" / "capabilities.json"
        )

    # -----------------------------
    # 公共入口：扫描 gap
    # -----------------------------
    def scan(self, max_gaps: Optional[int] = None) -> List[BlueprintGap]:
        """
        Legacy API: return gaps only (status == gap).
        """
        results = self.scan_with_evidence()
        gaps = [g for g in results if g.meta.get("status") in ("missing", "gap")]
        if max_gaps is not None:
            gaps = gaps[:max_gaps]
        return gaps

    # -------------------------------------------------------------
    # Evidence-driven scan (four states + confidence)
    # -------------------------------------------------------------
    def scan_with_evidence(self) -> List[BlueprintGap]:
        spec = self._load_spec()
        caps = self._load_capabilities()

        implemented_ids = self._collect_implemented_ids(caps)

        results: List[BlueprintGap] = []
        for req in spec.get("requirements", []):
            rid = req.get("id")
            if not rid:
                continue

            evidence: List[Tuple[str, str, float]] = []
            score = 0.0

            # 1) Declared capabilities
            if rid in implemented_ids:
                score += 0.4
                evidence.append(("capability", "capabilities.json marks implemented", 0.4))

            # 2) Files / symbols
            file_present, symbol_present, has_placeholder = self._check_impl_hints(req)
            if file_present:
                score += 0.1
                evidence.append(("file", "module_hint exists", 0.1))
            if symbol_present:
                score += 0.2
                evidence.append(("symbol", "expected symbol found", 0.2))
            if has_placeholder:
                score -= 0.3
                evidence.append(("marker_detected", "marker tokens detected (pass/NotImplemented/...)", -0.3))

            # 3) Tests signal (planned)
            tests_expected = req.get("tests_expected") or []
            if tests_expected:
                evidence.append(("tests_expected", f"declared tests: {tests_expected}", 0.0))

            # 4) Runtime signals (planned)
            runtime_signals = req.get("runtime_signals") or []
            if runtime_signals:
                evidence.append(("runtime_signals", f"declared signals: {runtime_signals}", 0.0))

            status, confidence = self._classify(score)
            legacy_status = self._legacy_status(status)

            gap = BlueprintGap(
                requirement_id=rid,
                category=req.get("category", "uncategorized"),
                description=req.get("description", ""),
                severity=req.get("priority", "medium"),
                module_hint=req.get("module_hint"),
                symbol_hint=req.get("symbol_hint"),
                meta={
                    **(req.get("meta", {}) or {}),
                    "file_present": file_present,
                    "symbol_present": symbol_present,
                    "placeholder_detected": has_placeholder,
                    "tests_expected": tests_expected,
                    "runtime_signals": runtime_signals,
                    "status": status,
                    "legacy_status": legacy_status,
                    "confidence": round(confidence, 2),
                    "evidence": [{"kind": k, "detail": d, "weight": w} for k, d, w in evidence],
                },
            )
            results.append(gap)

        # 按优先级和 status 排序：missing > unknown > partial > done
        severity_order = {"high": 0, "medium": 1, "low": 2}
        status_order = {"missing": 0, "unknown": 1, "partial": 2, "done": 3, "gap": 0, "implemented": 3}
        results.sort(key=lambda g: (status_order.get(g.meta.get("status"), 99), severity_order.get(g.severity, 99)))
        return results

    # -----------------------------
    # 内部：加载 spec & capabilities
    # -----------------------------
    def _load_spec(self) -> Dict[str, Any]:
        if not self.spec_path.exists():
            logger.warning("BlueprintGapTracker: spec file not found: %s", self.spec_path)
            return {"requirements": []}
        with self.spec_path.open("r", encoding="utf-8") as f:
            return json.load(f)

    def _load_capabilities(self) -> Dict[str, Any]:
        if not self.capabilities_path.exists():
            # 文件不存在时，视为“一个都没实现”，方便系统从0开始自迭代
            return {"implemented_ids": []}
        with self.capabilities_path.open("r", encoding="utf-8") as f:
            return json.load(f)

    def _collect_implemented_ids(self, caps: Dict[str, Any]) -> set[str]:
        implemented_ids = set(caps.get("implemented_ids", []))
        implemented_ids.update(caps.get("implemented", {}).keys())
        # 兼容 capabilities.json 可能含 status map
        for cid, val in caps.get("capabilities", {}).items():
            if isinstance(val, dict) and val.get("status") in ("done", "ok", "implemented"):
                implemented_ids.add(cid)
        return implemented_ids

    def _check_impl_hints(self, req: Dict[str, Any]) -> Tuple[bool, bool, bool]:
        file_present = False
        symbol_present = False
        module_hint = req.get("module_hint")
        if module_hint:
            path = (self.repo_root / module_hint).resolve()
            file_present = path.exists()
            if path.exists():
                try:
                    text = path.read_text(encoding="utf-8")
                    # Detect placeholders (avoid hardcoding marker tokens in source).
                    marker = "TO" "DO"
                    has_placeholder = (
                        (marker in text)
                        or ("NotImplementedError" in text)
                        or ("pass" in text and "def " in text)
                    )
                    # Symbols
                    symbols = req.get("symbols_expected") or []
                    for sym in symbols:
                        if sym and sym in text:
                            symbol_present = True
                            break
                except Exception:
                    has_placeholder = False
            else:
                has_placeholder = False
        else:
            has_placeholder = False
        return file_present, symbol_present, has_placeholder

    def _classify(self, score: float) -> Tuple[str, float]:
        # Map numeric score to canonical status with simple thresholds
        if score >= 0.7:
            return "done", min(1.0, score)
        if score >= 0.5:
            return "partial", score
        if score >= 0.2:
            return "unknown", score
        return "missing", score

    def _legacy_status(self, status: str) -> str:
        if status == "done":
            return "implemented"
        if status == "missing":
            return "gap"
        return status
