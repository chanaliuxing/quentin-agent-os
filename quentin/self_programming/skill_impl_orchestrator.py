from __future__ import annotations
from dataclasses import dataclass
from typing import List, Dict, Any, Optional
from pathlib import Path
import json
from datetime import datetime, timedelta

from quentin.self_programming.engine import SelfProgrammingEngine
from quentin.self_programming.schema import PatchProposal
from quentin.skills.registry import SkillRegistry
from quentin.skills.schema import SkillSpec, SkillStatus
from quentin.memory.fabric import MemoryFabric
from quentin.memory.models import MemoryQuery
from quentin.traces.core import JsonlTraceRecorder
from quentin.utils.time import now_utc, normalize_to_utc_iso


@dataclass
class SkillImplContext:
    skill: SkillSpec
    stub_code: str
    related_traces: List[Dict[str, Any]]
    related_memories: List[Dict[str, Any]]


def _load_skill_stub(skill: SkillSpec, repo_root: Path) -> Optional[str]:
    if not skill.impl_stub_path:
        return None
    path = repo_root / skill.impl_stub_path
    if not path.exists():
        return None
    return path.read_text(encoding="utf-8")


def _load_related_traces(skill: SkillSpec, repo_root: Path, days: int = 14, limit: int = 50) -> List[Dict[str, Any]]:
    trace_path = repo_root / "data" / "traces"
    if not trace_path.exists():
        return []

    since = now_utc() - timedelta(days=days)
    out: List[Dict[str, Any]] = []

    for trace_file in trace_path.glob("*.jsonl"):
        with trace_file.open("r", encoding="utf-8") as f:
            for line in f:
                try:
                    evt = json.loads(line)
                except json.JSONDecodeError:
                    continue

                if evt.get("event_type") != "TASK_SUCCESS":
                    continue
                
                payload = evt.get("payload", {})
                if payload.get("domain") != skill.domain:
                    continue

                ts_str = evt.get("timestamp")
                if not ts_str:
                    continue
                ts = datetime.fromisoformat(normalize_to_utc_iso(ts_str))
                if ts < since:
                    continue

                out.append(payload)
                if len(out) >= limit:
                    break
    return out


def _load_related_memories(skill: SkillSpec, memory_fabric: MemoryFabric, top_k: int = 10) -> List[Dict[str, Any]]:
    q = MemoryQuery(
        text=skill.name,
        top_k=top_k,
        min_importance=0.2,
        tags_any=[skill.domain],
    )
    recs = memory_fabric.recall(q)
    return [rec.to_dict() for rec in recs]


def build_skill_impl_context(skill: SkillSpec, repo_root: Path, memory_fabric: MemoryFabric) -> Optional[SkillImplContext]:
    stub_code = _load_skill_stub(skill, repo_root)
    if not stub_code:
        return None

    traces = _load_related_traces(skill, repo_root)
    memories = _load_related_memories(skill, memory_fabric)

    return SkillImplContext(
        skill=skill,
        stub_code=stub_code,
        related_traces=traces,
        related_memories=memories,
    )

def build_skill_impl_prompt(ctx: SkillImplContext) -> str:
    skill = ctx.skill
    examples_str = json.dumps([e.__dict__ for e in skill.examples], ensure_ascii=False, indent=2)
    traces_str = json.dumps(ctx.related_traces[:10], ensure_ascii=False, indent=2)
    memories_str = json.dumps(ctx.related_memories[:10], ensure_ascii=False, indent=2)

    prompt = f"""
You are a senior Python engineer inside a self-evolving meta-agent system.

Goal:
Implement the function `run_skill(params: Dict[str, Any])` for the following skill stub.
You must ONLY modify the stub file, keep its public signature, and write clean, robust code.

Skill spec:
- id: {skill.id}
- name: {skill.name}
- domain: {skill.domain}
- short_description: {skill.short_description}

Detailed description:
{skill.detailed_description}

Parameters schema (rough, not strict):
{json.dumps(skill.parameters, ensure_ascii=False, indent=2)}

Examples of usage:
{examples_str}

Related successful traces (recent):
{traces_str}

Related consolidated memories:
{memories_str}

Requirements:
1. Implement the core logic inside `run_skill`.
2. Add docstring and inline comments explaining key decisions.
3. Handle errors gracefully and return a structured dict.
4. DO NOT change the function signature.
5. DO NOT import heavy dependencies unless necessary.
6. Keep the implementation deterministic and testable.

You should produce a patch that:
- Only edits the stub file
- Replaces the `NotImplementedError` with a real implementation
- Adds any small helper functions inside the same file if needed.
"""
    return prompt

def generate_skill_impl_patch(
    engine: SelfProgrammingEngine,
    trace_recorder: JsonlTraceRecorder,
    ctx: SkillImplContext,
) -> Optional[PatchProposal]:
    prompt = build_skill_impl_prompt(ctx)

    from quentin.self_programming.schema import PatchTarget

    target = PatchTarget(
        kind="file",
        path=ctx.skill.impl_stub_path,
        symbol=None,
        constraints={},
    )
    
    result = engine.run_cycle(
        modules_to_improve=[target],
        context={
            "problem_description": prompt,
            "metrics": {},
            "notes": {
                "skill_id": ctx.skill.id,
                "skill_domain": ctx.skill.domain,
                "source": "skill_self_programming_cycle",
            }
        },
    )

    proposals = result.get("proposals")
    if proposals:
        return proposals[0]
    
    return None
