import json
from typing import List, Dict, Any
from pathlib import Path
from .templates import RequirementStatus


def load_report(path: str) -> Dict[str, Any]:
    p = Path(path)
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def compute_delta(prev_report: Dict[str, Any], current_results: List[RequirementStatus]) -> Dict[str, Any]:
    prev_map = {d.get("req_id"): d for d in prev_report.get("details", [])} if prev_report else {}
    delta_changed = []
    new_gaps = []
    closed_gaps = []

    for cur in current_results:
        pid = cur.req_id
        prev = prev_map.get(pid)
        if not prev:
            continue
        prev_status = prev.get("status")
        if prev_status != cur.status:
            delta_changed.append(
                {
                    "id": pid,
                    "from": prev_status,
                    "to": cur.status,
                    "confidence_delta": round(cur.confidence - prev.get("confidence", 0.0), 2),
                }
            )
        if prev_status != "gap" and cur.status == "gap":
            new_gaps.append(pid)
        if prev_status == "gap" and cur.status != "gap":
            closed_gaps.append(pid)

    return {
        "status_changed": sorted(delta_changed, key=lambda x: x["id"]),
        "new_gaps": sorted(new_gaps),
        "closed_gaps": sorted(closed_gaps),
    }
