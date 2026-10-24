#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import sys

from quentin.llm.client import call_llm


def main() -> int:
    p = argparse.ArgumentParser(description="Smoke test a real external LLM provider via quentin.llm.client.call_llm.")
    p.add_argument("--provider", default=os.getenv("LLM_PROVIDER", ""), help="Provider: openai|gemini|deepseek|openrouter|ollama")
    p.add_argument("--model", default=os.getenv("LLM_MODEL", ""), help="Model name/id (e.g. gpt-4o-mini, gemini-2.5-flash)")
    p.add_argument("--system", default="You are a helpful assistant.", help="System prompt")
    p.add_argument("--prompt", required=True, help="User prompt")
    args = p.parse_args()

    if not args.model:
        print("ERROR: missing --model (or env LLM_MODEL)", file=sys.stderr)
        return 2

    provider = args.provider.strip().lower() or None
    out = call_llm(
        args.model,
        user_prompt=args.prompt,
        system_prompt=args.system,
        provider=provider,
        environment=os.getenv("QUENTIN_ENV", "sandbox"),
        domain=os.getenv("QUENTIN_DOMAIN", "core"),
        risk_level=os.getenv("QUENTIN_RISK", "medium"),
    )
    sys.stdout.write(out if out.endswith("\n") else out + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

