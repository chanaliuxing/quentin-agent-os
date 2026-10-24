#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Optional


@dataclass
class StepResult:
    name: str
    cmd: list[str]
    returncode: int
    duration_sec: float
    ok: bool
    stdout_tail: str
    stderr_tail: str
    done: Optional[bool] = None
    done_confidence: Optional[float] = None


def _tail(text: str, limit: int = 4000) -> str:
    return str(text or "")[-limit:]


def _run_step(*, name: str, cmd: list[str], cwd: Path, env: dict[str, str], timeout_sec: int) -> StepResult:
    t0 = time.time()
    try:
        cp = subprocess.run(
            cmd,
            cwd=str(cwd),
            env=env,
            capture_output=True,
            text=True,
            timeout=max(1, int(timeout_sec)),
        )
        out = str(cp.stdout or "")
        err = str(cp.stderr or "")
        return StepResult(
            name=name,
            cmd=cmd,
            returncode=int(cp.returncode),
            duration_sec=round(time.time() - t0, 3),
            ok=int(cp.returncode) == 0,
            stdout_tail=_tail(out),
            stderr_tail=_tail(err),
        )
    except subprocess.TimeoutExpired as e:
        return StepResult(
            name=name,
            cmd=cmd,
            returncode=124,
            duration_sec=round(time.time() - t0, 3),
            ok=False,
            stdout_tail=_tail(str(e.stdout or "")),
            stderr_tail=_tail(str(e.stderr or "")) + f"\nstep_timeout_sec={int(timeout_sec)}",
        )


def _parse_canary_done(stdout_tail: str) -> tuple[Optional[bool], Optional[float]]:
    m_done = re.search(r"^\s*Done:\s*(True|False)\s*$", stdout_tail, re.MULTILINE)
    m_conf = re.search(r"^\s*Confidence:\s*([0-9]*\.?[0-9]+)\s*$", stdout_tail, re.MULTILINE)
    done = None if not m_done else (m_done.group(1) == "True")
    conf = None
    if m_conf:
        try:
            conf = float(m_conf.group(1))
        except Exception:
            conf = None
    return done, conf


def _default_env(base: dict[str, str], *, offline_smoke: bool) -> dict[str, str]:
    env = dict(base)
    # Keep runtime checks truthful to the caller's real environment.
    env.setdefault("QUENTIN_REQUIRE_CHAMPION", "1")
    if offline_smoke:
        env["QUENTIN_LLM_FORCE_STUB"] = "1"
        env["LLM_STUB"] = "1"
    return env


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Self-iteration gate: champion guards + canary brain run.")
    p.add_argument("--repo-root", default=".", help="Repository root path.")
    p.add_argument("--offline-smoke", action="store_true", help="Run canary in deterministic offline smoke mode.")
    p.add_argument(
        "--input-text",
        default="/status",
        help="Input text for canary run (default: deterministic /status health command).",
    )
    p.add_argument(
        "--allow-not-done",
        action="store_true",
        help="Allow gate to pass even when canary Done=False (not recommended).",
    )
    p.add_argument("--timeout-sec", type=int, default=300, help="Per-step timeout seconds.")
    p.add_argument(
        "--report-out",
        default="data/landing/brain_self_iteration_gate_report.json",
        help="Report output path.",
    )
    return p.parse_args()


def main() -> int:
    args = _parse_args()
    root = Path(args.repo_root).resolve()
    py = str(root / ".venv" / "bin" / "python")
    if not Path(py).exists():
        py = sys.executable

    env = _default_env(os.environ, offline_smoke=bool(args.offline_smoke))
    steps: list[StepResult] = []

    steps.append(
        _run_step(
            name="check_champion_env",
            cmd=[py, str(root / "scripts" / "check_champion_env.py"), "--strict"],
            cwd=root,
            env=env,
            timeout_sec=int(args.timeout_sec),
        )
    )
    steps.append(
        _run_step(
            name="check_champion_runtime",
            cmd=[py, str(root / "scripts" / "check_champion_runtime.py"), "--strict"],
            cwd=root,
            env=env,
            timeout_sec=int(args.timeout_sec),
        )
    )

    canary_cmd = [
        py,
        str(root / "scripts" / "run_canary_brain_once.py"),
        "--require-champion",
        "--input-text",
        str(args.input_text or "/status"),
    ]
    if bool(args.offline_smoke):
        canary_cmd.append("--offline-smoke")
    canary = _run_step(
        name="canary_brain_once",
        cmd=canary_cmd,
        cwd=root,
        env=env,
        timeout_sec=int(args.timeout_sec),
    )
    done, conf = _parse_canary_done(canary.stdout_tail)
    canary.done = done
    canary.done_confidence = conf
    steps.append(canary)

    strict_done = not bool(args.allow_not_done)
    ok = all(s.ok for s in steps)
    if strict_done:
        ok = ok and (canary.done is True)

    report = {
        "ok": bool(ok),
        "strict_done": bool(strict_done),
        "offline_smoke": bool(args.offline_smoke),
        "generated_at": int(time.time()),
        "steps": [asdict(s) for s in steps],
    }
    out_path = Path(args.report_out)
    if not out_path.is_absolute():
        out_path = root / out_path
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"ok": bool(ok), "report": str(out_path)}, ensure_ascii=False))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
