#!/usr/bin/env python
# scripts/blueprint_changelog.py
from __future__ import annotations
import argparse
import datetime as dt
import json

from meta_agent.blueprint.version_store import BlueprintVersionStore
from meta_agent.blueprint.impact_analyzer import BlueprintImpactAnalyzer
from meta_agent.llm.cli_clients import make_codex_cli_client

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Generate blueprint changelog using LLM")
    p.add_argument("--versions", type=int, default=10, help="Number of recent versions to include.")
    p.add_argument("--window-hours", type=int, default=24, help="Impact analysis window in hours.")
    return p.parse_args()

def main() -> None:
    args = parse_args()
    store = BlueprintVersionStore("data/blueprint/versions")
    versions = store.list_versions(limit=args.versions)
    analyzer = BlueprintImpactAnalyzer(window_hours=args.window_hours)
    report = analyzer.build_report(limit_versions=args.versions)
    impact_by_vid = {item.version_id: item for item in report.items}

    changes = []
    for v in versions:
        change = v.__dict__
        if (impact := impact_by_vid.get(v.version_id)):
            change["impact"] = impact.__dict__
        changes.append(change)

    context = {"generated_at": dt.datetime.utcnow().isoformat(), "changes": changes}
    
    llm = make_codex_cli_client()
    prompt = f"""
You are a technical writer for an AI project. Generate a changelog in Chinese based on the following JSON data,
which contains recent blueprint versions and their impact analysis.

{json.dumps(context, indent=2, ensure_ascii=False)}

The changelog should be human-readable, summarizing key changes, their effects (beneficial, harmful, neutral),
and any high-risk modifications. Structure it with sections like "Overview", "Key Changes", and "Impact Summary".
"""
    
    changelog = llm.generate(
        system="You write clear, concise changelogs in Chinese from structured data.",
        user=prompt,
    )
    print("=== Blueprint Changelog ===")
    print(changelog)

if __name__ == "__main__":
    main()
