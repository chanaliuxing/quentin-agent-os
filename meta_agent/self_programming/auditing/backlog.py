from typing import List, Dict, Any
from pathlib import Path
import json

from .templates import RequirementStatus


def recommend_next_steps(req: RequirementStatus) -> str:
    missing = req.missing_items
    if any(mi.startswith("missing_file") for mi in missing):
        return "Create module file or fix module_hint."
    if any(mi.startswith("missing_method") for mi in missing):
        return "Implement missing methods."
    if any(mi.startswith("missing_class") for mi in missing):
        return "Implement missing classes."
    if req.status in ("unknown", "partial"):
        return "Add symbols_expected or flesh out implementation."
    return "Review requirement for completeness."


def generate_backlog(results: List[RequirementStatus], top_n: int = 20) -> Dict[str, Any]:
    candidates = [r for r in results if r.status in ("gap", "unknown", "partial")]
    # sort by status severity then confidence ascending (lower confidence first)
    status_order = {"gap": 0, "unknown": 1, "partial": 2}
    candidates.sort(key=lambda r: (status_order.get(r.status, 99), r.confidence, r.req_id))

    backlog_items = []
    for r in candidates[:top_n]:
        backlog_items.append(
            {
                "req_id": r.req_id,
                "status": r.status,
                "confidence": round(r.confidence, 2),
                "missing_items": r.missing_items,
                "recommendation": recommend_next_steps(r),
            }
        )
    return {"items": backlog_items}


def save_backlog(backlog: Dict[str, Any], path: str) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(backlog, ensure_ascii=False, indent=2), encoding="utf-8")
