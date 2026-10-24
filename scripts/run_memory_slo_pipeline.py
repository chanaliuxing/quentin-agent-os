from __future__ import annotations

import argparse
import os
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
    parser = argparse.ArgumentParser(
        description="Run memory benchmark and generate SLO config in one pipeline."
    )
    parser.add_argument("--backend", default="sqlite_vec", choices=["sqlite", "sqlite_vec", "champion"])
    parser.add_argument("--vector-backend", default="", help="Expected vector backend for rebaseline filter.")
    parser.add_argument("--n", default="10000,100000,1000000")
    parser.add_argument("--modes", default="text_only,vector_only,hybrid")
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--warmup", type=int, default=1)
    parser.add_argument("--dim", type=int, default=64)
    parser.add_argument("--top-k", type=int, default=10)
    parser.add_argument("--db-dir", default="data/bench")
    parser.add_argument("--bench-out", default="data/bench/recall_bench.jsonl")
    parser.add_argument("--slo-in", default="config/memory_recall_slo.json")
    parser.add_argument("--slo-out", default="config/memory_recall_slo.generated.json")
    parser.add_argument("--tiers", default="10000,100000,1000000")
    parser.add_argument(
        "--require-index-backend",
        action="store_true",
        help="Fail benchmark when requested indexed backend is not active.",
    )
    parser.add_argument(
        "--fail-on-slo",
        action="store_true",
        help="Fail pipeline when benchmark violates slo-in thresholds.",
    )
    parser.add_argument(
        "--skip-precheck",
        action="store_true",
        help="Skip sqlite-vec environment precheck before benchmark.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Replace slo-in file with generated slo-out when pipeline succeeds.",
    )
    args = parser.parse_args()
    if str(args.backend) == "champion":
        os.environ.setdefault("MEM_EMBED_PROVIDER", "disabled")
        os.environ["MEM_EMBED_DIM"] = str(int(args.dim))

    repo_root = Path(__file__).resolve().parent.parent
    if not bool(args.skip_precheck):
        if str(args.backend) == "sqlite_vec":
            pre_cmd = [
                sys.executable,
                str(repo_root / "scripts" / "check_sqlite_vec_env.py"),
                "--strict",
            ]
            print({"stage": "precheck", "backend": "sqlite_vec"})
            code = _run(pre_cmd, cwd=repo_root)
            if code != 0:
                raise SystemExit(code)
        elif str(args.backend) == "champion":
            pre_cmd = [
                sys.executable,
                str(repo_root / "scripts" / "check_champion_env.py"),
                "--strict",
            ]
            print({"stage": "precheck", "backend": "champion"})
            code = _run(pre_cmd, cwd=repo_root)
            if code != 0:
                raise SystemExit(code)

    bench_cmd = [
        sys.executable,
        str(repo_root / "scripts" / "bench_memory_recall.py"),
        "--backend",
        str(args.backend),
        "--n",
        str(args.n),
        "--modes",
        str(args.modes),
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
        str(args.bench_out),
        "--slo-file",
        str(args.slo_in),
    ]
    if bool(args.fail_on_slo):
        bench_cmd.append("--fail-on-slo")
    if bool(args.require_index_backend):
        bench_cmd.append("--require-index-backend")

    print({"stage": "benchmark", "backend": args.backend, "n": args.n})
    code = _run(bench_cmd, cwd=repo_root)
    if code != 0:
        raise SystemExit(code)

    vector_backend = str(args.vector_backend or "").strip()
    if not vector_backend:
        if str(args.backend) == "sqlite_vec":
            vector_backend = "sqlite_vec"
        elif str(args.backend) == "champion":
            vector_backend = "qdrant"
        else:
            vector_backend = "client_scan"

    reb_cmd = [
        sys.executable,
        str(repo_root / "scripts" / "rebaseline_memory_slo.py"),
        "--in",
        str(args.bench_out),
        "--out",
        str(args.slo_out),
        "--tiers",
        str(args.tiers),
        "--backend",
        str(args.backend),
        "--vector-backend",
        vector_backend,
        "--fail-on-empty",
    ]
    print({"stage": "rebaseline", "vector_backend": vector_backend, "tiers": args.tiers})
    code = _run(reb_cmd, cwd=repo_root)
    if code != 0:
        raise SystemExit(code)

    if bool(args.apply):
        src = Path(str(args.slo_out))
        dst = Path(str(args.slo_in))
        dst.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
        print({"stage": "apply", "from": str(src), "to": str(dst)})

    print({"status": "ok", "slo_out": str(args.slo_out)})


if __name__ == "__main__":
    main()
