from __future__ import annotations

from typing import Any, Dict, Optional


def run(inputs: Dict[str, Any], ctx: Optional[Any] = None) -> Dict[str, Any]:
    _ = ctx
    raw = (inputs or {}).get("text")
    text = str(raw or "")
    return {
        "status": "ok",
        "output": {
            "original": text,
            "length": len(text),
            "tokens": [t for t in text.replace("\n", " ").split(" ") if t],
        },
    }

