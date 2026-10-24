from __future__ import annotations

import argparse
import gzip
import json
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, DefaultDict, Dict, List, Optional, Tuple


@dataclass
class PlanStat:
    attempts: int = 0
    skill_suggestions: int = 0
    tool_knowledge: int = 0
    tool_summaries: int = 0
    used_skills_total: int = 0


def _iter_jsonl_gz(path: Path) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    if not path.exists():
        return out
    with gzip.open(path, "rt", encoding="utf-8", errors="ignore") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except Exception:
                continue
            if isinstance(obj, dict):
                out.append(obj)
    return out


def _safe_int(x: Any) -> int:
    try:
        return int(x or 0)
    except Exception:
        return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Offline backflow/learning metrics report (from traces).")
    ap.add_argument("--repo-root", default=".", help="Repo root (default: .)")
    ap.add_argument("--events", default="data/traces/events.jsonl.gz", help="Events jsonl.gz path (relative to repo-root)")
    args = ap.parse_args()

    repo_root = Path(args.repo_root).resolve()
    events_path = (repo_root / args.events).resolve()

    events = _iter_jsonl_gz(events_path)
    if not events:
        print(f"No events found at {events_path}")
        return 2

    per_trace: DefaultDict[str, PlanStat] = defaultdict(PlanStat)

    for ev in events:
        trace_id = str(ev.get("trace_id") or "")
        if not trace_id:
            continue
        et = str(ev.get("event_type") or "")
        payload = ev.get("payload") if isinstance(ev.get("payload"), dict) else {}

        if et == "planning":
            st = per_trace[trace_id]
            st.attempts += 1
            ctx = payload.get("context_injected") if isinstance(payload.get("context_injected"), dict) else {}
            st.skill_suggestions += _safe_int(ctx.get("skill_suggestions_count"))
            st.tool_knowledge += _safe_int(ctx.get("tool_knowledge_count"))
            st.tool_summaries += _safe_int(ctx.get("tool_summaries_count"))
            used_skills = payload.get("used_skills")
            if isinstance(used_skills, list):
                st.used_skills_total += len([x for x in used_skills if x])

    traces = len(per_trace)
    total_attempts = sum(s.attempts for s in per_trace.values())
    if total_attempts <= 0:
        print("No planning events found.")
        return 2

    def avg(num: int) -> float:
        return float(num) / float(total_attempts) if total_attempts else 0.0

    print("Learning Backflow Report")
    print(f"- traces: {traces}")
    print(f"- planning_attempts: {total_attempts}")
    print(f"- avg_skill_suggestions_per_attempt: {avg(sum(s.skill_suggestions for s in per_trace.values())):.2f}")
    print(f"- avg_tool_knowledge_items_per_attempt: {avg(sum(s.tool_knowledge for s in per_trace.values())):.2f}")
    print(f"- avg_tool_summaries_count_per_attempt: {avg(sum(s.tool_summaries for s in per_trace.values())):.2f}")
    print(f"- avg_used_skills_per_attempt: {avg(sum(s.used_skills_total for s in per_trace.values())):.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

