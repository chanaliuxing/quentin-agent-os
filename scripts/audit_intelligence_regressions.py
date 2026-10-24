#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

# Allow direct script execution without requiring editable install.
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from quentin.diagnostics.intelligence_auditor import build_intelligence_audit


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit Quentin intelligence regressions from trace/audit logs.")
    parser.add_argument("--repo-root", default=".", help="Repository root path.")
    parser.add_argument("--limit", type=int, default=20000, help="Tail rows to scan from jsonl files.")
    parser.add_argument("--out", default="", help="Optional output JSON file.")
    args = parser.parse_args()

    report = build_intelligence_audit(repo_root=args.repo_root, limit=max(100, int(args.limit)))
    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.out:
        out = Path(args.out)
        if not out.is_absolute():
            out = (Path(args.repo_root).resolve() / out).resolve()
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
