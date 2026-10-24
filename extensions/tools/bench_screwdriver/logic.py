from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, Optional


def _stable_hash(obj: Any) -> str:
    try:
        s = json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    except Exception:
        s = repr(obj)
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:16]


def _infer_mode(task: str) -> str:
    t = (task or "").lower()
    cut_tokens = ("cut", "open", "tape", "package", "seal", "slice")
    screw_tokens = ("screw", "tighten", "loosen", "unscrew", "bolt", "fasten")
    if any(x in t for x in cut_tokens) and not any(x in t for x in screw_tokens):
        return "cut"
    if any(x in t for x in screw_tokens) and not any(x in t for x in cut_tokens):
        return "screw"
    # Ambiguous: default to "screw" as the canonical use.
    return "screw"


def run(payload: Dict[str, Any], ctx: Optional[Any] = None) -> Dict[str, Any]:
    _ = ctx
    task = str((payload or {}).get("task") or "").strip()
    target = (payload or {}).get("target")
    mode = str((payload or {}).get("mode") or "auto").strip().lower() or "auto"
    if not task:
        return {"status": "error", "error": "missing_task"}
    if mode not in {"auto", "screw", "cut"}:
        return {"status": "error", "error": f"invalid_mode:{mode}"}
    resolved_mode = _infer_mode(task) if mode == "auto" else mode

    out = {
        "tool": "bench.screwdriver",
        "mode": resolved_mode,
        "task": task,
        "target": str(target) if target is not None else None,
        "result": {
            "action": "rotate" if resolved_mode == "screw" else "slice",
            "note": "deterministic_benchmark_output",
        },
        "fingerprint": _stable_hash({"task": task, "target": target, "mode": resolved_mode}),
    }
    return {"status": "ok", "result": out}

