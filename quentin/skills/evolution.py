from __future__ import annotations
from typing import List, Dict, Any
from pathlib import Path
from datetime import datetime, timedelta
import json
import textwrap

from quentin.traces.core import JsonlTraceRecorder, TraceEventType, new_trace_event
from quentin.skills.registry import SkillRegistry
from quentin.skills.schema import SkillSpec, SkillStatus
from quentin.memory.fabric import MemoryFabric
from quentin.memory.models import MemoryQuery, MemoryTier
from quentin.llm.ollama_client import OllamaLLMClient
from dataclasses import dataclass
from quentin.utils.time import now_utc, normalize_to_utc_iso

@dataclass
class SkillEvolutionStats:
    patterns_mined: int
    candidates_generated: int
    experiments_created: int
    candidates_accepted: int
    candidates_rejected: int


class SkillEvolutionLoop:
    """
    Skill Evolution v1:
    1) 从 trace 中抽一批成功案例
    2) 调 council 生成 skill JSON
    3) 生成 SkillSpec + stub 文件
    4) 注册到 SkillRegistry（状态为 DRAFT）
    """
    def __init__(
        self,
        trace_recorder: JsonlTraceRecorder,
        skill_registry: SkillRegistry,
        memory_fabric: MemoryFabric,
        council: Any,
        repo_root: Path,
    ):
        self.trace_recorder = trace_recorder
        self.skill_registry = skill_registry
        self.memory_fabric = memory_fabric
        self.council = council
        self.repo_root = repo_root
        self.skills_dir = self.repo_root / "quentin" / "skills" / "generated"
        self.skills_dir.mkdir(parents=True, exist_ok=True)
    
    def _load_success_traces(
        self,
        domain: str,
        limit: int = 50,
        days: int = 7,
    ) -> List[Dict[str, Any]]:
        """
        v1: 简单从某个 trace 文件中筛选成功任务。
        """
        path = self.repo_root / "data" / "traces"
        if not path.exists():
            return []

        since = now_utc() - timedelta(days=days)
        results: List[Dict[str, Any]] = []

        for trace_file in path.glob("*.jsonl"):
             with trace_file.open("r", encoding="utf-8") as f:
                for line in f:
                    try:
                        evt = json.loads(line)
                    except json.JSONDecodeError:
                        continue

                    if evt.get("event_type") != "TASK_SUCCESS": # Assuming this event type
                        continue
                    
                    payload = evt.get("payload", {})
                    if payload.get("domain") != domain:
                        continue

                    ts_str = evt.get("timestamp")
                    if not ts_str:
                        continue
                    ts = datetime.fromisoformat(normalize_to_utc_iso(ts_str))
                    if ts < since:
                        continue

                    results.append(payload)
                    if len(results) >= limit:
                        break
        return results

    def _call_council_for_skill(self, domain: str, examples: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        调用 council，用一批成功案例生成技能 JSON。
        """
        if not hasattr(self.council, "propose_skill_from_examples"):
             # Fallback for simple LLM clients
             if isinstance(self.council, OllamaLLMClient):
                 example_str = json.dumps(examples, indent=2)
                 prompt = f"From the following successful task examples in domain '{domain}', extract ONE reusable skill. Return a JSON object with fields: {{name, short_description, detailed_description, tags, parameters, examples, notes}}.\n\n{example_str}"
                 raw_resp = self.council.complete(prompt)
                 try:
                     return json.loads(raw_resp)
                 except json.JSONDecodeError:
                     return {"name": "failed_to_parse_skill"}
             else:
                return {"name": "council_has_no_propose_skill_method"}

        payload = {
            "role": "skill_evolution",
            "instruction": (
                "You are a meta-agent skill designer. From the following successful task examples, "
                "extract ONE reusable, general-purpose skill. It should be something that can be "
                "called as a function/tool by a planner.\n\n"
                "Return STRICTLY a JSON object with fields: "
                "{name, domain, short_description, detailed_description, tags, parameters, examples, notes}."
            ),
            "domain": domain,
            "examples": examples,
        }
        resp = self.council.propose_skill_from_examples(payload)
        return resp

    def _create_impl_stub(self, skill: SkillSpec) -> str:
        """
        为新的 skill 生成一个 Python stub 文件，用于未来真正实现逻辑。
        """
        snake_name = skill.name.lower().replace(" ", "_")
        file_path = self.skills_dir / f"{snake_name}_{skill.id[:8]}.py"

        doc = textwrap.indent(textwrap.fill(skill.detailed_description, width=80), "    ")

        content = f'''"""
AUTO-GENERATED SKILL STUB

Skill Name: {skill.name}
Domain    : {skill.domain}
Status    : {skill.status.value}
Generated : {skill.created_at.isoformat()}

SHORT:
    {skill.short_description}

DETAIL:
{doc}

Notes:
    This stub was generated by skill_evolution_loop. Fill in the implementation
    in `run_skill(...)` and add proper unit tests.

"""

from typing import Any, Dict


def run_skill(params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Expected params schema (rough):
    {json.dumps(skill.parameters, indent=4)}

    Returns:
        A dict with the result. You can refine this contract later.
    """
    # Default behavior for generated stubs: return a structured "not implemented" result
    # so the runtime can handle it without crashing.
    return {
        "ok": False,
        "status": "not_implemented",
        "skill_id": "{skill.id}",
        "skill_name": "{skill.name}",
        "message": "Generated skill stub has no concrete implementation yet.",
        "params": params,
    }
'''

        file_path.write_text(content, encoding="utf-8")
        return str(file_path)

    def run_once(self, domain: str, max_examples: int = 30) -> SkillSpec | None:
        """
        Skill Evolution v1:
        1) 从 trace 中抽一批成功案例
        2) 调 council 生成 skill JSON
        3) 生成 SkillSpec + stub 文件
        4) 注册到 SkillRegistry（状态为 DRAFT）
        """
        success_examples = self._load_success_traces(domain=domain, limit=max_examples)
        if not success_examples:
            self.trace_recorder.record_event(
                new_trace_event(
                    trace_id="skill-evolution",
                    event_type=TraceEventType.SKILL_EVOLUTION,
                    payload={"domain": domain, "status": "no_examples"},
                )
            )
            return None

        council_json = self._call_council_for_skill(domain, success_examples)
        if "name" not in council_json:
            return None
        
        council_json.setdefault("domain", domain)
        council_json.setdefault("source_trace_ids", [e.get("trace_id") for e in success_examples if e.get("trace_id")])

        skill_spec = SkillSpec.new_from_council_json(council_json)

        impl_path = self._create_impl_stub(skill_spec)
        skill_spec.impl_stub_path = impl_path

        self.skill_registry.register(skill_spec)

        self.trace_recorder.record_event(
            new_trace_event(
                trace_id="skill-evolution",
                event_type=TraceEventType.SKILL_EVOLUTION,
                payload={
                    "status": "created",
                    "domain": domain,
                    "skill_id": skill_spec.id,
                    "skill_name": skill_spec.name,
                    "impl_stub_path": impl_path,
                },
            )
        )

        return skill_spec
