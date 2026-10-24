#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path

from quentin.llm.client import call_llm


def _now_ms() -> int:
    return int(time.time() * 1000)


def main() -> int:
    p = argparse.ArgumentParser(description="Benchmark real external LLM chat latency/tokens (opt-in).")
    p.add_argument("--provider", default=os.getenv("LLM_PROVIDER", ""), help="openai|gemini|deepseek|openrouter|ollama")
    p.add_argument("--model", default=os.getenv("LLM_MODEL", ""), help="model id")
    p.add_argument("--n", type=int, default=5, help="number of calls")
    p.add_argument("--prompt", default="Say 'pong' only.", help="user prompt")
    p.add_argument("--system", default="You are a helpful assistant.", help="system prompt")
    p.add_argument("--out", default="data/bench/real_llm_chat.jsonl", help="output jsonl path (default under data/)")
    args = p.parse_args()

    if not args.model:
        raise SystemExit("missing --model (or env LLM_MODEL)")

    out_path = Path(args.out).expanduser()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    provider = args.provider.strip().lower() or None
    rows = 0
    started_ms = _now_ms()
    for i in range(int(args.n)):
        t0 = time.perf_counter()
        text = call_llm(
            args.model,
            user_prompt=args.prompt,
            system_prompt=args.system,
            provider=provider,
            model_name=args.model,
            actor="bench_real_llm_chat",
            domain=os.getenv("QUENTIN_DOMAIN", "core"),
            environment=os.getenv("QUENTIN_ENV", "sandbox"),
            risk_level=os.getenv("QUENTIN_RISK", "medium"),
            action_metadata={"bench": True, "bench_iter": i},
        )
        dt_ms = int((time.perf_counter() - t0) * 1000)
        rec = {
            "ts_ms": _now_ms(),
            "provider": provider or "auto",
            "model": args.model,
            "iter": i,
            "latency_ms": dt_ms,
            "output_chars": len(text or ""),
        }
        with out_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        rows += 1

    total_ms = _now_ms() - started_ms
    print(json.dumps({"calls": rows, "total_ms": total_ms, "out": str(out_path)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

