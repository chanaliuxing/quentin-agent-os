from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import List


@dataclass
class StepResult:
    name: str
    command: List[str]
    returncode: int
    duration_ms: float
    stdout_tail: str
    stderr_tail: str


def _run_step(name: str, command: List[str], *, cwd: Path, dry_run: bool) -> StepResult:
    if dry_run:
        return StepResult(
            name=name,
            command=command,
            returncode=0,
            duration_ms=0.0,
            stdout_tail="[dry-run]",
        stderr_tail="",
    )


def _run_step_with_timeout(
    name: str,
    command: List[str],
    *,
    cwd: Path,
    dry_run: bool,
    timeout_sec: int,
) -> StepResult:
    if dry_run:
        return _run_step(name, command, cwd=cwd, dry_run=True)
    started = time.perf_counter()
    try:
        proc = subprocess.run(
            command,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=max(1, int(timeout_sec)),
        )
        duration_ms = (time.perf_counter() - started) * 1000.0
        return StepResult(
            name=name,
            command=command,
            returncode=int(proc.returncode),
            duration_ms=float(duration_ms),
            stdout_tail=(proc.stdout or "")[-4000:],
            stderr_tail=(proc.stderr or "")[-4000:],
        )
    except subprocess.TimeoutExpired as e:
        duration_ms = (time.perf_counter() - started) * 1000.0
        return StepResult(
            name=name,
            command=command,
            returncode=124,
            duration_ms=float(duration_ms),
            stdout_tail=(str(e.stdout or ""))[-4000:],
            stderr_tail=(str(e.stderr or ""))[-4000:] + f"\nstep_timeout_sec={int(timeout_sec)}",
        )
    started = time.perf_counter()
    proc = subprocess.run(command, cwd=str(cwd), capture_output=True, text=True)
    duration_ms = (time.perf_counter() - started) * 1000.0
    return StepResult(
        name=name,
        command=command,
        returncode=int(proc.returncode),
        duration_ms=float(duration_ms),
        stdout_tail=(proc.stdout or "")[-4000:],
        stderr_tail=(proc.stderr or "")[-4000:],
    )


def _build_steps(repo_root: Path, *, quick: bool) -> list[tuple[str, list[str]]]:
    py = str(repo_root / ".venv" / "bin" / "python")
    if not Path(py).exists():
        py = sys.executable

    unit_tests = [
        "tests/unit/test_cognitive_immune_action_linkage.py",
        "tests/unit/test_perception_layer_v0.py",
        "tests/unit/test_situation_skill_router.py",
        "tests/unit/test_expectation_engine_v0.py",
        "tests/unit/test_immune_loop_prediction_errors.py",
        "tests/unit/test_sleep_loop_gist_outputs.py",
        "tests/unit/test_tool_knowledge_sink.py",
        "tests/unit/test_tool_governance_aggregate_veto.py",
        "tests/unit/test_tool_governance_gate.py",
        "tests/unit/test_dual_track_router_v0.py",
        "tests/unit/test_dual_track_acquirer_v0.py",
        "tests/unit/test_mcp_tool_provider_disabled.py",
        "tests/unit/test_mcp_tool_provider_whitelist_and_backend_injection.py",
        "tests/unit/test_mcp_tool_invocation_stub.py",
        "tests/integration/test_memory_kind_recall_regression_large.py",
    ]
    integration_tests = [
        "tests/integration/test_check_champion_env_runs.py",
        "tests/integration/test_champion_store_end_to_end.py",
    ]

    scale_args = [
        py,
        str(repo_root / "scripts" / "run_memory_champion_scale.py"),
        "--n-records",
        "600" if not quick else "300",
        "--queries",
        "80" if not quick else "40",
        "--workers",
        "8" if not quick else "4",
        "--dim",
        "16",
        "--top-k",
        "10",
        "--min-hit-rate",
        "0.90" if not quick else "0.80",
        "--p95-ms-max",
        "1500" if not quick else "3000",
        "--require-qdrant-ready",
        "--expect-vec-ready",
        "1",
    ]

    slo_pipeline_args = [
        py,
        str(repo_root / "scripts" / "run_memory_slo_pipeline.py"),
        "--backend",
        "champion",
        "--vector-backend",
        "qdrant",
        "--n",
        "600" if not quick else "300",
        "--tiers",
        "600" if not quick else "300",
        "--runs",
        "1",
        "--warmup",
        "0",
        "--dim",
        "16",
        "--top-k",
        "10",
        "--bench-out",
        "data/bench/recall_bench_champion.jsonl",
        "--slo-in",
        "config/memory_recall_slo_champion.json",
        "--slo-out",
        "config/memory_recall_slo_champion.generated.json",
        "--fail-on-slo",
    ]

    return [
        (
            "champion_env_strict_check",
            [py, str(repo_root / "scripts" / "check_champion_env.py"), "--strict"],
        ),
        (
            "champion_runtime_strict_check",
            [
                "env",
                "QUENTIN_MEMORY_STORE=champion",
                "MEM_EMBED_PROVIDER=disabled",
                "MEM_EMBED_DIM=16",
                "QUENTIN_QDRANT_WAIT_READY=1",
                py,
                str(repo_root / "scripts" / "check_champion_runtime.py"),
                "--strict",
            ],
        ),
        (
            "memory_runtime_tier_boundary_check",
            [py, str(repo_root / "scripts" / "check_memory_runtime_tiers.py")],
        ),
        (
            "cognitive_policy_tuning_proposal",
            [py, str(repo_root / "scripts" / "propose_cognitive_policy_tuning.py")],
        ),
        (
            "v3_1_unit_keychain_tests",
            ["env", "QUENTIN_MEMORY_STORE=sqlite", py, "-m", "pytest", *unit_tests, "-q", "-x"],
        ),
        (
            "v3_1_champion_integration_tests",
            [py, "-m", "pytest", *integration_tests, "-q", "-x"],
        ),
        (
            "champion_slo_rebaseline_gate",
            slo_pipeline_args,
        ),
        (
            "champion_scale_acceptance",
            scale_args,
        ),
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description="Blueprint v3.1 formal landing runner.")
    parser.add_argument("--repo-root", default=".", help="Repository root")
    parser.add_argument("--quick", action="store_true", help="Use lighter scale acceptance parameters")
    parser.add_argument("--dry-run", action="store_true", help="Print/record commands only")
    parser.add_argument(
        "--report-out",
        default="data/landing/blueprint_v3_1_landing_report.json",
        help="Report output path",
    )
    parser.add_argument("--step-timeout-sec", type=int, default=600, help="Per-step timeout in seconds.")
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    os.environ.setdefault("PG_HOST", "127.0.0.1")
    os.environ.setdefault("PG_PORT", "55432")
    os.environ.setdefault("PG_USER", "postgres")
    os.environ.setdefault("PG_PASSWORD", "postgres")
    os.environ.setdefault("PG_DB", "quentin_memory")
    os.environ.setdefault("QDRANT_URL", "http://localhost:6333")

    steps = _build_steps(repo_root, quick=bool(args.quick))

    results: list[StepResult] = []
    overall_ok = True
    for name, cmd in steps:
        res = _run_step_with_timeout(
            name,
            cmd,
            cwd=repo_root,
            dry_run=bool(args.dry_run),
            timeout_sec=int(args.step_timeout_sec),
        )
        results.append(res)
        if res.returncode != 0:
            overall_ok = False
            break

    report = {
        "ok": bool(overall_ok),
        "quick": bool(args.quick),
        "dry_run": bool(args.dry_run),
        "steps": [asdict(r) for r in results],
    }
    out_path = Path(args.report_out)
    if not out_path.is_absolute():
        out_path = (repo_root / out_path).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"ok": overall_ok, "report": str(out_path)}, ensure_ascii=False))
    return 0 if overall_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
