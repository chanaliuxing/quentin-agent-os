#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
import os
import tempfile
from pathlib import Path

from quentin.l3.research.interface import ResearchInterfaceV3
from quentin.l3.research.eval_harness import EvalCase
from quentin.memory.fabric import MemoryFabric
from quentin.memory.models import MemoryQuery
from quentin.traces.core import JsonlTraceRecorder


def main() -> int:
    p = argparse.ArgumentParser(description="Run an offline L3->L2->L1 feedback loop for MemoryFabric defaults.")
    p.add_argument("--repo-root", default=".", help="Repo root (default: .)")
    p.add_argument("--kv-path", default="", help="KVStore sqlite path (default: temporary).")
    p.add_argument("--defaults-path", default="", help="Memory recall defaults json path (default: temporary).")
    args = p.parse_args()

    repo_root = Path(args.repo_root).resolve()
    with tempfile.TemporaryDirectory(prefix="quentin_mem_fb_") as d:
        tmp = Path(d).resolve()
        kv_path = Path(args.kv_path).expanduser().resolve() if str(args.kv_path).strip() else (tmp / "kv_store.sqlite3")
        defaults_path = (
            Path(args.defaults_path).expanduser().resolve()
            if str(args.defaults_path).strip()
            else (tmp / "memory_recall_config.json")
        )

        # Keep research state isolated and enable defaults for the L1 verification step.
        os.environ["QUENTIN_KVSTORE_PATH"] = str(kv_path)
        os.environ["QUENTIN_MEMORY_RECALL_DEFAULTS_ENABLE"] = "1"
        os.environ["QUENTIN_MEMORY_RECALL_DEFAULTS_PATH"] = str(defaults_path)

        ri = ResearchInterfaceV3(repo_root=str(repo_root))

        exp = ri.create_experiment(
            {
                "name": "MemoryRecallDefaults",
                "description": "Offline recall strategy A/B with deterministic embeddings.",
                "target_type": "memory_fabric",
                "metrics": ["success_rate", "avg_latency_ms"],
                "variants": [
                    {"variant_id": "vec_only", "name": "VectorOnly", "params": {"mode": "vector_only", "top_k": 5}},
                    {
                        "variant_id": "hybrid",
                        "name": "Hybrid",
                        "params": {"mode": "hybrid", "alpha": 0.2, "top_k": 5, "k_text": 5, "k_vec": 5},
                    },
                ],
            }
        )

        cases = [
            EvalCase(
                case_id="kw1",
                description="Find the exact error code token in memory.",
                input_payload={
                    "corpus": [f"noise_{i}" for i in range(40)]
                    + ["ERR_CODE_XYZ should be retrieved"]
                    + [f"more_noise_{i}" for i in range(40)],
                    "query": "ERR_CODE_XYZ",
                },
                expected_keywords=["ERR_CODE_XYZ"],
            ),
            EvalCase(
                case_id="kw2",
                description="Find the unique identifier quickly.",
                input_payload={
                    "corpus": [f"irrelevant_{i}" for i in range(60)] + ["ticket:ABC-123 is the one"] + [f"tail_{i}" for i in range(10)],
                    "query": "ABC-123",
                },
                expected_keywords=["ABC-123"],
            ),
        ]

        exp_id = str(exp.get("experiment_id") or "")
        if not exp_id:
            raise RuntimeError(f"missing experiment_id: {exp}")

        run = ri.run_experiment(exp_id, cases=[c.to_dict() for c in cases])
        results = run.get("variant_results") or {}

        decision = ri.decide_and_promote_variant(
            exp_id,
            promote_policy={
                "metric": "success_rate",
                "min_delta": 0.01,
                "apply": True,
                "human_approved": True,
                "rules_path": str(defaults_path),
            },
        )
        if not (decision.get("ok", True) is True and decision.get("applied", False) is True):
            raise RuntimeError(f"promotion failed: {decision}")
        if not defaults_path.exists():
            raise RuntimeError("promotion did not write memory recall defaults config")

        # L1 verification: mode=auto should use promoted defaults (requires ENABLE=1).
        trace_root = tmp / "trace_root"
        trace = JsonlTraceRecorder(repo_root=str(trace_root))

        class _ToyEmbed:
            def embed_text(self, text: str) -> list[float]:
                # Stable, deterministic embedding for offline tests.
                acc = 0
                for ch in str(text):
                    acc = (acc * 131 + ord(ch)) % 1000003
                base = (acc % 1000) / 1000.0
                return [base + (i * 0.001) for i in range(32)]

        fabric = MemoryFabric(
            repo_root=str(tmp),
            db_path=tmp / "memory.db",
            use_postgres=False,
            trace_recorder=trace,
            embedding_client=_ToyEmbed(),  # type: ignore[arg-type]
        )
        corpus = [f"noise_{i}" for i in range(40)] + ["ERR_CODE_XYZ should be retrieved"] + [f"more_noise_{i}" for i in range(40)]
        for t in corpus:
            fabric.remember_atomic(content=str(t), source="fb_loop", metadata={"tag": "corpus"})

        recs = fabric.recall(MemoryQuery(text="ERR_CODE_XYZ", top_k=5, mode="auto", debug=False))
        if not recs:
            raise RuntimeError("L1 verification recall returned no records")

        events_path = trace_root / "data" / "traces" / "events.jsonl"
        if not events_path.exists():
            raise RuntimeError("L1 verification trace events.jsonl missing")
        last = ""
        with events_path.open("r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    last = line
        ev = json.loads(last) if last else {}
        payload = ev.get("payload") if isinstance(ev, dict) else {}
        effective_mode = (payload or {}).get("mode")
        if effective_mode != "hybrid":
            raise RuntimeError(f"expected promoted effective mode=hybrid, got {effective_mode!r} payload={payload!r}")

        print("OK: full L3->L2->L1 memory recall feedback loop completed.")
        print("experiment_id:", exp_id)
        print("variant_results:", results)
        print("decision:", decision)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
