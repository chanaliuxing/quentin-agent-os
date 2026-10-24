#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
from pathlib import Path

from quentin.blueprint.evidence_emitter import emit_blueprint_spec_v3_evidence


def main() -> int:
    p = argparse.ArgumentParser(description="Emit deterministic evidence for blueprint/spec_v3.json (offline).")
    p.add_argument("--repo-root", default=".", help="Repo root (default: .)")
    p.add_argument("--spec", default="blueprint/spec_v3.json", help="Spec path relative to repo root.")
    p.add_argument(
        "--kv-path",
        default=None,
        help="Override KVStore sqlite path (default: <repo_root>/data/kv_store.sqlite3).",
    )
    args = p.parse_args()

    res = emit_blueprint_spec_v3_evidence(
        repo_root=args.repo_root,
        spec_path=args.spec,
        kv_path=Path(args.kv_path).resolve() if args.kv_path else None,
    )
    print(json.dumps(res.to_dict(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

