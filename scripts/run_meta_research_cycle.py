#!/usr/bin/env python
# scripts/run_meta_research_cycle.py
from __future__ import annotations
import json
import os

from meta_agent.observability.service import ObservabilityService
from meta_agent.evolution.schedule_config import SelfEvolutionScheduleConfig
from meta_agent.evolution.schedule_state import SelfEvolutionStateStore
from meta_agent.skills.registry import SkillRegistry
from meta_agent.research.meta_planner import MetaResearchAgent
from meta_agent.research.api import ResearchAPI

def main() -> None:
    print("Initializing Meta-Research cycle...")
    
    # Dependencies
    observability = ObservabilityService(
        sched_config=SelfEvolutionScheduleConfig(),
        state_store=SelfEvolutionStateStore(),
        skill_registry=SkillRegistry()
    )
    research_api = ResearchAPI()
    
    # The Agent
    agent = MetaResearchAgent(
        observability=observability,
        research_api=research_api,
    )

    plan = agent.run_cycle()

    print("\n=== Meta-Research Plan Summary ===")
    print(plan.summary)
    print("\n=== Tasks ===")
    for t in plan.tasks:
        print(f"- [{t.priority.upper()}] {t.id} :: {t.title} ({t.focus_area})")
        print(f"  Rationale: {t.rationale}")
        for a in t.actions:
            print(f"    * {a.kind}: {a.description} | target={a.target}")
        print()

    # Save the plan to a file
    path = "data/self_evo/meta_plans/last_plan.json"
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        # A simple way to serialize nested dataclasses
        plan_dict = {
            "generated_at": plan.generated_at,
            "summary": plan.summary,
            "tasks": [task.__dict__ for task in plan.tasks],
        }
        json.dump(plan_dict, f, ensure_ascii=False, indent=2)
    print(f"\nPlan saved to {path}")

if __name__ == "__main__":
    main()
