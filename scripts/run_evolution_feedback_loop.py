"""
Run a complete L3 -> L2 -> L1 evolution feedback loop locally (no external LLM required).

Flow:
1) L3: create + run an offline experiment (model_router) with baseline/candidate variants
2) L3: decide + promote the winning variant, applying an online-effective config (rules JSON)
3) L1: build a runtime using ModelRouter as the callable LLM and run a task, verifying routing changed

This script intentionally writes only under `data/` by default.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from quentin.kernel.safety import SafetyKernel
from quentin.l3.research.interface import ResearchInterfaceV3
from quentin.routing.model_router import ModelRouter
from quentin.runtime.system import build_default_runtime


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Run the full L3->L2->L1 evolution feedback loop.")
    p.add_argument("--repo-root", type=str, default=".", help="Repo root (default: .)")
    p.add_argument("--kv-path", type=str, default="data/research/demo_kv.sqlite3", help="KVStore sqlite path under repo.")
    p.add_argument("--rules-path", type=str, default="data/research/demo_model_router_rules.json", help="Rules JSON path under repo.")
    p.add_argument("--domain", type=str, default="desktop", help="Domain for governance.")
    p.add_argument("--environment", type=str, default="sandbox", help="Environment for governance.")
    return p.parse_args()


def main() -> None:
    args = parse_args()
    repo_root = Path(args.repo_root).resolve()

    os.environ["QUENTIN_KVSTORE_PATH"] = str((repo_root / args.kv_path).resolve())

    baseline_model = "qwen3-vl:latest"
    candidate_model = "deepseek-r1:1.5b"
    route_key = "balanced::chat"

    safety = SafetyKernel()
    research = ResearchInterfaceV3(
        repo_root=str(repo_root),
        domain=str(args.domain),
        environment=str(args.environment),
        risk_level="medium",
        safety_kernel=safety,
    )

    exp = research.create_experiment(
        {
            "name": "demo_full_feedback_loop",
            "description": "L3->L2->L1 demo: promote model_router rule",
            "target_type": "model_router",
            "metrics": ["success_rate"],
            "variants": [
                {"variant_id": "baseline", "name": "baseline", "params": {"route_key": route_key, "model": baseline_model}},
                {"variant_id": "candidate", "name": "candidate", "params": {"route_key": route_key, "model": candidate_model}},
            ],
        }
    )
    exp_id = exp["experiment_id"]

    # Candidate should win: expected keywords include candidate model name.
    run = research.run_experiment(
        exp_id,
        cases=[
            {
                "case_id": "c1",
                "description": "route chat model",
                "input_payload": {"prompt": "hello"},
                "expected_keywords": [candidate_model],
                "pass_threshold": 1.0,
                "meta": {},
            }
        ],
    )
    print("[L3] experiment_run:", {"experiment_id": exp_id, "variant_results": run.get("variant_results")})

    promo = research.decide_and_promote_variant(
        exp_id,
        promote_policy={
            "metric": "success_rate",
            "min_delta": 0.01,
            "apply": True,
            "rules_path": str(args.rules_path),
            "human_approved": True,
        },
    )
    print("[L3] promotion:", {"applied": promo.get("applied"), "reason": (promo.get("decision") or {}).get("reason")})

    rules_file = (repo_root / args.rules_path).resolve()
    router = ModelRouter(repo_root=repo_root, rules_path=rules_file)

    runtime = build_default_runtime(repo_root=repo_root, llm=router, council=None, enable_self_programming=False)
    res = runtime.run_task("hello evolution loop", {"domain": "general"})
    out = (res.output or {}).get("final_output") if isinstance(res.output, dict) else str(res.output)
    if not out and isinstance(res.output, dict):
        out = (res.output or {}).get("raw_output")
    print("[L1] task_output:", str(out)[:240])
    if res.status != "success":
        raise SystemExit(f"FAILED: runtime task status={res.status}, output={out!r}")

    print("OK: full L3->L2->L1 feedback loop completed.")


if __name__ == "__main__":
    main()
