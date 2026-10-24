#!/usr/bin/env python3
"""
Brain L3 benchmark (offline, stub-LLM powered).

Purpose:
- Exercise the *real* planning/execution/reflection pipeline without network access.
- Validate OpenClaw-parity signals:
  - attempt_evaluation category/correction_intensity
  - planner receives previous attempt's failure_category + correction_intensity
  - reflection can override plan to recover

This benchmark is meant to produce actionable gaps, not "perfect scores".
"""

from __future__ import annotations

import argparse
import gzip
import json
import os
import sys
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class BenchIssue:
    issue_type: str
    message: str
    scenario_id: str
    meta: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ScenarioResult:
    scenario_id: str
    name: str
    ok: bool
    latency_ms: float
    issues: List[BenchIssue] = field(default_factory=list)
    metrics: Dict[str, Any] = field(default_factory=dict)
    artifacts: Dict[str, Any] = field(default_factory=dict)


def _now_ms() -> float:
    return time.time() * 1000.0


def _safe_json(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, indent=2, default=str)


def _read_events(traces_dir: Path) -> List[Dict[str, Any]]:
    path = traces_dir / "events.jsonl.gz"
    if not path.exists():
        return []
    out: List[Dict[str, Any]] = []
    with gzip.open(path, "rt", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                if isinstance(obj, dict):
                    out.append(obj)
            except Exception:
                continue
    return out


def _select_trace_events(events: List[Dict[str, Any]], trace_id: str) -> List[Dict[str, Any]]:
    return [e for e in events if str(e.get("trace_id") or "") == trace_id]


def _latest_attempt_evaluation(trace_events: List[Dict[str, Any]]) -> Dict[str, Any]:
    # Emitted by loop_orchestration: TraceEventType.CRITIC payload action=attempt_evaluated.
    for e in reversed(trace_events):
        payload = e.get("payload") if isinstance(e.get("payload"), dict) else {}
        if payload.get("action") == "attempt_evaluated" and isinstance(payload.get("attempt_evaluation"), dict):
            return dict(payload["attempt_evaluation"])
    return {}


def _attempt_evaluations_by_attempt(trace_events: List[Dict[str, Any]]) -> Dict[int, Dict[str, Any]]:
    out: Dict[int, Dict[str, Any]] = {}
    for e in trace_events:
        payload = e.get("payload") if isinstance(e.get("payload"), dict) else {}
        if payload.get("action") != "attempt_evaluated":
            continue
        ae = payload.get("attempt_evaluation")
        if not isinstance(ae, dict):
            continue
        try:
            idx = int(payload.get("attempt_index") or 0)
        except Exception:
            idx = 0
        if idx <= 0:
            continue
        out[idx] = dict(ae)
    return out


def _planning_diagnostics(trace_events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for e in trace_events:
        if str(e.get("event_type") or "") != "planning":
            continue
        payload = e.get("payload") if isinstance(e.get("payload"), dict) else {}
        ctx = payload.get("context_injected") if isinstance(payload.get("context_injected"), dict) else {}
        diag = ctx.get("planning_diagnostics") if isinstance(ctx.get("planning_diagnostics"), dict) else {}
        if diag:
            out.append({"attempt_index": payload.get("attempt_index"), **diag})
    return out


class Harness:
    def __init__(self, *, repo_root: Path, workdir: Path, session_id: str) -> None:
        self.repo_root = repo_root
        self.workdir = workdir
        self.session_id = session_id

        rr = str(self.repo_root)
        if rr not in sys.path:
            sys.path.insert(0, rr)

        self.workdir.mkdir(parents=True, exist_ok=True)
        self.traces_dir = self.workdir / "traces"
        os.environ["QUENTIN_TRACES_DIR"] = str(self.traces_dir)

        # Force offline stub provider for the whole brain.
        os.environ["LLM_PROVIDER"] = "stub"
        os.environ["LLM_MODEL"] = "stub-model"
        os.environ["QUENTIN_TOOL_CALL_PROTOCOLS"] = "0"
        os.environ["QUENTIN_REFLECTION_FAILURE_THRESHOLD"] = "1"
        os.environ["QUENTIN_MAX_LOOPS"] = "3"
        os.environ["QUENTIN_BILLING_BYPASS"] = "1"
        os.environ["QUENTIN_ENABLE_PRE_SENSING"] = "0"
        os.environ["QUENTIN_LLM_FORCE_STUB"] = "1"
        os.environ["QUENTIN_COUNCIL_FORCE_FIRST"] = "1"

        from quentin.bootstrap.container import Container

        # Container() loads .env and may override LLM_* env vars.
        self.container = Container(repo_root=str(self.repo_root))
        # Re-assert all bench env after Container() because load_dotenv(override=True) clobbers.
        os.environ["LLM_PROVIDER"] = "stub"
        os.environ["LLM_MODEL"] = "stub-model"
        os.environ["QUENTIN_TOOL_CALL_PROTOCOLS"] = "0"
        os.environ["QUENTIN_REFLECTION_FAILURE_THRESHOLD"] = "1"
        os.environ["QUENTIN_MAX_LOOPS"] = "3"
        os.environ["QUENTIN_BILLING_BYPASS"] = "1"
        os.environ["QUENTIN_ENABLE_PRE_SENSING"] = "0"
        os.environ["QUENTIN_LLM_FORCE_STUB"] = "1"
        os.environ["QUENTIN_COUNCIL_FORCE_FIRST"] = "1"

        self.loop = self.container.cognitive_loop

    def run_task(self, *, input_text: str, domain: str = "core", environment: str = "sandbox") -> Tuple[Any, str]:
        from quentin.cognitive.loop_models import CognitiveTask

        task_id = f"bench_l3_{uuid.uuid4().hex[:10]}"
        task = CognitiveTask(
            input_text=input_text,
            task_id=task_id,
            domain=domain,
            environment=environment,
            metadata={"session_id": self.session_id},
        )
        res = self.loop.run_task(task)
        return res, task_id


def _scenario_tool_error_recovery(h: Harness) -> ScenarioResult:
    sid = "tool_error_recovery"
    t0 = _now_ms()
    issues: List[BenchIssue] = []

    # The stub planner looks for BENCH_SCENARIO:<id> in the goal/prompt text.
    input_text = "BENCH_SCENARIO:tool_error\nGoal: trigger a tool_execution_error, then recover via reflection plan override."

    before = len(_read_events(h.traces_dir))
    res, _task_id = h.run_task(input_text=input_text)
    events_all = _read_events(h.traces_dir)
    events = events_all[before:] if before <= len(events_all) else events_all
    trace_id = ""
    for e in reversed(events):
        if str(e.get("event_type") or "") == "summary":
            trace_id = str(e.get("trace_id") or "")
            break
    te = _select_trace_events(events, trace_id) if trace_id else []

    attempt_eval = _latest_attempt_evaluation(te)
    attempt_evals = _attempt_evaluations_by_attempt(te)
    first_eval = attempt_evals.get(1) or {}
    diag = _planning_diagnostics(te)

    expected_eval = first_eval or attempt_eval
    if not expected_eval:
        issues.append(BenchIssue("missing_attempt_evaluation", "no attempt_evaluated trace event found", sid, meta={"trace_id": trace_id}))
    else:
        # For this scenario we care about the *first* failure classification.
        observed = expected_eval
        cat = str(observed.get("category") or "")
        if cat != "tool_execution_error":
            issues.append(BenchIssue("wrong_category", "expected tool_execution_error on first failure", sid, meta={"observed": observed, "all": attempt_evals}))
        ci = str(observed.get("correction_intensity") or "")
        if ci not in {"medium", "high", "critical"}:
            issues.append(BenchIssue("bad_correction_intensity", "correction_intensity not populated as expected", sid, meta={"observed": observed}))

    # Ensure planner sees previous failure signals in planning diagnostics (attempt >=2).
    if len(diag) >= 2:
        expected_cat = str(expected_eval.get("category") or "")
        if str(diag[-1].get("failure_category") or "") != expected_cat:
            issues.append(BenchIssue("planner_signal_missing", "planning_diagnostics.failure_category did not match last attempt evaluation", sid, meta={"planning_diagnostics": diag[-1], "expected": expected_eval, "latest": attempt_eval}))

    done = bool(getattr(res, "done", False))
    if not done:
        issues.append(BenchIssue("did_not_recover", "expected brain to recover and reach done within max loops", sid, meta={"final_output": getattr(res, "final_output", "")}))

    ok = not issues
    return ScenarioResult(
        scenario_id=sid,
        name="Tool error -> AttemptEvaluation(tool_execution_error) -> Reflection override -> Done",
        ok=ok,
        latency_ms=_now_ms() - t0,
        issues=issues,
        metrics={"attempt_evaluation_latest": attempt_eval, "attempt_evaluation_expected": expected_eval, "attempt_evaluations": attempt_evals, "planning_diagnostics": diag, "done": done},
        artifacts={"trace_id": trace_id, "traces_dir": str(h.traces_dir)},
    )


def _scenario_logic_loop_recovery(h: Harness) -> ScenarioResult:
    sid = "logic_loop_recovery"
    t0 = _now_ms()
    issues: List[BenchIssue] = []

    input_text = "BENCH_SCENARIO:logic_loop\nGoal: trigger repeated_tool_call_loop (logic_path_error), then recover via reflection plan override."

    before = len(_read_events(h.traces_dir))
    res, _task_id = h.run_task(input_text=input_text)
    events_all = _read_events(h.traces_dir)
    events = events_all[before:] if before <= len(events_all) else events_all
    trace_id = ""
    for e in reversed(events):
        if str(e.get("event_type") or "") == "summary":
            trace_id = str(e.get("trace_id") or "")
            break
    te = _select_trace_events(events, trace_id) if trace_id else []

    attempt_eval = _latest_attempt_evaluation(te)
    attempt_evals = _attempt_evaluations_by_attempt(te)
    first_eval = attempt_evals.get(1) or {}
    diag = _planning_diagnostics(te)

    expected_eval = first_eval or attempt_eval
    if not expected_eval:
        issues.append(BenchIssue("missing_attempt_evaluation", "no attempt_evaluated trace event found", sid, meta={"trace_id": trace_id}))
    else:
        cat = str(expected_eval.get("category") or "")
        if cat != "logic_path_error":
            issues.append(BenchIssue("wrong_category", "expected logic_path_error for repeated_tool_call_loop", sid, meta={"observed": expected_eval, "all": attempt_evals}))
        ci = str(expected_eval.get("correction_intensity") or "")
        if ci not in {"high", "critical"}:
            issues.append(BenchIssue("weak_correction_intensity", "logic_path_error should drive high/critical correction", sid, meta={"observed": expected_eval}))

    if len(diag) >= 2:
        if str(diag[-1].get("failure_category") or "") != str(expected_eval.get("category") or ""):
            issues.append(BenchIssue("planner_signal_missing", "planning_diagnostics.failure_category did not match last attempt evaluation", sid, meta={"planning_diagnostics": diag[-1], "expected": expected_eval, "latest": attempt_eval}))

    done = bool(getattr(res, "done", False))
    if not done:
        issues.append(BenchIssue("did_not_recover", "expected brain to recover and reach done within max loops", sid, meta={"final_output": getattr(res, "final_output", "")}))

    ok = not issues
    return ScenarioResult(
        scenario_id=sid,
        name="Logic loop -> AttemptEvaluation(logic_path_error) -> Reflection override -> Done",
        ok=ok,
        latency_ms=_now_ms() - t0,
        issues=issues,
        metrics={"attempt_evaluation_latest": attempt_eval, "attempt_evaluation_expected": expected_eval, "attempt_evaluations": attempt_evals, "planning_diagnostics": diag, "done": done},
        artifacts={"trace_id": trace_id, "traces_dir": str(h.traces_dir)},
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-dir", default="generated/benchmarks", help="root output directory")
    args = ap.parse_args()

    repo_root = Path(__file__).resolve().parents[1]
    ts = time.strftime("%Y%m%d_%H%M%S")
    run_id = f"brain_l3_{ts}_{uuid.uuid4().hex[:8]}"
    out_root = (repo_root / args.out_dir / run_id).resolve()
    out_root.mkdir(parents=True, exist_ok=True)

    h = Harness(repo_root=repo_root, workdir=out_root, session_id=run_id)

    results = [
        _scenario_tool_error_recovery(h),
        _scenario_logic_loop_recovery(h),
    ]

    report_results: List[Dict[str, Any]] = []
    for r in results:
        report_results.append(
            {
                **dict(r.__dict__),
                "issues": [dict(i.__dict__) for i in (r.issues or [])],
            }
        )
    report = {
        "run_id": run_id,
        "ts": ts,
        "results": json.loads(_safe_json(report_results)),
        "pass_rate": sum(1 for r in results if r.ok) / max(1, len(results)),
        "issues": json.loads(_safe_json([dict(i.__dict__) for r in results for i in (r.issues or [])])),
        "todo": _build_todo(results),
    }
    (out_root / "report.json").write_text(_safe_json(report), encoding="utf-8")

    # Console summary (kept short; artifacts are in report.json).
    print(_safe_json({"run_id": run_id, "pass_rate": report["pass_rate"], "issues": report["issues"]}))
    return 0 if report["pass_rate"] == 1.0 else 2


def _build_todo(results: List[ScenarioResult]) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    for r in results:
        for iss in r.issues:
            items.append(
                {
                    "scenario_id": r.scenario_id,
                    "issue_type": iss.issue_type,
                    "message": iss.message,
                    "suggested_fix": _suggest_fix(iss.issue_type),
                }
            )
    # Deduplicate by (issue_type,message).
    seen = set()
    out: List[Dict[str, Any]] = []
    for it in items:
        k = (it["issue_type"], it["message"])
        if k in seen:
            continue
        seen.add(k)
        out.append(it)
    return out


def _suggest_fix(issue_type: str) -> str:
    mapping = {
        "missing_attempt_evaluation": "Ensure loop_orchestration emits attempt_evaluated trace and attempt_evaluator is called on failures.",
        "wrong_category": "Fix attempt_evaluator classification rules (tool vs logic vs misalignment) and align marker strings.",
        "weak_correction_intensity": "Adjust correction_intensity mapping for logic_path_error/critical signals, and ensure planner consumes it.",
        "planner_signal_missing": "Ensure planner_ctx.last_attempt_evaluation is injected into planner and recorded in planning trace diagnostics.",
        "did_not_recover": "Improve reflection override plan wiring or executor recovery behaviors; verify QUENTIN_REFLECTION_FAILURE_THRESHOLD and plan_override cache.",
    }
    return mapping.get(issue_type, "Investigate and add a targeted fix + regression test.")


if __name__ == "__main__":
    raise SystemExit(main())
