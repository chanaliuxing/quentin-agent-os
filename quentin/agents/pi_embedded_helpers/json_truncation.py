from __future__ import annotations

import json
from typing import Any


def truncate_json_text(text: str, *, max_chars: int = 4000) -> str:
    s = str(text or "")
    if len(s) <= max_chars:
        return s
    try:
        data = json.loads(s)
    except Exception:
        keep = max(200, max_chars // 2)
        return s[:keep] + f"\n...[TRUNCATED {len(s)-2*keep} CHARS]...\n" + s[-keep:]
    return truncate_json_obj(data, max_chars=max_chars)


def truncate_json_obj(obj: Any, *, max_chars: int = 4000) -> str:
    try:
        dumped = json.dumps(obj, ensure_ascii=False, indent=2, default=str)
    except Exception:
        dumped = str(obj)
    if len(dumped) <= max_chars:
        return dumped

    if isinstance(obj, dict):
        compact = {}
        for i, (k, v) in enumerate(obj.items()):
            if i >= 20:
                compact["..."] = f"<truncated {len(obj) - 20} keys>"
                break
            compact[str(k)] = v
        return json.dumps(compact, ensure_ascii=False, indent=2, default=str)
    if isinstance(obj, list):
        head = obj[:5]
        tail = obj[-3:] if len(obj) > 8 else []
        out = head + ([f"... <truncated {max(0, len(obj)-8)} items> ..."] if len(obj) > 8 else []) + tail
        return json.dumps(out, ensure_ascii=False, indent=2, default=str)

    keep = max(200, max_chars // 2)
    return dumped[:keep] + f"\n...[TRUNCATED {len(dumped)-2*keep} CHARS]...\n" + dumped[-keep:]

