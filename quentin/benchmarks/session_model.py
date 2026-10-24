from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, UTC
from pathlib import Path
from typing import Any, Dict

from quentin.infra.concurrency.abort_signal import abort_registry
from quentin.infra.concurrency.lane_orchestrator import LaneOrchestrator
from quentin.infra.sessions.session_store import SessionPolicy, SessionStore
from quentin.memory.session_deltas import SessionDeltaConfig, SessionDeltaWriter


@dataclass
class _DummyMemory:
    writes: list[dict]

    def remember_atomic(self, **kwargs):
        self.writes.append(dict(kwargs))


class _AllowKernel:
    class _Result:
        allow = True

    def guard_action(self, action):
        return self._Result()


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _score_bool(ok: bool) -> float:
    return 1.0 if bool(ok) else 0.0


def run_benchmark(*, repo_root: str | Path = ".") -> Dict[str, Any]:
    root = Path(repo_root).resolve()
    work_root = root / "generated" / "benchmarks" / "session_model_runtime"
    work_root.mkdir(parents=True, exist_ok=True)

    checks: Dict[str, Dict[str, Any]] = {}

    # 1) recovery after "restart"
    store_a = SessionStore(repo_root=work_root)
    state = store_a.load_or_create("bench-session", metadata={"origin": "session_model_benchmark"})
    state.history.append({"role": "user", "content": "hello"})
    state.touch()
    store_a.save(state)
    store_b = SessionStore(repo_root=work_root)
    loaded = store_b.load("bench-session")
    recovery_ok = bool(loaded.history and loaded.history[-1].get("content") == "hello")
    checks["session_recovery"] = {
        "pass": recovery_ok,
        "details": {
            "history_len": len(loaded.history),
            "version": int(loaded.version),
        },
    }

    # 2) deterministic/stateful compaction
    state = store_b.load_or_create("bench-compact")
    for i in range(12):
        state.history.append({"role": "user" if i % 2 == 0 else "assistant", "content": f"msg-{i}"})
    state.touch()
    store_b.save(state)
    policy = SessionPolicy(max_history_messages=8, keep_recent_messages=3, min_messages_to_compact=4)
    compacted_state, report = store_b.maybe_compact("bench-compact", policy=policy)
    compaction_ok = bool(report.compacted and compacted_state.compaction.compaction_count >= 1 and len(compacted_state.history) == 4)
    checks["compaction_stateful"] = {
        "pass": compaction_ok,
        "details": {
            "reason": report.reason,
            "before_count": report.before_count,
            "after_count": report.after_count,
            "compaction_count": int(compacted_state.compaction.compaction_count),
        },
    }

    # 3) lane/abort binding by SessionState
    state = store_b.load_or_create("bench-lane")
    state.abort_signal_id = "bench-abort-signal"
    store_b.save(state)

    async def _noop() -> str:
        await asyncio.sleep(0.01)
        return "ok"

    orchestrator = LaneOrchestrator()
    out = orchestrator.run_sync_in_session(state, _noop, session_store=store_b, abort_existing=True)
    sig = abort_registry.get_signal("bench-abort-signal")
    lane_abort_ok = bool(out == "ok" and sig.is_aborted)
    checks["lane_abort_binding"] = {
        "pass": lane_abort_ok,
        "details": {
            "result": out,
            "signal_aborted": bool(sig.is_aborted),
            "lane_key": str(state.lane_key),
        },
    }

    # 4) session_deltas writes back to SessionState cursor/metadata
    mem = _DummyMemory(writes=[])
    writer = SessionDeltaWriter(
        memory_fabric=mem,
        safety_kernel=_AllowKernel(),
        config=SessionDeltaConfig(enabled=True, throttle_seconds=999, min_events=1, delta_bytes=1, delta_messages=1),
        session_store=store_b,
    )
    writer.observe_execution(
        session_id="bench-delta",
        trace_id="bench-trace",
        attempt_index=1,
        task_domain="core",
        task_environment="sandbox",
        plan_summary="plan",
        actions_summary="actions",
        final_output="done",
    )
    delta_state = store_b.load("bench-delta")
    delta_ok = bool(mem.writes and delta_state.metadata.get("last_trace_id") == "bench-trace" and delta_state.deltas_cursor.get("pending_events", 0) == 0)
    checks["delta_state_bridge"] = {
        "pass": delta_ok,
        "details": {
            "writes": len(mem.writes),
            "last_trace_id": str(delta_state.metadata.get("last_trace_id") or ""),
            "pending_events": int(delta_state.deltas_cursor.get("pending_events", -1) or -1),
        },
    }

    pass_count = sum(1 for v in checks.values() if bool(v.get("pass")))
    total = len(checks)
    quality_score = float(pass_count) / float(max(1, total))

    return {
        "generated_at": _now_iso(),
        "benchmark": "session_model",
        "quality_score": quality_score,
        "pass": bool(pass_count == total),
        "checks": checks,
        "summary": {
            "passed": pass_count,
            "total": total,
            "failed_keys": [k for k, v in checks.items() if not bool(v.get("pass"))],
        },
    }
