#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.config import settings
from app.metrics import (
    filter_variant_rows,
    load_execution_summaries,
    summarize_variant,
    to_markdown,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--variant-a", required=True)
    parser.add_argument("--variant-b", required=True)
    parser.add_argument("--match-mode", choices=["prefix", "contains", "exact"], default="prefix")
    parser.add_argument("--window-size", type=int, default=100)
    parser.add_argument("--only-subprocess", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    rows = load_execution_summaries(settings.runtime_dir / "evidence")
    rows_a = filter_variant_rows(rows=rows, variant_tag=args.variant_a, match_mode=args.match_mode, window_size=args.window_size)
    rows_b = filter_variant_rows(rows=rows, variant_tag=args.variant_b, match_mode=args.match_mode, window_size=args.window_size)
    summary_a = summarize_variant(name=args.variant_a, rows=rows_a)
    summary_b = summarize_variant(name=args.variant_b, rows=rows_b)

    report = {
        "generated_at": datetime.now().isoformat(),
        "variant_a": {
            "name": summary_a.name,
            "total_runs": summary_a.total_runs,
            "acceptance_pass_rate": summary_a.acceptance_pass_rate,
            "terminal_distribution": summary_a.terminal_distribution,
            "primary_failure_distribution": summary_a.primary_failure_distribution,
            "top_primary_failures": summary_a.top_primary_failures,
            "subprocess_nonzero_exit_count": summary_a.subprocess_nonzero_exit_count,
            "subprocess_nonzero_exit_stage_distribution": summary_a.subprocess_nonzero_exit_stage_distribution,
            "subprocess_nonzero_exit_owner_distribution": summary_a.subprocess_nonzero_exit_owner_distribution,
            "subprocess_nonzero_exit_action_distribution": summary_a.subprocess_nonzero_exit_action_distribution,
        },
        "variant_b": {
            "name": summary_b.name,
            "total_runs": summary_b.total_runs,
            "acceptance_pass_rate": summary_b.acceptance_pass_rate,
            "terminal_distribution": summary_b.terminal_distribution,
            "primary_failure_distribution": summary_b.primary_failure_distribution,
            "top_primary_failures": summary_b.top_primary_failures,
            "subprocess_nonzero_exit_count": summary_b.subprocess_nonzero_exit_count,
            "subprocess_nonzero_exit_stage_distribution": summary_b.subprocess_nonzero_exit_stage_distribution,
            "subprocess_nonzero_exit_owner_distribution": summary_b.subprocess_nonzero_exit_owner_distribution,
            "subprocess_nonzero_exit_action_distribution": summary_b.subprocess_nonzero_exit_action_distribution,
        },
        "delta": {
            "pass_rate_delta": round(summary_b.acceptance_pass_rate - summary_a.acceptance_pass_rate, 4),
            "sample_size_delta": summary_b.total_runs - summary_a.total_runs,
            "subprocess_nonzero_exit_count_delta": (
                summary_b.subprocess_nonzero_exit_count - summary_a.subprocess_nonzero_exit_count
            ),
        },
    }

    slug_a = _slug(args.variant_a)
    slug_b = _slug(args.variant_b)
    json_out = settings.runtime_dir / "metrics" / f"variant_compare_{slug_a}_vs_{slug_b}.json"
    md_out = settings.runtime_dir / "reports" / f"compare_{slug_a}_vs_{slug_b}.md"
    json_out.parent.mkdir(parents=True, exist_ok=True)
    md_out.parent.mkdir(parents=True, exist_ok=True)
    json_out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    if args.only_subprocess:
        md_out.write_text(to_subprocess_markdown(slice_a=summary_a, slice_b=summary_b), encoding="utf-8")
    else:
        md_out.write_text(to_markdown(slice_a=summary_a, slice_b=summary_b), encoding="utf-8")
    print(json_out)
    print(md_out)
    return 0


def _slug(value: str) -> str:
    return "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in value).strip("_")[:48] or "variant"


def to_subprocess_markdown(*, slice_a, slice_b) -> str:
    delta = slice_b.subprocess_nonzero_exit_count - slice_a.subprocess_nonzero_exit_count
    lines = [
        f"# Subprocess Compare: `{slice_a.name}` vs `{slice_b.name}`",
        "",
        "## Summary",
        f"- `{slice_a.name}` subprocess_nonzero_exit_count: `{slice_a.subprocess_nonzero_exit_count}`",
        f"- `{slice_b.name}` subprocess_nonzero_exit_count: `{slice_b.subprocess_nonzero_exit_count}`",
        f"- delta (`{slice_b.name}` - `{slice_a.name}`): `{delta}`",
        "",
        "## Stage Distribution",
        f"- `{slice_a.name}`: `{slice_a.subprocess_nonzero_exit_stage_distribution}`",
        f"- `{slice_b.name}`: `{slice_b.subprocess_nonzero_exit_stage_distribution}`",
        "",
        "## Owner Distribution",
        f"- `{slice_a.name}`: `{slice_a.subprocess_nonzero_exit_owner_distribution}`",
        f"- `{slice_b.name}`: `{slice_b.subprocess_nonzero_exit_owner_distribution}`",
        "",
        "## Action Distribution",
        f"- `{slice_a.name}`: `{slice_a.subprocess_nonzero_exit_action_distribution}`",
        f"- `{slice_b.name}`: `{slice_b.subprocess_nonzero_exit_action_distribution}`",
    ]
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    raise SystemExit(main())
