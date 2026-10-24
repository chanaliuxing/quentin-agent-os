import json
from pathlib import Path
from typing import List

from .templates import RequirementStatus


def update_capabilities_snapshot(results: List[RequirementStatus], path: str, implemented_threshold: float = 0.85) -> None:
    """
    Update or create a capabilities snapshot file from audit results.
    Only marks status implemented for entries meeting threshold and status implemented.
    """
    p = Path(path)
    existing = {}
    if p.exists():
        try:
            existing = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            existing = {}

    caps = existing.get("capabilities", [])
    cap_map = {c.get("id") or c.get("capability_id"): c for c in caps}

    for r in results:
        cid = r.req_id
        if r.status != "implemented" or r.confidence < implemented_threshold:
            continue
        cap_map[cid] = {"id": cid, "status": "implemented", "confidence": r.confidence}

    new_caps = list(cap_map.values())
    payload = {"capabilities": new_caps}
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
