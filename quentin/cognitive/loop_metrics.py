from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


def extract_attempt_metrics(
    *,
    raw_exec_data: Dict[str, Any],
    attempt_start: datetime | str,
    attempt_end: datetime | str,
) -> Dict[str, Any]:
    """Extract latency/cost/tool-call metrics from executor raw payload."""
    tokens_used = 0.0
    step_latencies: List[float] = []
    tool_calls = 0
    prediction_errors = 0

    def _parse_dt(val: datetime | str) -> Optional[datetime]:
        if isinstance(val, datetime):
            return val
        try:
            return datetime.fromisoformat(str(val))
        except Exception:
            return None

    for step in raw_exec_data.get("steps", []) or []:
        meta = {}
        if isinstance(step, dict):
            res_obj = step.get("result") if isinstance(step.get("result"), dict) else {}
            meta = res_obj.get("meta", {}) if isinstance(res_obj, dict) else {}
            if isinstance(res_obj, dict) and res_obj.get("tool_name"):
                tool_calls += 1
            if isinstance(meta, dict) and meta.get("prediction_error") is not None:
                prediction_errors += 1
            if meta.get("tokens") is not None:
                try:
                    tokens_used += float(meta["tokens"])
                except Exception:
                    pass
            if meta.get("cost_tokens") is not None:
                try:
                    tokens_used += float(meta["cost_tokens"])
                except Exception:
                    pass
            if meta.get("latency_ms") is not None:
                try:
                    step_latencies.append(float(meta["latency_ms"]))
                except Exception:
                    pass
            elif step.get("started_at") and step.get("finished_at"):
                start_dt = _parse_dt(step["started_at"])
                end_dt = _parse_dt(step["finished_at"])
                if start_dt and end_dt:
                    step_latencies.append((end_dt - start_dt).total_seconds() * 1000.0)

    meta = raw_exec_data.get("meta", {}) or {}
    try:
        tokens_used += float(meta.get("tokens_used", 0.0))
    except Exception:
        pass

    meta_latency = meta.get("latency_ms")
    if meta_latency is not None:
        try:
            latency_ms = float(meta_latency)
        except Exception:
            latency_ms = None
    else:
        latency_ms = None

    if latency_ms is None:
        if step_latencies:
            latency_ms = sum(step_latencies)
        else:
            start_dt = _parse_dt(attempt_start)
            end_dt = _parse_dt(attempt_end)
            latency_ms = (
                (end_dt - start_dt).total_seconds() * 1000.0
                if (start_dt and end_dt)
                else 0.0
            )

    return {
        "cost_tokens": tokens_used,
        "latency_ms": latency_ms,
        "step_latencies": step_latencies,
        "tool_calls": tool_calls,
        "prediction_errors": prediction_errors,
        "prediction_error_rate": (prediction_errors / tool_calls) if tool_calls > 0 else 0.0,
    }


def recent_forbidden_actions(*, repo_root: Path, limit: int = 6) -> List[str]:
    """Build a lightweight forbidden-actions cache from recent audit denials/errors."""
    path = repo_root / "data" / "audit_events.jsonl"
    if not path.exists():
        return []
    try:
        lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()[-800:]
    except Exception:
        return []

    out: List[str] = []
    seen: set[str] = set()
    cmd_pattern = re.compile(r"interactive command ['\"]?([a-zA-Z0-9._/-]+)['\"]?")
    known = ("nano", "vim", "vi", "emacs", "wget", "curl", "man", "less", "more")

    for line in reversed(lines):
        if len(out) >= limit:
            break
        try:
            evt = json.loads(line)
        except Exception:
            continue
        if not isinstance(evt, dict):
            continue
        phase = str(evt.get("phase") or "").strip().lower()
        if phase not in {"denied", "error"}:
            continue
        payload = evt.get("payload") if isinstance(evt.get("payload"), dict) else {}
        text = (
            f"{payload.get('reason', '')} "
            f"{payload.get('error', '')} "
            f"{payload.get('command_head', '')} "
            f"{json.dumps(payload, ensure_ascii=False)}"
        ).lower()

        m = cmd_pattern.search(text)
        if m:
            cmd = m.group(1).lower()
            if cmd and cmd not in seen:
                seen.add(cmd)
                out.append(cmd)
                continue
        for k in known:
            if re.search(rf"(^|[^a-z0-9_]){re.escape(k)}([^a-z0-9_]|$)", text):
                if k not in seen:
                    seen.add(k)
                    out.append(k)
                break
    return out
