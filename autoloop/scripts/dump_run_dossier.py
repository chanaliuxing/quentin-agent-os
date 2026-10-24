#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.harness import AgentHarness


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workflow-id", required=True)
    parser.add_argument("--phase-id", default="phase_01")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    dossier = AgentHarness().build_dossier(workflow_id=args.workflow_id, phase_id=args.phase_id)
    out = ROOT_DIR / "runtime" / "reports" / f"run_{args.workflow_id}_{args.phase_id}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(dossier.to_markdown(), encoding="utf-8")
    print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
