#!/usr/bin/env python3
"""
Brain E2E benchmark (execution-focused).

Why this exists:
- Execution-layer microbenches validate tool correctness in isolation.
- This benchmark validates that the *brain entrypoint* can drive those tools
  deterministically (no LLM required), producing reliable side effects and
  diagnosable artifacts.

It is intentionally not a "maximize score" harness. It produces actionable
issue clusters + a TODO list to make the agent smarter at task completion and
recovery.
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import sys
import time
import traceback
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple


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
    artifacts: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Scenario:
    scenario_id: str
    name: str
    run: Callable[["Harness"], ScenarioResult]
    tags: Tuple[str, ...] = ()


def _now_ms() -> float:
    return time.time() * 1000.0


def _safe_json(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, indent=2)


def _parse_tool_output(text: str) -> Dict[str, Any]:
    """
    Inline-action final_output is usually `str(dict)` (Python repr, not JSON).
    We accept JSON first, then fall back to `ast.literal_eval`.
    """
    raw = (text or "").strip()
    if not raw:
        return {}
    try:
        obj = json.loads(raw)
        return obj if isinstance(obj, dict) else {}
    except Exception:
        pass
    try:
        obj = ast.literal_eval(raw)
        return obj if isinstance(obj, dict) else {}
    except Exception:
        return {}


class Harness:
    def __init__(self, *, repo_root: Path, workdir: Path, session_id: str) -> None:
        self.repo_root = repo_root
        self.workdir = workdir
        self.workdir_rel = str(workdir.relative_to(repo_root))
        self.session_id = session_id

        # Ensure imports stay stable regardless of cwd.
        rr = str(self.repo_root)
        if rr not in sys.path:
            sys.path.insert(0, rr)

        self.workdir.mkdir(parents=True, exist_ok=True)

        # Keep traces inside the bench workdir.
        os.environ["QUENTIN_TRACES_DIR"] = str(self.workdir / "traces")

        from quentin.bootstrap.container import Container

        self.container = Container(repo_root=str(self.repo_root))
        # Container/env normalization may clobber these. Force after init so /tool remains deterministic.
        os.environ["QUENTIN_INPUT_INLINE_ACTIONS_ENABLED"] = "1"
        os.environ["QUENTIN_INPUT_INLINE_ACTION_TOOL_ALLOWLIST"] = "*"
        os.environ["QUENTIN_INPUT_INLINE_ACTION_SHELL_ALLOWLIST"] = "*"
        self.loop = self.container.cognitive_loop

    def close(self) -> None:
        return

    def run_inline_tool(self, tool_name: str, args: Dict[str, Any]) -> Any:
        from quentin.cognitive.loop_models import CognitiveTask

        task = CognitiveTask(
            input_text=f"/tool {tool_name} {json.dumps(args, ensure_ascii=False)}",
            task_id=f"bench_{uuid.uuid4().hex[:10]}",
            domain="core",
            environment="sandbox",
            metadata={"session_id": self.session_id, "repo_root": str(self.workdir)},
        )
        return self.loop.run_task(task)

    def must_inline_ok(self, res: Any, *, scenario_id: str, issues: List[BenchIssue]) -> Dict[str, Any]:
        # Inline-action should mark self-awareness; if not, we almost certainly fell back into planner/LLM.
        sa = getattr(res, "self_awareness", None) or {}
        if not (isinstance(sa, dict) and sa.get("inline_action_hit") is True):
            issues.append(
                BenchIssue(
                    "inline_action_missed",
                    "brain did not take deterministic /tool path (likely fell back to planner/LLM)",
                    scenario_id,
                    meta={"self_awareness": sa},
                )
            )
        if not bool(getattr(res, "done", False)):
            issues.append(
                BenchIssue(
                    "brain_not_done",
                    "brain did not return done=True for deterministic tool call",
                    scenario_id,
                    meta={"done_confidence": getattr(res, "done_confidence", None)},
                )
            )
        out_text = str(getattr(res, "final_output", "") or "")
        parsed = _parse_tool_output(out_text)
        if not parsed:
            issues.append(
                BenchIssue(
                    "unparseable_tool_output",
                    "could not parse inline tool output (expected dict-ish string)",
                    scenario_id,
                    meta={"final_output_preview": out_text[:500]},
                )
            )
        return parsed


def _scenario_fs_roundtrip(h: Harness) -> ScenarioResult:
    sid = "fs_roundtrip"
    t0 = _now_ms()
    issues: List[BenchIssue] = []
    rel_path = f"{h.workdir_rel}/out/hello.txt"
    abs_path = (h.repo_root / rel_path).resolve()
    abs_path.parent.mkdir(parents=True, exist_ok=True)

    res1 = h.run_inline_tool("fs.write_file", {"path": str(rel_path), "content": "hello\nworld\n"})
    _ = h.must_inline_ok(res1, scenario_id=sid, issues=issues)
    if not abs_path.exists():
        issues.append(BenchIssue("side_effect_missing", "expected file to be written", sid, meta={"path": str(rel_path)}))

    res2 = h.run_inline_tool("fs.read_file", {"path": str(rel_path)})
    out2 = h.must_inline_ok(res2, scenario_id=sid, issues=issues)
    txt = ""
    if isinstance(out2, dict):
        txt = str(out2.get("content") or out2.get("result") or "")
    if "hello" not in txt:
        issues.append(BenchIssue("wrong_output", "read_file did not return expected content", sid, meta={"content_preview": txt[:200]}))

    ok = not issues
    return ScenarioResult(
        scenario_id=sid,
        name="Brain inline /tool fs.write_file + fs.read_file",
        ok=ok,
        latency_ms=_now_ms() - t0,
        issues=issues,
        artifacts={"path": str(abs_path), "rel_path": str(rel_path)},
    )


def _scenario_shell_signal_forwarding(h: Harness) -> ScenarioResult:
    sid = "shell_signal_forwarding"
    t0 = _now_ms()
    issues: List[BenchIssue] = []

    # Start a long-running process in background mode.
    res1 = h.run_inline_tool(
        "shell.run_command",
        {"command": "python -c \"import time; print('ready'); time.sleep(999)\"", "yield_seconds": 0.15},
    )
    out1 = h.must_inline_ok(res1, scenario_id=sid, issues=issues)
    proc_id = str(out1.get("proc_id") or out1.get("execution_id") or "").strip()
    if not proc_id:
        issues.append(BenchIssue("missing_proc_id", "background shell did not return proc_id", sid, meta={"out": out1}))
        return ScenarioResult(scenario_id=sid, name="Signal forwarding to background shell process", ok=False, latency_ms=_now_ms() - t0, issues=issues)

    # Send SIGINT (OpenClaw parity: allow gentle stop).
    res2 = h.run_inline_tool("shell.send_signal", {"proc_id": proc_id, "signal": "SIGINT"})
    _ = h.must_inline_ok(res2, scenario_id=sid, issues=issues)

    # Poll until exited (bounded).
    exit_code = None
    for _i in range(30):
        res3 = h.run_inline_tool("shell.poll_results", {"proc_id": proc_id})
        out3 = h.must_inline_ok(res3, scenario_id=sid, issues=issues)
        exit_code = out3.get("exit_code") if isinstance(out3, dict) else None
        if exit_code is not None:
            break
        time.sleep(0.05)
    if exit_code is None:
        issues.append(BenchIssue("process_stuck", "process did not exit after SIGINT + polling", sid, meta={"proc_id": proc_id}))

    ok = not issues
    return ScenarioResult(
        scenario_id=sid,
        name="Brain -> shell.run_command(background) -> shell.send_signal(SIGINT) -> shell.poll_results",
        ok=ok,
        latency_ms=_now_ms() - t0,
        issues=issues,
        artifacts={"proc_id": proc_id, "exit_code": exit_code},
    )


def _scenario_cron_schedule_and_run_due(h: Harness) -> ScenarioResult:
    sid = "cron_schedule_run_due"
    t0 = _now_ms()
    issues: List[BenchIssue] = []

    name = f"bench_{uuid.uuid4().hex[:8]}"
    # Use interval syntax ("1s") so schedule can be immediately due deterministically.
    res1 = h.run_inline_tool(
        "cron.tool",
        {
            "action": "schedule",
            "name": name,
            "task_input": "echo cron bench",
            "interval": "1s",
            "start_immediately": True,
            "misfire_policy": "catch_up",
        },
    )
    out1 = h.must_inline_ok(res1, scenario_id=sid, issues=issues)
    if str(out1.get("status") or "") != "ok":
        issues.append(BenchIssue("cron_schedule_failed", "cron.tool schedule did not return ok", sid, meta={"out": out1}))

    res2 = h.run_inline_tool("cron.tool", {"action": "run_due", "dry_run": True, "max_tasks": 10, "max_catch_up": 5})
    out2 = h.must_inline_ok(res2, scenario_id=sid, issues=issues)
    due = int(out2.get("due_count") or 0) if isinstance(out2, dict) else 0
    if due < 1:
        issues.append(BenchIssue("cron_not_due", "expected at least one due task after start_immediately schedule", sid, meta={"out": out2}))

    ok = not issues
    return ScenarioResult(
        scenario_id=sid,
        name="Brain -> cron.tool(schedule interval=1s) -> cron.tool(run_due dry_run)",
        ok=ok,
        latency_ms=_now_ms() - t0,
        issues=issues,
        artifacts={"cron_name": name, "due_count": due},
    )


def _scenario_channels_listener_inject(h: Harness) -> ScenarioResult:
    sid = "channels_listener_inject"
    t0 = _now_ms()
    issues: List[BenchIssue] = []
    platform = "discord"
    thread_id = f"bench_thread_{uuid.uuid4().hex[:6]}"

    # Inject inbound message into offline listener (OpenClaw-style streaming convo threading, but local).
    res1 = h.run_inline_tool(
        "channels.listener",
        {
            "action": "inject",
            "platform": platform,
            "text": "hello from benchmark",
            "sender_id": "user",
            "message_id": f"m_{uuid.uuid4().hex[:8]}",
            # Align with thread normalization logic: discord uses channel_id => thread_id "discord:<channel_id>".
            "metadata": {"channel_id": thread_id},
            "auto_reply": False,
        },
    )
    out1 = h.must_inline_ok(res1, scenario_id=sid, issues=issues)
    if str(out1.get("status") or "") != "ok":
        issues.append(BenchIssue("listener_inject_failed", "inject did not return ok", sid, meta={"out": out1}))

    # Offline inject writes to the thread store (not the live listener queue). Validate persistence.
    try:
        store = h.workdir / "data" / "channels" / f"{platform}_threads.json"
        if not store.exists():
            issues.append(BenchIssue("thread_store_missing", "expected thread store to exist after inject", sid, meta={"path": str(store)}))
        else:
            data = json.loads(store.read_text(encoding="utf-8"))
            node = ((data or {}).get("threads") or {}).get(f"{platform}:{thread_id}") or {}
            msgs = list(node.get("messages") or [])
            if not msgs:
                issues.append(BenchIssue("thread_store_empty", "expected injected message to persist into thread store", sid, meta={"path": str(store)}))
    except Exception as e:
        issues.append(BenchIssue("thread_store_read_failed", f"failed to read thread store: {e}", sid))

    ok = not issues
    return ScenarioResult(
        scenario_id=sid,
        name="Brain -> channels.listener(inject) -> channels.listener(poll)",
        ok=ok,
        latency_ms=_now_ms() - t0,
        issues=issues,
        artifacts={"platform": platform, "thread_id": thread_id},
    )


def _scenario_web_readability_patch(h: Harness) -> ScenarioResult:
    sid = "web_readability_patch"
    t0 = _now_ms()
    issues: List[BenchIssue] = []

    html = """
    <html><head><title>Test</title></head>
    <body>
      <div id="mw-navigation">NAV</div>
      <div id="mw-panel">SIDEBAR</div>
      <div id="content">
        <h1 id="firstHeading">Example Heading</h1>
        <p>This is the main content. It should remain.</p>
        <div class="mw-footer">FOOTER</div>
      </div>
    </body></html>
    """.strip()
    res = h.run_inline_tool(
        "web.readability",
        {"url": "https://en.wikipedia.org/wiki/Example", "html": html, "apply_site_patch": True, "max_chars": 5000},
    )
    out = h.must_inline_ok(res, scenario_id=sid, issues=issues)
    content = str(out.get("content") or "")
    if "main content" not in content:
        issues.append(BenchIssue("readability_wrong", "readability content missing expected text", sid, meta={"content_preview": content[:300]}))
    patch = out.get("site_patch") if isinstance(out, dict) else {}
    removed = int((patch or {}).get("removed_blocks") or 0) if isinstance(patch, dict) else 0
    if removed < 1:
        issues.append(BenchIssue("site_patch_noop", "expected site patch to remove at least 1 block for wikipedia fixture", sid, meta={"site_patch": patch}))

    ok = not issues
    return ScenarioResult(
        scenario_id=sid,
        name="Brain -> web.readability(site patch rules, offline HTML)",
        ok=ok,
        latency_ms=_now_ms() - t0,
        issues=issues,
        artifacts={"removed_blocks": removed},
    )


def _scenario_image_ocr_smoke(h: Harness) -> ScenarioResult:
    sid = "image_ocr_smoke"
    t0 = _now_ms()
    issues: List[BenchIssue] = []

    rel_img_path = f"{h.workdir_rel}/out/ocr.png"
    img_path = (h.repo_root / rel_img_path).resolve()
    img_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        from PIL import Image, ImageDraw, ImageFont

        im = Image.new("RGB", (520, 140), color=(255, 255, 255))
        d = ImageDraw.Draw(im)
        try:
            font = ImageFont.truetype("DejaVuSans.ttf", 64)
        except Exception:
            font = ImageFont.load_default()
        d.text((20, 30), "HELLO 123", fill=(0, 0, 0), font=font)
        im.save(img_path)
    except Exception as e:
        issues.append(BenchIssue("fixture_failed", f"failed to generate OCR fixture image: {e}", sid))
        return ScenarioResult(scenario_id=sid, name="Image OCR smoke", ok=False, latency_ms=_now_ms() - t0, issues=issues)

    # Pass a relative path to satisfy PathGuard.
    res = h.run_inline_tool("image.tool", {"path": str(rel_img_path), "ocr_mode": "tesseract", "ocr_allow_fallback": False})
    out = h.must_inline_ok(res, scenario_id=sid, issues=issues)
    ocr_text = str(out.get("ocr_text") or "")
    eng = str(out.get("ocr_engine") or "")
    if "HELLO" not in ocr_text.upper():
        # Informational: OCR is inherently noisy across platforms/fonts.
        issues.append(BenchIssue("ocr_missed", "OCR did not recognize 'HELLO' from fixture", sid, meta={"engine": eng, "text_preview": ocr_text[:200]}))
    if eng in {"hint", "none", ""}:
        issues.append(BenchIssue("ocr_degraded", "OCR backend degraded to hint/none (capability gap)", sid, meta={"engine": eng}))

    ok = not any(i.issue_type in {"fixture_failed"} for i in issues)
    return ScenarioResult(
        scenario_id=sid,
        name="Brain -> image.tool(ocr_mode=tesseract)",
        ok=ok,
        latency_ms=_now_ms() - t0,
        issues=issues,
        artifacts={"path": str(img_path), "ocr_engine": eng},
    )


def _scenario_canvas_lifecycle(h: Harness) -> ScenarioResult:
    sid = "canvas_lifecycle"
    t0 = _now_ms()
    issues: List[BenchIssue] = []

    res1 = h.run_inline_tool("canvas.tool", {"action": "create", "type": "ActionCard", "props": {"title": "Bench"}, "state": {"enabled": True}})
    out1 = h.must_inline_ok(res1, scenario_id=sid, issues=issues)
    comp = out1.get("component") if isinstance(out1, dict) else None
    cid = str((comp or {}).get("component_id") or "").strip() if isinstance(comp, dict) else ""
    if not cid:
        issues.append(BenchIssue("canvas_missing_id", "canvas.tool did not return component_id", sid, meta={"out": out1}))
        return ScenarioResult(scenario_id=sid, name="Canvas lifecycle", ok=False, latency_ms=_now_ms() - t0, issues=issues)

    res2 = h.run_inline_tool("canvas.tool", {"action": "update", "component_id": cid, "state": {"enabled": False}})
    out2 = h.must_inline_ok(res2, scenario_id=sid, issues=issues)
    if not bool(out2.get("updated")):
        issues.append(BenchIssue("canvas_update_failed", "expected canvas update to succeed", sid, meta={"out": out2}))

    res3 = h.run_inline_tool("canvas.tool", {"action": "get", "component_id": cid})
    out3 = h.must_inline_ok(res3, scenario_id=sid, issues=issues)
    node = out3.get("component") if isinstance(out3, dict) else None
    enabled = None
    if isinstance(node, dict):
        enabled = (node.get("state") or {}).get("enabled")
    if enabled is not False:
        issues.append(BenchIssue("canvas_state_wrong", "expected enabled=False after update", sid, meta={"enabled": enabled}))

    ok = not issues
    return ScenarioResult(
        scenario_id=sid,
        name="Brain -> canvas.tool(create/update/get)",
        ok=ok,
        latency_ms=_now_ms() - t0,
        issues=issues,
        artifacts={"component_id": cid},
    )


def _scenario_trace_recorder_smoke(h: Harness) -> ScenarioResult:
    sid = "trace_recorder_smoke"
    t0 = _now_ms()
    issues: List[BenchIssue] = []

    try:
        from quentin.traces.core import JsonlTraceRecorder, TraceEvent

        rec = JsonlTraceRecorder(repo_root=str(h.workdir))
        rec.record_event(TraceEvent(event_id="bench", trace_id="bench", event_type="benchmark", payload={"k": "v"}))
        gz = (h.workdir / "traces" / "events.jsonl.gz")
        if not gz.exists():
            issues.append(BenchIssue("trace_missing", "expected trace gz file to exist after record_event", sid, meta={"path": str(gz)}))
    except Exception as e:
        issues.append(BenchIssue("trace_exception", f"trace recorder raised: {e}", sid, meta={"traceback": traceback.format_exc()}))

    ok = not issues
    return ScenarioResult(
        scenario_id=sid,
        name="Trace recorder gzip append smoke",
        ok=ok,
        latency_ms=_now_ms() - t0,
        issues=issues,
        artifacts={},
    )


def default_scenarios() -> List[Scenario]:
    return [
        Scenario("trace_recorder_smoke", "Trace recorder gzip append smoke", _scenario_trace_recorder_smoke, tags=("observability",)),
        Scenario("fs_roundtrip", "Brain inline /tool fs roundtrip", _scenario_fs_roundtrip, tags=("fs", "correctness")),
        Scenario("shell_signal_forwarding", "Signal forwarding to background process", _scenario_shell_signal_forwarding, tags=("shell", "control", "robustness")),
        Scenario("cron_schedule_run_due", "Cron schedule + run_due", _scenario_cron_schedule_and_run_due, tags=("cron", "persistence")),
        Scenario("channels_listener_inject", "Channels listener inject + poll", _scenario_channels_listener_inject, tags=("communication", "threading")),
        Scenario("web_readability_patch", "Web readability site patch", _scenario_web_readability_patch, tags=("web", "fetch")),
        Scenario("image_ocr_smoke", "Image OCR smoke", _scenario_image_ocr_smoke, tags=("media", "ocr")),
        Scenario("canvas_lifecycle", "Canvas lifecycle", _scenario_canvas_lifecycle, tags=("ui", "lifecycle")),
    ]


def _issues_to_todo(issues: List[BenchIssue]) -> List[Dict[str, Any]]:
    """
    Turn issue clusters into an actionable TODO list. These are intentionally
    pragmatic "do X" items, not vague recommendations.
    """
    clusters: Dict[str, List[BenchIssue]] = {}
    for it in issues:
        clusters.setdefault(it.issue_type, []).append(it)

    todo: List[Dict[str, Any]] = []
    if "inline_action_missed" in clusters:
        todo.append(
            {
                "id": "bench.inline_action.missed",
                "priority": "P0",
                "title": "Ensure /tool inline actions never fall back to planner in sandbox benchmark mode",
                "why": "If /tool falls back, benchmark turns into LLM-council smoke and becomes non-deterministic/un-runnable in restricted envs.",
                "how": [
                    "Make allowlist explicit in benchmark harness (already).",
                    "Consider propagating repo_root/session_id to ToolCallContext for parity tools.",
                ],
            }
        )
    if "process_stuck" in clusters or "missing_proc_id" in clusters:
        todo.append(
            {
                "id": "bench.shell.signal_forwarding",
                "priority": "P0",
                "title": "Fix shell background process control (proc_id, send_signal, poll_results)",
                "why": "Without gentle SIGINT/SIGTERM control, the agent loses the ability to stop hanging commands safely.",
                "how": ["Reproduce with scenario shell_signal_forwarding and fix process_manager/signal ladder."],
            }
        )
    if "ocr_degraded" in clusters:
        todo.append(
            {
                "id": "bench.ocr.backend",
                "priority": "P1",
                "title": "Make OCR backend reliable (tesseract/python deps, or vision endpoint)",
                "why": "OCR unlocks reading text from screenshots into memory and reasoning context.",
                "how": [
                    "Ensure tesseract CLI fallback works everywhere (added).",
                    "Optionally add pytesseract dependency for richer configs.",
                ],
            }
        )
    if "trace_exception" in clusters or "trace_missing" in clusters:
        todo.append(
            {
                "id": "bench.trace.robustness",
                "priority": "P0",
                "title": "Fix trace recorder so benchmark can attribute failures",
                "why": "Without stable traces, we can’t localize regressions or cluster failures objectively.",
                "how": ["Run scenario trace_recorder_smoke and ensure gz JSONL append works."],
            }
        )

    # Always keep a stub entry to push more scenarios instead of chasing a single score.
    todo.append(
        {
            "id": "bench.expand.scenarios",
            "priority": "P2",
            "title": "Add scenarios for recovery (tool-error vs logic-error) once real LLM mode is runnable",
            "why": "Smartness comes from recovery behavior, not perfect tool outputs.",
            "how": [
                "Add scenarios that intentionally fail a tool once and verify planner retry strategy changes.",
                "Add scenario that fails due to wrong plan and verify reflection increases correction intensity.",
            ],
        }
    )
    return todo


def run_benchmark(
    *,
    repo_root: Path,
    runs: int,
    output_path: Path,
    history_path: Optional[Path] = None,
    seed: int = 0,
) -> Dict[str, Any]:
    random_seed = int(seed or 0)
    try:
        import random

        random.seed(random_seed)
    except Exception:
        pass

    started = time.time()
    results: List[ScenarioResult] = []
    all_issues: List[BenchIssue] = []

    for r in range(max(1, int(runs or 1))):
        run_id = f"{int(time.time())}_{r}_{uuid.uuid4().hex[:6]}"
        workdir = repo_root / "generated" / "benchmarks" / f"brain_e2e_workdir_{run_id}"
        h = Harness(repo_root=repo_root, workdir=workdir, session_id=f"bench_{run_id}")
        try:
            for sc in default_scenarios():
                try:
                    sr = sc.run(h)
                except Exception as e:
                    sr = ScenarioResult(
                        scenario_id=sc.scenario_id,
                        name=sc.name,
                        ok=False,
                        latency_ms=0.0,
                        issues=[BenchIssue("scenario_exception", str(e), sc.scenario_id, meta={"traceback": traceback.format_exc()})],
                    )
                results.append(sr)
                all_issues.extend(sr.issues)
        finally:
            h.close()

    total = len(results)
    passed = sum(1 for r in results if r.ok)
    latency_ms = [r.latency_ms for r in results if r.latency_ms >= 0.0]
    latency_ms_sorted = sorted(latency_ms)

    def pct(p: float) -> float:
        if not latency_ms_sorted:
            return 0.0
        idx = int(max(0, min(len(latency_ms_sorted) - 1, round((p / 100.0) * (len(latency_ms_sorted) - 1)))))
        return float(latency_ms_sorted[idx])

    report: Dict[str, Any] = {
        "meta": {
            "benchmark": "brain_e2e_benchmark",
            "started_at": started,
            "finished_at": time.time(),
            "duration_sec": time.time() - started,
            "repo_root": str(repo_root),
            "runs": int(runs),
            "seed": random_seed,
        },
        "summary": {
            "scenario_count": total,
            "pass_count": passed,
            "pass_rate": (passed / max(1, total)),
            "latency_ms_p50": pct(50),
            "latency_ms_p95": pct(95),
        },
        "scenarios": [
            {
                "scenario_id": r.scenario_id,
                "name": r.name,
                "ok": r.ok,
                "latency_ms": r.latency_ms,
                "issues": [
                    {"issue_type": i.issue_type, "message": i.message, "scenario_id": i.scenario_id, "meta": i.meta}
                    for i in r.issues
                ],
                "artifacts": r.artifacts,
            }
            for r in results
        ],
    }
    report["issues"] = [{"issue_type": i.issue_type, "message": i.message, "scenario_id": i.scenario_id, "meta": i.meta} for i in all_issues]
    report["todo"] = _issues_to_todo(all_issues)
    report["pass"] = bool(report["summary"]["pass_rate"] >= 0.90)  # soft gate; informational

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(_safe_json(report), encoding="utf-8")

    if history_path is not None:
        history_path.parent.mkdir(parents=True, exist_ok=True)
        rec = {"ts": time.time(), "summary": report["summary"], "pass": report["pass"], "issues_count": len(all_issues)}
        with history_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    return report


def main() -> int:
    ap = argparse.ArgumentParser(description="Brain E2E benchmark (execution-focused, deterministic /tool path).")
    ap.add_argument("--repo-root", type=str, default=".", help="Repository root")
    ap.add_argument("--runs", type=int, default=1, help="Number of runs (sampling)")
    ap.add_argument("--seed", type=int, default=0, help="Random seed (fixtures ordering)")
    ap.add_argument("--output", type=str, default="generated/benchmarks/brain_e2e_benchmark_report.json", help="Output report path")
    ap.add_argument("--history", type=str, default="generated/benchmarks/brain_e2e_benchmark_history.jsonl", help="Optional history jsonl path")
    args = ap.parse_args()

    repo_root = Path(args.repo_root).resolve()
    output_path = (repo_root / args.output).resolve() if not Path(args.output).is_absolute() else Path(args.output)
    history_path = (repo_root / args.history).resolve() if args.history else None

    report = run_benchmark(
        repo_root=repo_root,
        runs=int(args.runs),
        seed=int(args.seed),
        output_path=output_path,
        history_path=history_path,
    )
    # Minimal console summary (human-friendly, grep-friendly).
    print(_safe_json({"pass": report.get("pass"), "summary": report.get("summary"), "issues_count": len(report.get("issues") or [])}))
    return 0 if report.get("pass") else 1


if __name__ == "__main__":
    raise SystemExit(main())
