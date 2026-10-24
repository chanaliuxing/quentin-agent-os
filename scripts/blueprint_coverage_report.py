# scripts/blueprint_coverage_report.py
import json
from pathlib import Path
from typing import List

from meta_agent.blueprint.coverage import (
    BlueprintCoverageAnalyzer,
    BlueprintIndexItem,
)
from meta_agent.observability.service import ObservabilityService


def load_blueprint_index(path: str | Path = "blueprint/meta_agent_v3.yaml") -> List[BlueprintIndexItem]:
    """
    Best-effort blueprint index loader.

    Notes:
    - The coverage analyzer works on an index of section_ids.
    - We always include a small canonical set of section_ids used by current collectors.
    - If the YAML blueprint is available, we append additional items for visibility.
    """
    base = [
        BlueprintIndexItem("memory.fabric", "memory.fabric", "Memory Fabric"),
        BlueprintIndexItem("skills.mining", "skills.mining", "Skill Mining & Promotion"),
        BlueprintIndexItem("patchflow.core", "patchflow.core", "PatchFlow Core Pipeline"),
    ]

    try:
        import yaml  # type: ignore

        p = Path(path)
        if not p.exists():
            return base
        raw = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        layers = raw.get("layers") or []
        extra: List[BlueprintIndexItem] = []
        for layer in layers:
            lid = layer.get("id")
            lname = layer.get("name") or lid
            modules = layer.get("modules") or []
            for m in modules:
                mid = m.get("id")
                if not mid:
                    continue
                sec_id = f"{lid}.{mid}"
                extra.append(BlueprintIndexItem(sec_id, sec_id, f"{lname}: {mid}"))
        # Deduplicate by section_id while preserving order.
        seen = set()
        out: List[BlueprintIndexItem] = []
        for item in [*base, *extra]:
            if item.section_id in seen:
                continue
            seen.add(item.section_id)
            out.append(item)
        return out
    except Exception:
        return base


def main() -> None:
    obs = ObservabilityService()
    snapshot_obj = obs.build_snapshot()
    snapshot = snapshot_obj.to_dict() if hasattr(snapshot_obj, "to_dict") else dict(snapshot_obj)

    index = load_blueprint_index()

    analyzer = BlueprintCoverageAnalyzer()
    report = analyzer.build_report(index, snapshot)

    print("Generated at:", report.generated_at)
    print("Summary:", json.dumps(report.summary.to_dict(), ensure_ascii=False, indent=2))
    print("\nTop sections with gaps/open_items:")
    sections_sorted = sorted(
        report.sections,
        key=lambda s: (-(s.open_gaps + s.open_todos)),
    )
    for s in sections_sorted[:10]:
        print(
            f"- {s.path} [{s.level}] gaps={s.open_gaps} todos={s.open_todos} "
            f"impl={s.impl_present} tested={s.tested} self_evo={s.self_evolving}"
        )


if __name__ == "__main__":
    main()
