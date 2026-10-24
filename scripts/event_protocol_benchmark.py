from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path
import uuid
from typing import Any, Dict, List

from quentin.runtime.system_events import SystemEventQueue


async def _emit_many_sessions(queue: SystemEventQueue, *, sessions: int, per_session: int) -> tuple[bool, int]:
    async def _run_session(idx: int) -> tuple[str, list[int]]:
        sid = f"bench-concurrency-{idx:04d}"
        seqs: list[int] = []
        for step in range(per_session):
            ev = queue.emit_brain_event(
                session_id=sid,
                event_type="tool_execution_end",
                category="tool",
                phase="end",
                source="benchmark",
                payload={"step": step, "success": True},
                turn_id=f"turn-{idx}",
            )
            seqs.append(int(ev.seq))
            await asyncio.sleep(0)
        return sid, seqs

    rows = await asyncio.gather(*[_run_session(i) for i in range(max(1, int(sessions)))])
    monotonic = True
    total = 0
    for _sid, seqs in rows:
        total += len(seqs)
        if any(seqs[i] >= seqs[i + 1] for i in range(max(0, len(seqs) - 1))):
            monotonic = False
    return monotonic, total


def _probe_rate_limit_degrade(repo_root: Path) -> bool:
    from fastapi.testclient import TestClient
    from meta_agent.api.server import app, _brain_events_rate_window

    prev_backend = os.getenv("QUENTIN_OBS_EVENT_STORE_BACKEND")
    prev_limit = os.getenv("QUENTIN_BRAIN_EVENTS_RATE_LIMIT_PER_MIN")
    prev_cwd = Path.cwd()
    os.environ["QUENTIN_OBS_EVENT_STORE_BACKEND"] = "file"
    os.environ["QUENTIN_BRAIN_EVENTS_RATE_LIMIT_PER_MIN"] = "1"
    try:
        os.chdir(repo_root)
        _brain_events_rate_window.clear()
        queue = SystemEventQueue(repo_root=repo_root)
        sid = f"bench-rate-{uuid.uuid4().hex[:8]}"
        queue.emit_brain_event(
            session_id=sid,
            event_type="message",
            category="message",
            phase="update",
            source="benchmark",
            payload={"text": "warm"},
            turn_id="t1",
        )
        client = TestClient(app)
        warm = client.get("/brain-events/drain", params={"session_id": sid, "limit": 5})
        if warm.status_code != 200:
            return False
        limited = client.get("/brain-events/drain", params={"session_id": sid, "limit": 5})
        body = limited.json() if limited.status_code == 200 else {}
        if not bool(body.get("degraded")):
            return False
        events = queue.list_brain_events(session_id=f"default:{sid}", limit=20)
        return any(str(e.event_type or "") == "gateway.rate_limited" for e in events)
    finally:
        os.chdir(prev_cwd)
        if prev_backend is None:
            os.environ.pop("QUENTIN_OBS_EVENT_STORE_BACKEND", None)
        else:
            os.environ["QUENTIN_OBS_EVENT_STORE_BACKEND"] = prev_backend
        if prev_limit is None:
            os.environ.pop("QUENTIN_BRAIN_EVENTS_RATE_LIMIT_PER_MIN", None)
        else:
            os.environ["QUENTIN_BRAIN_EVENTS_RATE_LIMIT_PER_MIN"] = prev_limit


def run(repo_root: Path) -> dict:
    queue = SystemEventQueue(repo_root=repo_root)
    session_id = f"bench-event-protocol-{uuid.uuid4().hex[:8]}"
    seen = []

    def _bad(_ev):  # type: ignore[no-untyped-def]
        raise RuntimeError("subscriber_failure")

    def _good(ev):  # type: ignore[no-untyped-def]
        seen.append(str(ev.event_type or ""))

    queue.subscribe_session(session_id, _bad)
    queue.subscribe_session(session_id, _good)

    first = queue.emit_brain_event(
        session_id=session_id,
        event_type="turn_start",
        category="turn",
        phase="start",
        source="benchmark",
        payload={"attempt": 1},
        turn_id="turn-1",
    )
    queue.emit_brain_event(
        session_id=session_id,
        event_type="tool_execution_start",
        category="tool",
        phase="start",
        source="benchmark",
        payload={"tool_name": "fs.read_file"},
        turn_id="turn-1",
    )
    queue.emit_brain_event(
        session_id=session_id,
        event_type="tool_execution_end",
        category="tool",
        phase="end",
        source="benchmark",
        payload={"tool_name": "fs.read_file", "success": True},
        turn_id="turn-1",
    )
    queue.emit_brain_event(
        session_id=session_id,
        event_type="message",
        category="message",
        phase="end",
        source="benchmark",
        payload={"final_output_preview": "ok"},
        turn_id="turn-1",
    )

    full = queue.list_brain_events(session_id=session_id, limit=50, after_cursor="")
    replay_after = queue.drain_brain_events(session_id=session_id, limit=50, after_cursor=first.cursor)
    timeline_types = [str(e.event_type or "") for e in full if str(e.event_type or "") != "subscriber_diagnostic"]
    timeline_rebuild_ok = timeline_types == [
        "turn_start",
        "tool_execution_start",
        "tool_execution_end",
        "message",
    ]

    seq_ok = all(int(full[i].seq) < int(full[i + 1].seq) for i in range(max(0, len(full) - 1)))
    fail_closed_ok = len(seen) >= 4
    replay_ok = len(replay_after) == max(0, len(full) - 1)
    concurrent_ok, concurrent_total = asyncio.run(_emit_many_sessions(queue, sessions=120, per_session=4))
    stats = queue.get_subscriber_stats(session_id=session_id)
    has_subscriber_diag = any(
        str(e.event_type or "") == "subscriber_diagnostic" for e in queue.list_brain_events(session_id=session_id, limit=200)
    )
    stats_ok = bool(stats) and int((stats[0] or {}).get("failures_total") or 0) >= 1
    rate_limit_observable_ok = _probe_rate_limit_degrade(repo_root)

    failure_cases: List[Dict[str, Any]] = []
    # 20 failure-injection cases: 10 callback storms + 10 restart resume flows.
    for idx in range(10):
        sid = f"{session_id}-fi-storm-{idx}"
        seen_local: List[str] = []

        def _bad_local(_ev):  # type: ignore[no-untyped-def]
            raise RuntimeError("storm_injected")

        def _good_local(ev):  # type: ignore[no-untyped-def]
            seen_local.append(str(ev.event_type or ""))

        queue.subscribe_session(sid, _bad_local)
        queue.subscribe_session(sid, _good_local)
        for _ in range(3):
            queue.emit_brain_event(
                session_id=sid,
                event_type="message",
                category="message",
                phase="update",
                source="benchmark",
                payload={"storm": idx},
                turn_id="t",
            )
        listed = queue.list_brain_events(session_id=sid, limit=50)
        ok = len(seen_local) >= 1 and any(str(e.event_type or "") == "subscriber_diagnostic" for e in listed)
        failure_cases.append({"case_id": f"storm_{idx}", "ok": bool(ok), "count": len(listed)})

    for idx in range(10):
        sid = f"{session_id}-fi-resume-{idx}"
        e1 = queue.emit_brain_event(
            session_id=sid,
            event_type="message",
            category="message",
            phase="update",
            source="benchmark",
            payload={"n": 1},
            turn_id="t",
        )
        queue.ack_cursor(session_id=sid, cursor=e1.cursor)
        queue.emit_brain_event(
            session_id=sid,
            event_type="message",
            category="message",
            phase="update",
            source="benchmark",
            payload={"n": 2},
            turn_id="t",
        )
        queue2 = SystemEventQueue(repo_root=repo_root)
        replay = queue2.list_brain_events(
            session_id=sid,
            after_cursor=queue2.get_acked_cursor(session_id=sid),
            limit=10,
            dedupe=True,
        )
        ok = len(replay) == 1 and int(replay[0].payload.get("n") or 0) == 2
        failure_cases.append({"case_id": f"resume_{idx}", "ok": bool(ok), "count": len(replay)})

    capability_score = 0.0
    capability_score += 0.4 if seq_ok else 0.0
    capability_score += 0.3 if replay_ok else 0.0
    capability_score += 0.3 if timeline_rebuild_ok else 0.0

    reliability_score = 0.0
    reliability_score += 0.4 if fail_closed_ok else 0.0
    reliability_score += 0.3 if stats_ok else 0.0
    reliability_score += 0.3 if concurrent_ok else 0.0

    operations_score = 0.0
    operations_score += 0.4 if has_subscriber_diag else 0.0
    operations_score += 0.4 if concurrent_total >= 480 else 0.0
    operations_score += 0.2 if rate_limit_observable_ok else 0.0

    injected_ok_ratio = (
        float(sum(1 for c in failure_cases if bool(c.get("ok")))) / float(len(failure_cases))
        if failure_cases
        else 0.0
    )
    operations_score = min(1.0, (operations_score * 0.6) + (injected_ok_ratio * 0.4))
    score = round((capability_score + reliability_score + operations_score) / 3.0, 4)
    pass_gate = bool(
        score >= 0.85
        and capability_score >= 0.85
        and reliability_score >= 0.85
        and operations_score >= 0.85
        and len(failure_cases) >= 20
        and injected_ok_ratio >= 0.85
    )

    return {
        "score": score,
        "pass": pass_gate,
        "score_breakdown": {
            "capability_score": round(capability_score, 4),
            "reliability_score": round(reliability_score, 4),
            "operations_score": round(operations_score, 4),
        },
        "checks": {
            "sequence_monotonic": seq_ok,
            "fail_closed_subscriber": fail_closed_ok,
            "cursor_replay": replay_ok,
            "timeline_rebuild": timeline_rebuild_ok,
            "subscriber_stats_recorded": stats_ok,
            "concurrency_session_seq_monotonic": concurrent_ok,
            "diagnostic_event_emitted": has_subscriber_diag,
            "rate_limit_observable_degrade": rate_limit_observable_ok,
            "failure_injection_ratio_ok": injected_ok_ratio >= 0.85,
        },
        "failure_injection_cases": len(failure_cases),
        "failure_injection_ok_ratio": round(injected_ok_ratio, 4),
        "failure_injection_details": failure_cases,
        "events_count": len(full),
        "replay_after_count": len(replay_after),
        "concurrency_events_count": int(concurrent_total),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Event protocol benchmark (cursor replay + fail-closed).")
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--output", default="generated/benchmarks/event_protocol_benchmark_report.json")
    args = parser.parse_args()

    report = run(Path(args.repo_root))
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))
    return 0 if bool(report.get("pass")) else 2


if __name__ == "__main__":
    raise SystemExit(main())
