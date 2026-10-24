# meta_agent/blueprint/store.py
from __future__ import annotations
from pathlib import Path
import json
import datetime as dt
from typing import List, Dict, Any, Optional

from meta_agent.blueprint.coverage import BlueprintCoverageReport, BlueprintCoverageSummary, SectionCoverage # Assuming these are defined elsewhere


class BlueprintCoverageStore:
    def __init__(
        self,
        current_path: str | Path = "data/blueprint/coverage_report.json",
        history_dir: str | Path = "data/blueprint/coverage_history",
    ) -> None:
        self.current_path = Path(current_path)
        self.history_dir = Path(history_dir)
        self.history_dir.mkdir(parents=True, exist_ok=True)
        self.current_path.parent.mkdir(parents=True, exist_ok=True)

    def save_current(self, report: BlueprintCoverageReport) -> None:
        data = report.to_dict()
        self.current_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        ts = report.generated_at.replace(":", "-").replace(".", "-") # Adjust for file naming
        fname = f"coverage_{ts}.json"
        hist_path = self.history_dir / fname
        hist_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def load_current(self) -> Optional[BlueprintCoverageReport]:
        if not self.current_path.exists():
            return None
        data = json.loads(self.current_path.read_text(encoding="utf-8"))
        return self._report_from_dict(data)

    def list_history_summaries(self, limit: int = 100) -> List[Dict[str, Any]]:
        items: List[Dict[str, Any]] = []
        for p in sorted(self.history_dir.glob("coverage_*.json"), key=lambda x: x.name, reverse=True): # Sort by filename for recency
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                continue
            ts = data.get("generated_at") or self._ts_from_name(p.name)
            summary = data.get("summary", {})
            items.append(
                {
                    "generated_at": ts,
                    "summary": summary,
                }
            )

        return items[:limit]

    def _report_from_dict(self, data: Dict[str, Any]) -> BlueprintCoverageReport:
        # Assuming coverage classes are defined
        summary = BlueprintCoverageSummary(**data["summary"])
        sections = [SectionCoverage(**s) for s in data.get("sections", [])]
        return BlueprintCoverageReport(
            generated_at=data["generated_at"],
            summary=summary,
            sections=sections,
        )

    def _ts_from_name(self, name: str) -> str:
        try:
            base = name[len("coverage_") : -len(".json")]
            return base.replace("-", ":", 2)
        except Exception:
            return dt.datetime.utcfromtimestamp(Path(name).stat().st_mtime).isoformat()
