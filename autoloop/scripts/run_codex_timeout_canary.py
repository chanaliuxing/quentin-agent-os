#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


def _project_id(prefix: str, index: int) -> str:
    return f"{prefix}-{int(time.time())}-{index:02d}"


def _summary_file(root: Path, workflow_id: str) -> Path:
    return root / "runtime" / "evidence" / workflow_id / "phase_01" / "execution_summary.json"


def _runner_health_delta_file(root: Path, workflow_id: str) -> Path:
    return root / "runtime" / "evidence" / workflow_id / "phase_01" / "runner_health_delta.json"


def _load_run_observation(*, root: Path, workflow_id: str, timed_out: bool) -> dict:
    summary_path = _summary_file(root, workflow_id)
    delta_path = _runner_health_delta_file(root, workflow_id)
    terminal_state = None
    primary_failure_type = None
    degraded_run = False
    runner_health_signals: list[str] = []

    if summary_path.exists():
        summary_data = json.loads(summary_path.read_text(encoding="utf-8"))
        terminal_state = summary_data.get("terminal_state")
        primary_failure_type = summary_data.get("primary_failure_type")
        degraded_run = bool(summary_data.get("runner_health_degraded_run", False))
        runner_health_signals = [
            str(item)
            for item in summary_data.get("runner_health_signals", [])
            if str(item).strip()
        ]
        return {
            "summary_path": str(summary_path),
            "terminal_state": terminal_state,
            "primary_failure_type": primary_failure_type,
            "degraded_run": degraded_run,
            "runner_health_signals": runner_health_signals,
        }

    if delta_path.exists():
        delta_data = json.loads(delta_path.read_text(encoding="utf-8"))
        degraded_run = bool(delta_data.get("runner_health_degraded_run", False))
        runner_health_signals = [
            str(item)
            for item in delta_data.get("runner_health_signals", [])
            if str(item).strip()
        ]

    if timed_out:
        terminal_state = "TIMEOUT"
        primary_failure_type = "GLOBAL_TIMEOUT"

    return {
        "summary_path": str(summary_path),
        "terminal_state": terminal_state,
        "primary_failure_type": primary_failure_type,
        "degraded_run": degraded_run,
        "runner_health_signals": runner_health_signals,
    }


def _evaluate_promotion_gate(
    *,
    global_timeout_rate: float,
    reliability_degraded_run_rate: float,
    max_global_timeout_rate: float,
    max_degraded_run_rate: float,
) -> dict:
    reasons: list[str] = []
    if float(global_timeout_rate) > float(max_global_timeout_rate):
        reasons.append("GLOBAL_TIMEOUT_RATE_EXCEEDED")
    if float(reliability_degraded_run_rate) > float(max_degraded_run_rate):
        reasons.append("DEGRADED_RUN_RATE_EXCEEDED")
    return {
        "promotion_eligible": not reasons,
        "gate_reasons": reasons,
    }


def _build_degraded_breakdown(*, run_results: list[dict], runs: int) -> dict:
    run_count = max(1, int(runs or 0))
    run_signal_counter: Counter[str] = Counter()
    for row in run_results:
        signals = [str(item) for item in row.get("runner_health_signals", []) if str(item).strip()]
        for signal in sorted(set(signals)):
            run_signal_counter[signal] += 1

    run_rate = {signal: (count / run_count) for signal, count in sorted(run_signal_counter.items())}
    reliability_degraded_runs = 0
    capacity_limited_runs = 0
    for row in run_results:
        signals = {str(item) for item in row.get("runner_health_signals", []) if str(item).strip()}
        if "RUNNER_USAGE_LIMIT" in signals:
            capacity_limited_runs += 1
        if any(signal for signal in signals if signal != "RUNNER_USAGE_LIMIT"):
            reliability_degraded_runs += 1
    priority_order = [
        "AGENT_RUNNER_SESSION_DEGRADED",
        "STATE_DB_DEGRADED",
        "RUNNER_PROBE_FAILURE",
        "RUNNER_USAGE_LIMIT",
    ]
    ranked = sorted(
        run_rate.items(),
        key=lambda item: (
            -(item[1]),
            priority_order.index(item[0]) if item[0] in priority_order else 999,
            item[0],
        ),
    )
    top_signal = ranked[0][0] if ranked else ""
    top_signal_rate = ranked[0][1] if ranked else 0.0
    return {
        "signal_run_count": dict(run_signal_counter),
        "signal_run_rate": run_rate,
        "session_degraded_run_rate": run_rate.get("AGENT_RUNNER_SESSION_DEGRADED", 0.0),
        "state_db_degraded_run_rate": run_rate.get("STATE_DB_DEGRADED", 0.0),
        "probe_failure_run_rate": run_rate.get("RUNNER_PROBE_FAILURE", 0.0),
        "usage_limit_run_rate": run_rate.get("RUNNER_USAGE_LIMIT", 0.0),
        "reliability_degraded_run_rate": reliability_degraded_runs / run_count,
        "capacity_limited_run_rate": capacity_limited_runs / run_count,
        "top_priority_signal": top_signal,
        "top_priority_signal_rate": top_signal_rate,
    }


def _run_with_graceful_timeout(*, cmd: list[str], cwd: Path, env: dict[str, str], timeout_seconds: int) -> tuple[int, bool]:
    proc = subprocess.Popen(
        cmd,
        cwd=cwd,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
    )
    try:
        proc.communicate(timeout=max(1, timeout_seconds))
        return int(proc.returncode or 0), False
    except subprocess.TimeoutExpired:
        try:
            os.killpg(proc.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        try:
            proc.communicate(timeout=20)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            proc.communicate()
        return 124, True


def main() -> int:
    parser = argparse.ArgumentParser(description="Run codex timeout-profile canary and summarize outcomes.")
    parser.add_argument("--prd-path", required=True)
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--timeout-profile", default="codex_balanced")
    parser.add_argument("--project-prefix", default="codex-canary")
    parser.add_argument("--out", default="runtime/metrics/codex_timeout_canary_report.json")
    parser.add_argument("--run-timeout-seconds", type=int, default=480)
    parser.add_argument("--max-global-timeout-rate", type=float, default=0.0)
    parser.add_argument("--max-degraded-run-rate", type=float, default=0.0)
    parser.add_argument("--enforce-promotion-gate", action="store_true")
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[1]
    run_results: list[dict] = []
    terminal_counter: Counter[str] = Counter()
    primary_counter: Counter[str] = Counter()
    degraded_counter = 0
    degraded_signal_counter: Counter[str] = Counter()

    for idx in range(1, args.runs + 1):
        workflow_id = _project_id(args.project_prefix, idx)
        env = os.environ.copy()
        env["AGENT_RUNNER_TYPE"] = "codex"
        env["CODEX_TIMEOUT_PROFILE"] = args.timeout_profile
        env["AUTOLOOP_TIMEOUT_TERMINATES_AS_GLOBAL_TIMEOUT"] = "1"
        cmd = [
            str(repo_root / ".venv" / "bin" / "python"),
            "-m",
            "app.main",
            "run",
            args.prd_path,
            "--mode",
            "temporal",
            "--project-id",
            workflow_id,
        ]
        exit_code, timed_out = _run_with_graceful_timeout(
            cmd=cmd,
            cwd=repo_root,
            env=env,
            timeout_seconds=args.run_timeout_seconds,
        )
        observation = _load_run_observation(root=repo_root, workflow_id=workflow_id, timed_out=timed_out)
        terminal_value = str(observation.get("terminal_state", "")).strip()
        primary_value = str(observation.get("primary_failure_type", "")).strip()
        if terminal_value:
            terminal_counter[terminal_value] += 1
        if primary_value:
            primary_counter[primary_value] += 1
        if bool(observation.get("degraded_run", False)):
            degraded_counter += 1
        for signal in observation.get("runner_health_signals", []):
            degraded_signal_counter[str(signal)] += 1
        run_results.append(
            {
                "workflow_id": workflow_id,
                "exit_code": exit_code,
                "timed_out": timed_out,
                "summary_file": str(observation.get("summary_path", "")),
                "terminal_state": observation.get("terminal_state"),
                "primary_failure_type": observation.get("primary_failure_type"),
                "degraded_run": bool(observation.get("degraded_run", False)),
                "runner_health_signals": list(observation.get("runner_health_signals", [])),
            }
        )

    global_timeout_count = int(primary_counter.get("GLOBAL_TIMEOUT", 0))
    unknown_count = int(primary_counter.get("UNKNOWN", 0) + primary_counter.get("UNCLASSIFIED_EXECUTION_FAILURE", 0))
    global_timeout_rate = (global_timeout_count / args.runs) if args.runs else 0.0
    degraded_run_rate = (degraded_counter / args.runs) if args.runs else 0.0
    degraded_breakdown = _build_degraded_breakdown(run_results=run_results, runs=args.runs)
    gate = _evaluate_promotion_gate(
        global_timeout_rate=global_timeout_rate,
        reliability_degraded_run_rate=float(degraded_breakdown.get("reliability_degraded_run_rate", 0.0)),
        max_global_timeout_rate=args.max_global_timeout_rate,
        max_degraded_run_rate=args.max_degraded_run_rate,
    )
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "timeout_profile": args.timeout_profile,
        "runs": args.runs,
        "terminal_distribution": dict(terminal_counter),
        "primary_failure_distribution": dict(primary_counter),
        "global_timeout_rate": global_timeout_rate,
        "unknown_failure_rate": (unknown_count / args.runs) if args.runs else 0.0,
        "degraded_run_count": degraded_counter,
        "degraded_run_rate": degraded_run_rate,
        "degraded_signal_distribution": dict(degraded_signal_counter),
        "degraded_breakdown": degraded_breakdown,
        "max_global_timeout_rate": float(args.max_global_timeout_rate),
        "max_degraded_run_rate": float(args.max_degraded_run_rate),
        "promotion_eligible": bool(gate["promotion_eligible"]),
        "gate_reasons": list(gate["gate_reasons"]),
        "runs_detail": run_results,
    }

    out_file = (repo_root / args.out).resolve()
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(out_file)
    if args.enforce_promotion_gate and not bool(gate["promotion_eligible"]):
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
