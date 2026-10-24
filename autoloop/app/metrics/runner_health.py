from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from app.config import settings


DEFAULT_RUNNER_HEALTH: dict[str, Any] = {
    "state_db_fallback_count": 0,
    "session_degraded_count": 0,
    "execution_timeout_count": 0,
    "probe_failure_count": 0,
    "last_event": "",
    "last_event_at": "",
}


def read_runner_health(runtime_dir: Path | None = None) -> dict[str, Any]:
    path = _runner_health_file(runtime_dir=runtime_dir)
    if not path.exists():
        return dict(DEFAULT_RUNNER_HEALTH)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        merged = dict(DEFAULT_RUNNER_HEALTH)
        merged.update(payload)
        return merged
    except Exception:
        return dict(DEFAULT_RUNNER_HEALTH)


def bump_runner_health(metric: str, runtime_dir: Path | None = None) -> dict[str, Any]:
    payload = read_runner_health(runtime_dir=runtime_dir)
    payload[metric] = int(payload.get(metric, 0)) + 1
    payload["last_event"] = metric
    payload["last_event_at"] = datetime.now().isoformat()
    path = _runner_health_file(runtime_dir=runtime_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def _runner_health_file(runtime_dir: Path | None = None) -> Path:
    root = runtime_dir or settings.runtime_dir
    return root / "metrics" / "runner_health.json"

