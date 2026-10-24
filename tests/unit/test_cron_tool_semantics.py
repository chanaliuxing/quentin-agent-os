from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from quentin.tools import execution_parity
from quentin.tools.execution_parity import cron_tool


def test_cron_dom_dow_or_semantics() -> None:
    # When both DOM and DOW are restricted, cron should match either field.
    now = datetime(2026, 2, 3, 12, 0, tzinfo=timezone.utc).timestamp()
    expr = "0 0 1 * 1"  # midnight when (day-of-month==1) OR (day-of-week==Monday)

    nf = execution_parity._next_fire_from_cron(expr, now_ts=now, max_scan_minutes=60 * 24 * 40)
    assert nf is not None

    dt_now = datetime.fromtimestamp(now, tz=timezone.utc)
    # Next Monday midnight.
    days_ahead = (0 - dt_now.weekday()) % 7
    if days_ahead == 0:
        days_ahead = 7
    dt_mon = (dt_now + timedelta(days=days_ahead)).date()
    next_mon = datetime(dt_mon.year, dt_mon.month, dt_mon.day, 0, 0, tzinfo=timezone.utc).timestamp()

    # Next 1st-of-month midnight.
    y = dt_now.year
    m = dt_now.month + 1
    if m == 13:
        y += 1
        m = 1
    next_dom1 = datetime(y, m, 1, 0, 0, tzinfo=timezone.utc).timestamp()

    expected = min(next_mon, next_dom1)
    assert abs(float(nf) - float(expected)) < 60.0


def test_cron_sunday_7_supported() -> None:
    # Cron supports 7==Sunday. Ensure it maps correctly to Python weekday().
    sat_noon = datetime(2026, 2, 7, 12, 0, tzinfo=timezone.utc).timestamp()
    nf = execution_parity._next_fire_from_cron("0 0 * * 7", now_ts=sat_noon, max_scan_minutes=60 * 24 * 10)
    assert nf is not None
    expected = datetime(2026, 2, 8, 0, 0, tzinfo=timezone.utc).timestamp()
    assert abs(float(nf) - float(expected)) < 60.0


def test_cron_special_hourly_supported() -> None:
    now = datetime(2026, 2, 7, 12, 34, tzinfo=timezone.utc).timestamp()
    nf = execution_parity._next_fire_from_cron("@hourly", now_ts=now, max_scan_minutes=60 * 24 * 2)
    assert nf is not None
    expected = datetime(2026, 2, 7, 13, 0, tzinfo=timezone.utc).timestamp()
    assert abs(float(nf) - float(expected)) < 60.0


def test_cron_tool_catch_up_enqueues_multiple(tmp_path) -> None:
    ctx = SimpleNamespace(metadata={"repo_root": str(tmp_path.resolve())})
    cron_tool(
        {
            "action": "schedule",
            "name": "t",
            "task_input": "echo hi",
            "interval": "1s",
            "domain": "maintenance",
            "environment": "sandbox",
            "session_id": "bench",
            "priority": 1,
            "misfire_policy": "catch_up",
        },
        ctx,
    )

    db = tmp_path / "data" / "cron_tasks.json"
    raw = json.loads(db.read_text(encoding="utf-8"))
    node = dict((raw or {}).get("t") or {})
    now_ts = datetime.now(timezone.utc).timestamp()
    node["last_run"] = float(now_ts - 20)
    node["next_fire_ts"] = float(now_ts - 5)
    raw["t"] = node
    db.write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")

    out = cron_tool({"action": "run_due", "max_tasks": 25, "max_catch_up": 50}, ctx)
    assert int(out.get("enqueued_count") or 0) >= 2

