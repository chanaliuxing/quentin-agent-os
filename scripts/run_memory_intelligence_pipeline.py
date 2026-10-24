from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


def _run(cmd: list[str], *, cwd: Path) -> int:
    proc = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True)
    if proc.stdout:
        print(proc.stdout.rstrip())
    if proc.stderr:
        print(proc.stderr.rstrip(), file=sys.stderr)
    return int(proc.returncode)


def main() -> None:
    p = argparse.ArgumentParser(description="Run intelligence-first memory benchmark pipeline.")
    p.add_argument("--backend", default="sqlite_vec", choices=["sqlite", "sqlite_vec"])
    p.add_argument("--n", default="10000,100000")
    p.add_argument("--modes", default="text_only,vector_only,hybrid")
    p.add_argument("--case-profile", default="mixed", choices=["basic", "mixed"])
    p.add_argument("--query-domain-policy", default="case", choices=["none", "case"])
    p.add_argument("--cases", type=int, default=40)
    p.add_argument("--runs", type=int, default=5)
    p.add_argument("--warmup", type=int, default=1)
    p.add_argument("--dim", type=int, default=768)
    p.add_argument("--top-k", type=int, default=10)
    p.add_argument("--db-dir", default="data/bench")
    p.add_argument("--out", default="data/bench/memory_intelligence_bench.jsonl")
    p.add_argument("--slo-file", default="config/memory_intelligence_slo.json")
    p.add_argument("--fail-on-slo", action="store_true")
    p.add_argument("--require-index-backend", action="store_true")
    p.add_argument("--skip-precheck", action="store_true")
    args = p.parse_args()

    repo_root = Path(__file__).resolve().parent.parent

    if str(args.backend) == "sqlite_vec" and not bool(args.skip_precheck):
        pre_cmd = [
            sys.executable,
            str(repo_root / "scripts" / "check_sqlite_vec_env.py"),
            "--strict",
        ]
        print({"stage": "precheck", "backend": "sqlite_vec"})
        rc = _run(pre_cmd, cwd=repo_root)
        if rc != 0:
            raise SystemExit(rc)

    bench_cmd = [
        sys.executable,
        str(repo_root / "scripts" / "bench_memory_intelligence.py"),
        "--backend",
        str(args.backend),
        "--n",
        str(args.n),
        "--modes",
        str(args.modes),
        "--cases",
        str(args.cases),
        "--case-profile",
        str(args.case_profile),
        "--query-domain-policy",
        str(args.query_domain_policy),
        "--runs",
        str(args.runs),
        "--warmup",
        str(args.warmup),
        "--dim",
        str(args.dim),
        "--top-k",
        str(args.top_k),
        "--db-dir",
        str(args.db_dir),
        "--out",
        str(args.out),
        "--slo-file",
        str(args.slo_file),
    ]
    if bool(args.fail_on_slo):
        bench_cmd.append("--fail-on-slo")
    if bool(args.require_index_backend):
        bench_cmd.append("--require-index-backend")

    print({"stage": "benchmark", "backend": str(args.backend), "n": str(args.n)})
    rc = _run(bench_cmd, cwd=repo_root)
    if rc != 0:
        raise SystemExit(rc)

    print({"status": "ok", "out": str(args.out)})


if __name__ == "__main__":
    main()
