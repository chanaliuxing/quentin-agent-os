from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate memory online/offline runtime tier boundary config.")
    parser.add_argument("--config", default="config/memory_runtime_tiers.json")
    args = parser.parse_args()

    path = Path(str(args.config))
    if not path.is_absolute():
        repo_root = Path(__file__).resolve().parent.parent
        path = (repo_root / path).resolve()
    if not path.exists():
        print({"status": "not_ready", "reason": "missing_config", "path": str(path)})
        return 2

    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:  # noqa: BLE001
        print({"status": "not_ready", "reason": f"invalid_json:{e}", "path": str(path)})
        return 3

    online = obj.get("online") if isinstance(obj, dict) else {}
    offline = obj.get("offline") if isinstance(obj, dict) else {}
    try:
        online_max = int((online or {}).get("max_records"))
        offline_min = int((offline or {}).get("min_records"))
        active_days = int((online or {}).get("active_window_days"))
    except Exception:
        print({"status": "not_ready", "reason": "invalid_numeric_fields", "path": str(path)})
        return 4

    ok = True
    reasons: list[str] = []
    if online_max <= 0:
        ok = False
        reasons.append("online.max_records<=0")
    if offline_min <= online_max:
        ok = False
        reasons.append("offline.min_records<=online.max_records")
    if active_days <= 0:
        ok = False
        reasons.append("online.active_window_days<=0")

    print(
        {
            "status": "ok" if ok else "not_ready",
            "path": str(path),
            "online_max_records": online_max,
            "offline_min_records": offline_min,
            "active_window_days": active_days,
            "reasons": reasons,
        }
    )
    return 0 if ok else 5


if __name__ == "__main__":
    raise SystemExit(main())
