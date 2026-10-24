from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

from quentin.infra.unified_diff import parse_unified_diff


def compute_unified_diff_stats(diff_text: str, *, targets: Optional[Sequence[str]] = None) -> Dict[str, Any]:
    """
    Compute per-file added/removed counts from a unified diff.

    Output schema:
      {
        "path/to/file.py": {"added": int, "removed": int},
        ...
      }

    Notes:
    - If `targets` is provided, counts are limited to patches whose path matches targets.
    - This intentionally does not attempt to infer rename pairs; it uses `new_path or old_path`.
    """
    diff_text = diff_text or ""
    if not diff_text.strip():
        return {}

    targets_set = set(str(t) for t in (targets or []))
    out: Dict[str, Any] = {}
    try:
        patches = parse_unified_diff(diff_text)
    except Exception:
        return {}

    for fp in patches:
        path = fp.new_path or fp.old_path
        if not path:
            continue
        if targets_set and path not in targets_set:
            continue

        added = 0
        removed = 0
        for h in fp.hunks:
            for line in h.lines:
                if not line:
                    continue
                if line.startswith("+") and not line.startswith("+++"):
                    added += 1
                elif line.startswith("-") and not line.startswith("---"):
                    removed += 1

        out[path] = {"added": added, "removed": removed}
    return out
