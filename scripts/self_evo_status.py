#!/usr/bin/env python
# scripts/self_evo_status.py
from __future__ import annotations
import argparse
import json

from meta_agent.observability.service import ObservabilityService
from meta_agent.observability.snapshot import SystemSnapshot

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Meta-Agent Self-Evolution Status")
    p.add_argument("--json", action="store_true", help="Output the full snapshot in JSON format.")
    return p.parse_args()

def print_snapshot(snapshot: SystemSnapshot) -> None:
    def print_hline(): print("-" * 80)
    
    print_hline()
    print("LOOPS STATUS")
    print_hline()
    print(f"{ 'Loop':<15} {'Runs Today':<12} {'Last Run At':<26} {'Next Earliest':<26}")
    for ls in snapshot.loops:
        print(f"{ls.name:<15} {ls.runs_today:<12} {(ls.last_run_at or '-'):<26} {(ls.next_earliest_run_at or '-'):<26}")

    print_hline()
    print("PATCHES STATUS")
    print_hline()
    p = snapshot.patches
    print(f"Total: {p.total_patches}, Applied: {p.applied_patches}, Rejected: {p.rejected_patches}, Pending: {p.pending_patches}")
    print(f"Last 24h -> New: {p.last_24h_new}, Applied: {p.last_24h_applied}, Rejected: {p.last_24h_rejected}")

    print_hline()
    print("SKILLS STATUS")
    print_hline()
    s = snapshot.skills
    print(f"Total: {s.total_skills}, By Status: {s.by_status}")
    print(f"Avg Success Rate: {s.avg_success_rate:.3f} (Active Avg: {s.active_avg_success_rate:.3f})")
    print("\nTop Recent Skills:")
    print(f"{ 'ID':<12} {'Name':<25} {'Status':<10} {'Success':<8} {'Usage':<6}")
    for ks in s.top_recent_skills:
        print(f"{ks.get('id', '')[:12]:<12} {ks.get('name', '')[:25]:<25} {ks.get('status', ''):<10} {ks.get('success_rate', 0.0):<8.2f} {ks.get('usage_count', 0):<6}")

    print_hline()
    print("BLUEPRINT GAPS STATUS")
    print_hline()
    g = snapshot.gaps
    print(f"Total: {g.total_gaps}, Open: {g.open_gaps}, Closed: {g.closed_gaps}")
    print(f"Avg Clarity: {g.avg_clarity}, Avg Alignment: {g.avg_alignment}, Low Quality: {g.low_quality_count}")

    print_hline()
    print("RESEARCH STATUS")
    print_hline()
    r = snapshot.research
    print(f"Total Calls: {r.total_research_calls}, Last 24h: {r.last_24h_research_calls}")
    print(f"By Source: {r.by_source}")
    print(f"Last Research At: {r.last_research_at}")

    print_hline()
    print("BLUEPRINT VERSION STATUS")
    print_hline()
    b = snapshot.blueprint
    print(f"Total Versions: {b.total_versions}, Last 7d: {b.last_7d_versions}")
    print(f"By Risk Level: {b.by_risk_level}")
    print(f"Last Version ID: {b.last_version_id}")
    print(f"Last Version At: {b.last_version_at}")
    print(f"Last Summary: {b.last_version_summary}")

    print_hline()
    print("BLUEPRINT EFFECTS")
    print_hline()
    be = snapshot.blueprint_effects
    print(f"Analyzed versions: {be.total_analyzed}")
    print(f"Beneficial / Neutral: {be.beneficial} / {be.neutral}")
    print(f"Harmful / Unknown: {be.harmful} / {be.unknown}")
    print(f"Last beneficial version: {be.last_beneficial_version_id} @ {be.last_beneficial_at}")
    print(f"Last harmful version: {be.last_harmful_version_id} @ {be.last_harmful_at}")
    print_hline()

def main() -> None:
    args = parse_args()
    service = ObservabilityService()
    snapshot = service.build_snapshot()

    if args.json:
        print(json.dumps(snapshot.to_dict(), indent=2))
    else:
        print_snapshot(snapshot)

if __name__ == "__main__":
    main()
