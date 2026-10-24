from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path


def _run_one(cmd: list[str], *, cwd: Path, timeout_s: int) -> tuple[int, float, str, str]:
    t0 = time.perf_counter()
    try:
        proc = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True, timeout=max(1, int(timeout_s)))
        dt = time.perf_counter() - t0
        return int(proc.returncode), dt, str(proc.stdout or ""), str(proc.stderr or "")
    except subprocess.TimeoutExpired as e:
        dt = time.perf_counter() - t0
        return 124, dt, str(getattr(e, "stdout", "") or ""), str(getattr(e, "stderr", "") or "")


def main() -> None:
    p = argparse.ArgumentParser(description="Run memory intelligence benchmark across scale tiers.")
    p.add_argument("--backend", default="sqlite_vec", choices=["sqlite", "sqlite_vec"])
    p.add_argument("--n", default="10000,30000,100000")
    p.add_argument("--modes", default="hybrid")
    p.add_argument("--case-profile", default="mixed", choices=["basic", "mixed"])
    p.add_argument("--query-domain-policy", default="case", choices=["none", "case"])
    p.add_argument("--cases", type=int, default=40)
    p.add_argument("--runs", type=int, default=1)
    p.add_argument("--warmup", type=int, default=0)
    p.add_argument("--dim", type=int, default=768)
    p.add_argument("--top-k", type=int, default=10)
    p.add_argument("--db-dir", default="/tmp/memory_intelligence_scale")
    p.add_argument("--out-dir", default="/tmp/memory_intelligence_scale")
    p.add_argument("--slo-file", default="config/memory_intelligence_slo.json")
    p.add_argument("--timeout-s", type=int, default=1800)
    p.add_argument("--lock-file", default="/tmp/memory_intelligence_scale/.scale_matrix.lock")
    p.add_argument("--lock-timeout-s", type=int, default=0)
    p.add_argument("--require-index-backend", action="store_true")
    p.add_argument("--fail-fast", action="store_true")
    args = p.parse_args()

    repo_root = Path(__file__).resolve().parent.parent
    out_dir = Path(str(args.out_dir))
    out_dir.mkdir(parents=True, exist_ok=True)
    lock_path = Path(str(args.lock_file))
    lock_path.parent.mkdir(parents=True, exist_ok=True)

    ns = [int(x.strip()) for x in str(args.n).split(",") if x.strip()]
    summary: list[dict] = []

    lock_fd: int | None = None
    start_wait = time.time()
    while lock_fd is None:
        try:
            lock_fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
            os.write(lock_fd, str(os.getpid()).encode("utf-8"))
        except FileExistsError:
            waited = int(time.time() - start_wait)
            if waited >= max(0, int(args.lock_timeout_s)):
                print({"status": "lock_busy", "lock_file": str(lock_path), "waited_s": waited}, file=sys.stderr)
                raise SystemExit(9)
            time.sleep(1)

    try:
        for n in ns:
            out_file = out_dir / f"bench_n{n}.jsonl"
            cmd = [
                sys.executable,
                str(repo_root / "scripts" / "bench_memory_intelligence.py"),
                "--backend",
                str(args.backend),
                "--n",
                str(n),
                "--modes",
                str(args.modes),
                "--case-profile",
                str(args.case_profile),
                "--query-domain-policy",
                str(args.query_domain_policy),
                "--cases",
                str(args.cases),
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
                str(out_file),
                "--slo-file",
                str(args.slo_file),
                "--fail-on-slo",
            ]
            if bool(args.require_index_backend):
                cmd.append("--require-index-backend")

            print({"stage": "run", "n": int(n), "out": str(out_file)})
            rc, dt, out, err = _run_one(cmd, cwd=repo_root, timeout_s=int(args.timeout_s))
            row = {
                "n": int(n),
                "returncode": int(rc),
                "elapsed_s": round(float(dt), 3),
                "out_file": str(out_file),
            }
            summary.append(row)
            print({"stage": "done", **row})
            if out.strip():
                print(out.strip())
            if err.strip():
                print(err.strip(), file=sys.stderr)

            if bool(args.fail_fast) and rc != 0:
                break
    finally:
        try:
            if lock_fd is not None:
                os.close(lock_fd)
        except Exception:
            pass
        try:
            if lock_path.exists():
                lock_path.unlink()
        except Exception:
            pass

    summary_path = out_dir / "scale_summary.json"
    summary_path.write_text(json.dumps({"runs": summary}, ensure_ascii=False, indent=2), encoding="utf-8")
    print({"status": "ok", "summary": str(summary_path), "runs": summary})


if __name__ == "__main__":
    main()
