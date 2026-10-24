from __future__ import annotations
from dataclasses import is_dataclass, fields
from typing import Any, Dict, List, Set, Optional

_DROP_KEYS = {"cancel_token", "trace_recorder"}


def make_jsonable(
    x: Any,
    *,
    max_depth: int = 10,
    max_items: int = 200,
    max_str: int = 4000,
    _seen: Optional[Set[int]] = None,
    _depth: int = 0,
) -> Any:
    """
    Recursively converts an object into a JSON-serializable structure.
    Handles dataclasses, dicts, lists, and basic types.

    Safety features:
    - Cycle detection (prevents recursion overflow)
    - Depth/size limits (prevents giant payloads)
    - Drop known problematic keys (e.g. cancel tokens, trace recorder objects)
    """
    if _seen is None:
        _seen = set()
    if _depth > max(1, int(max_depth)):
        return {"type": "max_depth", "repr": repr(x)[:200]}

    if x is None:
        return None
    if isinstance(x, (str, int, float, bool)):
        if isinstance(x, str) and len(x) > max_str:
            return x[: max(0, max_str - 20)] + f"...<truncated {len(x)} chars>"
        return x

    obj_id = id(x)
    if obj_id in _seen:
        return {"type": "cycle", "repr": repr(x)[:200]}
    _seen.add(obj_id)

    if isinstance(x, dict):
        out: Dict[str, Any] = {}
        for idx, (k, v) in enumerate(x.items()):
            if idx >= max_items:
                out["..."] = f"<truncated {len(x)} items>"
                break
            ks = str(k)
            if ks in _DROP_KEYS:
                continue
            out[ks] = make_jsonable(
                v,
                max_depth=max_depth,
                max_items=max_items,
                max_str=max_str,
                _seen=_seen,
                _depth=_depth + 1,
            )
        return out
    if isinstance(x, list):
        out_list: List[Any] = []
        for idx, v in enumerate(x):
            if idx >= max_items:
                out_list.append(f"<truncated {len(x)} items>")
                break
            out_list.append(
                make_jsonable(
                    v,
                    max_depth=max_depth,
                    max_items=max_items,
                    max_str=max_str,
                    _seen=_seen,
                    _depth=_depth + 1,
                )
            )
        return out_list
    if is_dataclass(x):
        try:
            # Avoid dataclasses.asdict(): it deep-copies unknown objects in nested dicts/lists,
            # which can explode or recurse (e.g. ToolCallResult, trace recorders).
            out: Dict[str, Any] = {}
            for f in fields(x):
                name = str(getattr(f, "name", "") or "")
                if not name or name in _DROP_KEYS:
                    continue
                out[name] = make_jsonable(
                    getattr(x, name),
                    max_depth=max_depth,
                    max_items=max_items,
                    max_str=max_str,
                    _seen=_seen,
                    _depth=_depth + 1,
                )
            return out
        except Exception:
            pass
    if hasattr(x, "to_dict"):
        try:
            return make_jsonable(
                x.to_dict(),
                max_depth=max_depth,
                max_items=max_items,
                max_str=max_str,
                _seen=_seen,
                _depth=_depth + 1,
            )
        except Exception:
            pass
    if hasattr(x, "__dict__"):
        try:
            data = {k: v for k, v in vars(x).items() if str(k) not in _DROP_KEYS}
            if not data:
                return {"type": x.__class__.__name__, "repr": repr(x)[:2000]}
            return make_jsonable(
                data,
                max_depth=max_depth,
                max_items=max_items,
                max_str=max_str,
                _seen=_seen,
                _depth=_depth + 1,
            )
        except Exception:
            pass
    return {"type": x.__class__.__name__, "repr": repr(x)[:2000]}
