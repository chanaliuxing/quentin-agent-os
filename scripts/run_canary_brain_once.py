#!/usr/bin/env python3
# scripts/run_canary_brain_once.py

from __future__ import annotations

import argparse
import json
import multiprocessing as mp
import os
import re
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Tuple

# Ensure project root is in sys.path
repo_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(repo_root))

from quentin.runtime.brain_daemon import brain_daemon_from_env


def _is_truthy(raw: str | None) -> bool:
    return str(raw or "").strip().lower() in ("1", "true", "yes", "on")


def _apply_base_env() -> None:
    # 1. Force Canary Mode
    os.environ["QUENTIN_CANARY"] = "1"
    # 2. Configure Environment (ensure sandbox)
    os.environ["QUENTIN_ENV"] = "sandbox"
    # 3. Forbid auto-apply (double safety)
    os.environ["META_AGENT_PATCHFLOW_AUTO_APPLY"] = "0"
    os.environ["QUENTIN_BLUEPRINT_AUTOPATCH_RUN_SELFPROG"] = "1"
    # 4. Prefer direct input task only (avoid stale observability backlog hijacking canary runs)
    os.environ["QUENTIN_TASK_SOURCE_OBS"] = "0"
    # 5. Keep canary bounded: avoid long hanging loops on weak local models.
    os.environ["QUENTIN_MAX_LOOPS"] = "2"
    # 6. Default canary should exercise live model path, not offline stub.
    os.environ["QUENTIN_LLM_FORCE_STUB"] = "0"
    os.environ["LLM_STUB"] = "0"
    # 7. Local models may be slow; use generous timeouts to avoid premature failure.
    os.environ["QUENTIN_LLM_TIMEOUT_LOCAL_S"] = "420"
    os.environ["QUENTIN_OLLAMA_READ_TIMEOUT_S"] = "0"
    os.environ["QUENTIN_COUNCIL_MEMBER_TIMEOUT_S"] = "180"
    os.environ["QUENTIN_COUNCIL_ARBITER_TIMEOUT_S"] = "420"
    os.environ["QUENTIN_COUNCIL_LOCAL_MEMBER_TIMEOUT_S"] = "420"
    os.environ["QUENTIN_COUNCIL_LOCAL_ARBITER_TIMEOUT_S"] = "900"
    # 8. Canary validates planner/executor/memory/tool path first; disable reflection retries.
    os.environ["QUENTIN_REFLECTION_ENABLED"] = "0"
    os.environ["QUENTIN_DONE_COUNCIL_ENABLED"] = "0"
    os.environ["QUENTIN_ENABLE_PRE_SENSING"] = "0"
    os.environ["QUENTIN_BRAIN_RUN_SLEEP"] = "0"
    os.environ["QUENTIN_BRAIN_RUN_IMMUNE"] = "0"


def _apply_offline_smoke_env() -> None:
    # Offline deterministic mode for one-command smoke validation.
    os.environ["QUENTIN_LLM_FORCE_STUB"] = "1"
    os.environ["LLM_STUB"] = "1"
    # Keep full brain loops enabled in smoke mode.
    os.environ["QUENTIN_BRAIN_RUN_SLEEP"] = "1"
    os.environ["QUENTIN_BRAIN_RUN_IMMUNE"] = "1"


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Run one canary brain cycle.")
    p.add_argument(
        "--input-text",
        default="Perform a system self-check and identify any immediate capability gaps or anomalies.",
        help="Task prompt for this canary run.",
    )
    p.add_argument(
        "--offline-smoke",
        action="store_true",
        help="Force local deterministic stub mode suitable for CI/smoke runs.",
    )
    p.add_argument(
        "--require-champion",
        action="store_true",
        help="Require champion runtime guard (same effect as QUENTIN_REQUIRE_CHAMPION=1).",
    )
    p.add_argument(
        "--max-loops",
        type=int,
        default=2,
        help="Override QUENTIN_MAX_LOOPS for this canary run.",
    )
    p.add_argument(
        "--expect-file",
        default="",
        help="Optional relative file path that must exist after run (acceptance gate).",
    )
    p.add_argument(
        "--expect-file-content",
        default="",
        help="Optional exact content check for --expect-file.",
    )
    p.add_argument(
        "--timeout-sec",
        type=int,
        default=0,
        help="Optional hard timeout (seconds) for daemon.run_once. 0 means no forced timeout.",
    )
    p.add_argument(
        "--heartbeat-sec",
        type=int,
        default=10,
        help="Monitoring heartbeat interval while canary is running. 0 disables monitor mode.",
    )
    p.add_argument(
        "--idle-timeout-sec",
        type=int,
        default=0,
        help="Timeout only when no observable progress for N seconds. 0 disables.",
    )
    p.add_argument(
        "--session-id",
        default="",
        help="Optional session id for canary run. Default generates a unique canary session.",
    )
    p.add_argument(
        "--guard-timeout-sec",
        type=int,
        default=45,
        help="Timeout for champion runtime guard check.",
    )
    p.add_argument(
        "--guard-qdrant-timeout-sec",
        type=float,
        default=5.0,
        help="Qdrant timeout used only by champion runtime guard subprocess.",
    )
    return p.parse_args()


def _run_once_worker(input_text: str, metadata: dict[str, object], q: mp.Queue) -> None:
    stop = threading.Event()

    def _heartbeat_loop() -> None:
        while not stop.wait(2.0):
            try:
                q.put_nowait({"type": "heartbeat", "ts": time.time()})
            except Exception:
                pass

    hb = threading.Thread(target=_heartbeat_loop, daemon=True)
    hb.start()
    try:
        daemon = brain_daemon_from_env()
        report = daemon.run_once(input_text=input_text, metadata=metadata)
        q.put({"type": "report", "ok": True, "report": report})
    except Exception as e:  # noqa: BLE001
        q.put({"type": "report", "ok": False, "error": repr(e)})
    finally:
        stop.set()


def _activity_snapshot() -> Tuple[int, int]:
    paths = [
        repo_root / "data" / "audit_events.jsonl",
        repo_root / "data" / "traces" / "events.jsonl",
        repo_root / "data" / "goals.jsonl",
        repo_root / "data" / "llm_raw_history.jsonl",
    ]
    total_size = 0
    latest_mtime_ns = 0
    for p in paths:
        try:
            st = p.stat()
            total_size += int(st.st_size)
            latest_mtime_ns = max(latest_mtime_ns, int(getattr(st, "st_mtime_ns", int(st.st_mtime * 1e9))))
        except Exception:
            continue
    return total_size, latest_mtime_ns


def _parse_ps_time_to_seconds(raw: str) -> float:
    s = str(raw or "").strip()
    if not s:
        return 0.0
    # Formats: MM:SS, HH:MM:SS, DD-HH:MM:SS
    m = re.fullmatch(r"(?:(?P<days>\d+)-)?(?:(?P<h>\d+):)?(?P<m>\d{1,2}):(?P<s>\d{2})", s)
    if not m:
        return 0.0
    days = int(m.group("days") or 0)
    hours = int(m.group("h") or 0)
    mins = int(m.group("m") or 0)
    secs = int(m.group("s") or 0)
    return float(days * 86400 + hours * 3600 + mins * 60 + secs)


def _probe_process_runtime(pid: int) -> dict:
    probe = {
        "state": "",
        "cpu_seconds": 0.0,
        "cpu_ok": False,
        "has_llm_conn": False,
    }
    try:
        ps = subprocess.run(
            ["ps", "-p", str(int(pid)), "-o", "state=", "-o", "time="],
            capture_output=True,
            text=True,
            timeout=2,
        )
        if ps.returncode == 0:
            line = str(ps.stdout or "").strip()
            if line:
                parts = line.split()
                if len(parts) >= 2:
                    probe["state"] = str(parts[0] or "")
                    probe["cpu_seconds"] = _parse_ps_time_to_seconds(parts[1])
                    probe["cpu_ok"] = True
    except Exception:
        pass
    try:
        lsof = subprocess.run(
            ["lsof", "-nP", "-a", "-p", str(int(pid)), "-iTCP"],
            capture_output=True,
            text=True,
            timeout=2,
        )
        if lsof.returncode == 0:
            txt = str(lsof.stdout or "")
            probe["has_llm_conn"] = any(
                k in txt
                for k in (
                    ":11434",
                    ":11435",
                    ":11436",
                )
            )
    except Exception:
        pass
    return probe


def _local_ollama_preflight(*, base_url: str, model: str) -> Tuple[bool, str]:
    normalized = str(base_url or "").strip().rstrip("/")
    model_name = str(model or "").strip()
    if not normalized:
        return False, "missing_llm_base_url"
    if not model_name:
        return False, "missing_llm_model"
    tags_url = f"{normalized}/api/tags"
    try:
        with urllib.request.urlopen(tags_url, timeout=2.0) as resp:
            payload = json.loads(resp.read().decode("utf-8", errors="ignore") or "{}")
    except Exception as e:  # noqa: BLE001
        return False, f"ollama_tags_unreachable:{e}"
    models = payload.get("models") if isinstance(payload, dict) else []
    if not isinstance(models, list):
        models = []
    names = {
        str(item.get("name") or item.get("model") or "").strip()
        for item in models
        if isinstance(item, dict)
    }
    if model_name not in names:
        return False, f"ollama_model_missing:{model_name}"
    return True, f"ollama_ready:{model_name}"


def main() -> int:
    args = _parse_args()
    print("=== Quentin Canary Brain Run ===")

    _apply_base_env()
    session_id = str(args.session_id or "").strip() or f"canary-{int(time.time()*1000)}"
    os.environ["QUENTIN_BRAIN_SESSION"] = session_id
    if bool(args.offline_smoke):
        _apply_offline_smoke_env()
    if bool(args.require_champion):
        os.environ["QUENTIN_REQUIRE_CHAMPION"] = "1"
    if int(args.max_loops or 0) > 0:
        os.environ["QUENTIN_MAX_LOOPS"] = str(int(args.max_loops))
    print(
        "LLM route: "
        f"provider={os.getenv('LLM_PROVIDER', '') or '<unset>'}, "
        f"model={os.getenv('LLM_MODEL', '') or '<unset>'}, "
        f"force_stub={os.getenv('QUENTIN_LLM_FORCE_STUB', '') or '<unset>'}, "
        f"llm_stub={os.getenv('LLM_STUB', '') or '<unset>'}"
    )
    print(f"Canary session: {session_id}")

    llm_provider = str(os.getenv("LLM_PROVIDER", "") or "ollama").strip().lower()
    if not bool(args.offline_smoke) and llm_provider == "ollama":
        ok, detail = _local_ollama_preflight(
            base_url=os.getenv("LLM_BASE_URL", "http://localhost:11434"),
            model=os.getenv("LLM_MODEL", ""),
        )
        if not ok:
            print(f"Canary preflight failed: {detail}")
            return 7
        print(f"Canary preflight ok: {detail}")

    # 5. Initialize Daemon
    if _is_truthy(os.environ.get("QUENTIN_REQUIRE_CHAMPION")):
        cmd = [sys.executable, str(repo_root / "scripts" / "check_champion_runtime.py"), "--strict"]
        guard_env = dict(os.environ)
        guard_env.setdefault("QUENTIN_QDRANT_TIMEOUT_S", str(float(args.guard_qdrant_timeout_sec or 5.0)))
        try:
            guard = subprocess.run(
                cmd,
                cwd=str(repo_root),
                env=guard_env,
                capture_output=True,
                text=True,
                timeout=max(1, int(args.guard_timeout_sec or 45)),
            )
        except subprocess.TimeoutExpired:
            print(f"Champion runtime guard failed: timeout after {int(args.guard_timeout_sec or 45)}s")
            return 2
        if guard.returncode != 0:
            print("Champion runtime guard failed.")
            print((guard.stdout or "")[-2000:])
            print((guard.stderr or "")[-2000:])
            return 2

    # 6. Run one cycle with a smoke task
    input_text = str(args.input_text or "").strip()
    print(f"Running brain cycle with task: {input_text}")

    try:
        timeout_sec = int(args.timeout_sec or 0)
        heartbeat_raw = int(args.heartbeat_sec or 0)
        expected_rel = str(args.expect_file or "").strip()
        expected_target = (repo_root / expected_rel).resolve() if expected_rel else None
        expected_content = str(args.expect_file_content or "")
        early_accept = False
        if timeout_sec <= 0 and heartbeat_raw <= 0:
            daemon = brain_daemon_from_env()
            report = daemon.run_once(input_text=input_text, metadata={"topic": "canary_smoke", "session_id": session_id})
        else:
            heartbeat_sec = max(1, heartbeat_raw or 10)
            idle_timeout_sec = max(0, int(args.idle_timeout_sec or 0))
            q: mp.Queue = mp.Queue(maxsize=128)
            proc = mp.Process(
                target=_run_once_worker,
                args=(input_text, {"topic": "canary_smoke", "session_id": session_id}, q),
                daemon=True,
            )
            proc.start()
            started_at = time.time()
            last_progress_at = started_at
            last_heartbeat_at = started_at
            last_snapshot = _activity_snapshot()
            last_probe = _probe_process_runtime(proc.pid) if proc.pid else {"cpu_seconds": 0.0, "cpu_ok": False}
            last_state = "unknown"
            report_payload: dict | None = None
            while proc.is_alive():
                proc.join(timeout=float(heartbeat_sec))
                while True:
                    try:
                        msg = q.get_nowait()
                    except Exception:
                        break
                    if isinstance(msg, dict) and msg.get("type") == "heartbeat":
                        last_heartbeat_at = time.time()
                    elif isinstance(msg, dict) and msg.get("type") == "report":
                        report_payload = msg
                        last_progress_at = time.time()
                if proc.is_alive():
                    elapsed = int(time.time() - started_at)
                    now_snapshot = _activity_snapshot()
                    probe = _probe_process_runtime(proc.pid) if proc.pid else {"cpu_seconds": 0.0, "cpu_ok": False, "has_llm_conn": False}
                    cpu_progress = False
                    if bool(probe.get("cpu_ok")) and bool(last_probe.get("cpu_ok")):
                        cpu_progress = float(probe.get("cpu_seconds") or 0.0) > float(last_probe.get("cpu_seconds") or 0.0)

                    if now_snapshot != last_snapshot:
                        last_snapshot = now_snapshot
                        last_progress_at = time.time()
                        last_state = "working_io"
                        print(f"[monitor] state=working_io pid={proc.pid} elapsed={elapsed}s")
                    elif cpu_progress:
                        last_progress_at = time.time()
                        last_state = "working_cpu"
                        print(f"[monitor] state=working_cpu pid={proc.pid} elapsed={elapsed}s")
                    elif bool(probe.get("has_llm_conn")):
                        last_state = "waiting_llm_response"
                        print(f"[monitor] state=waiting_llm_response pid={proc.pid} elapsed={elapsed}s")
                    else:
                        last_state = "idle_or_stuck"
                        print(f"[monitor] state=idle_or_stuck pid={proc.pid} elapsed={elapsed}s")
                    last_probe = probe
                    if expected_target is not None and expected_target.exists():
                        content_ok = True
                        if expected_content:
                            try:
                                actual = expected_target.read_text(encoding="utf-8", errors="ignore")
                            except Exception:
                                content_ok = False
                            else:
                                content_ok = actual == expected_content
                        if content_ok:
                            early_accept = True
                            print(f"[monitor] canary acceptance reached early via file artifact: {expected_rel}")
                            proc.terminate()
                            proc.join(timeout=5.0)
                            break
                    if timeout_sec > 0 and elapsed >= timeout_sec:
                        proc.terminate()
                        proc.join(timeout=5.0)
                        print(f"Canary run failed: timeout after {timeout_sec}s")
                        return 4
                    idle_elapsed = int(time.time() - last_progress_at)
                    if idle_timeout_sec > 0 and idle_elapsed >= idle_timeout_sec:
                        proc.terminate()
                        proc.join(timeout=5.0)
                        if last_state == "waiting_llm_response":
                            print(
                                "Canary run failed: llm-no-response "
                                f"(state={last_state}, idle={idle_elapsed}s, heartbeat_age={int(time.time()-last_heartbeat_at)}s)"
                            )
                            return 6
                        print(
                            "Canary run failed: process-stuck "
                            f"(state={last_state}, idle={idle_elapsed}s, heartbeat_age={int(time.time()-last_heartbeat_at)}s)"
                        )
                        return 5
            if report_payload is None and not early_accept:
                while True:
                    try:
                        msg = q.get_nowait()
                    except Exception:
                        break
                    if isinstance(msg, dict) and msg.get("type") == "report":
                        report_payload = msg
                        break
            if report_payload is None and not early_accept:
                print("Canary run failed: no report received from worker process")
                return 1
            if early_accept:
                report = {
                    "task_id": "early_accept_file_gate",
                    "done": True,
                    "done_confidence": 1.0,
                    "patchflow_report": {"processed": 0, "applied": 0, "blocked": 0, "rejected": 0, "processed_ids": []},
                }
            else:
                payload = report_payload
                if not bool(payload.get("ok")):
                    print(f"Canary run failed: {payload.get('error')}")
                    return 1
                report = payload.get("report") or {}

        print("\n=== Canary Run Report ===")
        print(f"Task ID: {report.get('task_id')}")
        print(f"Done: {report.get('done')}")
        print(f"Confidence: {report.get('done_confidence')}")

        if report.get("patchflow_report"):
            print(f"PatchFlow: {json.dumps(report.get('patchflow_report'), indent=2)}")

        print("\nAudit logs located in: data/audit_events.jsonl")
        print("Trace logs located in: data/traces/events.jsonl")

        expected = expected_rel
        if expected:
            target = expected_target if expected_target is not None else (repo_root / expected).resolve()
            if not target.exists():
                print(f"Canary acceptance failed: expected file missing: {expected}")
                return 3
            expect_content = expected_content
            if expect_content:
                try:
                    actual = target.read_text(encoding="utf-8", errors="ignore")
                except Exception as e:  # noqa: BLE001
                    print(f"Canary acceptance failed: unable to read expected file: {e}")
                    return 3
                if actual != expect_content:
                    print(
                        "Canary acceptance failed: expected file content mismatch "
                        f"(path={expected}, expected={expect_content!r}, actual={actual!r})"
                    )
                    return 3

    except Exception as e:
        print(f"Canary run failed: {e}")
        return 1
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
