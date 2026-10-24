from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
import uuid
import json
import logging
import os

from quentin.llm.ollama_client import OllamaLLMClient

logger = logging.getLogger(__name__)
from quentin.skills.registry import SkillRegistry
from quentin.planning.memory_helpers import recall_for_task
from quentin.skills.schema import SkillStatus
from quentin.utils.hash import get_goal_fingerprint


@dataclass
class PlanStep:
    """
    一个计划步骤，可以是分层的。
    """
    step_id: str
    description: str
    kind: str              # "skill" / "tool" / "llm_call" / "sub_plan"
    name: str              # skill 名称 / tool 名称
    args: Dict[str, Any]
    sub_steps: List['PlanStep'] = field(default_factory=list)
    depends_on: List[str] = field(default_factory=list)
    rollback_point: Optional[str] = None
    estimated_cost_tokens: int = 0
    fingerprint: Optional[str] = None
    target_file: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "step_id": self.step_id,
            "description": self.description,
            "kind": self.kind,
            "name": self.name,
            "args": self.args,
            "sub_steps": [s.to_dict() for s in self.sub_steps],
            "depends_on": list(self.depends_on or []),
            "rollback_point": self.rollback_point,
            "estimated_cost_tokens": int(self.estimated_cost_tokens or 0),
            "fingerprint": self.fingerprint,
            "target_file": self.target_file,
        }

@dataclass
class PlanMilestone:
    milestone_id: str
    title: str
    steps: List[PlanStep] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "milestone_id": self.milestone_id,
            "title": self.title,
            "steps": [s.to_dict() for s in self.steps],
        }


@dataclass
class Plan:
    plan_id: str
    goal: str
    milestones: List[PlanMilestone] = field(default_factory=list)
    steps: List[PlanStep] = field(default_factory=list)  # flattened / back-compat
    success_criteria: List[str] = field(default_factory=list)
    hard_constraints: List[str] = field(default_factory=list)
    estimated_total_cost_tokens: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "goal": self.goal,
            "milestones": [m.to_dict() for m in self.milestones],
            "steps": [s.to_dict() for s in self.steps],
            "success_criteria": list(self.success_criteria or []),
            "hard_constraints": list(self.hard_constraints or []),
            "estimated_total_cost_tokens": int(self.estimated_total_cost_tokens or 0),
        }


class HierarchicalPlanner:
    """
    v2 Hierarchical Planner：

    - 接收一个高层目标
    - 使用 LLM 将其分解为多步、分层的计划
    - 可以递归地对复杂步骤进行进一步分解
    - 会使用 MemoryFabric 和 SkillRegistry 来增强规划能力
    """

    def __init__(self, llm: OllamaLLMClient, skill_registry: SkillRegistry, max_depth: int = 2):
        self.llm = llm
        self.skill_registry = skill_registry
        self.max_depth = max_depth

    async def plan(
        self,
        goal: str,
        context: Dict[str, Any],
        *,
        current_depth: int = 0,
        success_criteria: Optional[List[str]] = None,
        hard_constraints: Optional[List[str]] = None,
        project_goal: Optional[str] = None,
    ) -> Plan:
        plan_id = "plan_" + uuid.uuid4().hex
        
        if current_depth >= self.max_depth:
            # Base case for recursion
            step = PlanStep(
                step_id="step_" + uuid.uuid4().hex[:8],
                description=goal,
                kind="llm_call",
                name="direct_model_call",
                args={"goal": goal, "context": context},
                fingerprint=get_goal_fingerprint(goal, context),
            )
            return Plan(
                plan_id=plan_id,
                goal=goal,
                milestones=[PlanMilestone(milestone_id="m1", title="Execute", steps=[step])],
                steps=[step],
                success_criteria=list(success_criteria or []),
                hard_constraints=list(hard_constraints or []),
                estimated_total_cost_tokens=int(step.estimated_cost_tokens or 0),
            )

        prompt = self._build_planning_prompt(
            goal,
            context,
            success_criteria=list(success_criteria or []),
            hard_constraints=list(hard_constraints or []),
            project_goal=project_goal,
        )
        
        try:
            raw_response = self.llm.complete(prompt)
            if hasattr(raw_response, "__await__"):
                raw_response = await raw_response  # type: ignore[assignment]
            
            # P4-B: Use robust extraction
            plan_json = self.llm.extract_json(raw_response)
            raw_steps = plan_json.get("steps", [])
            
            # P4-B: Validate and filter steps
            steps_data = []
            for s in raw_steps:
                if not isinstance(s, dict): continue
                kind = s.get("kind", "tool")
                name = s.get("name")
                if kind in ("tool", "skill") and not str(name or "").strip():
                    logger.warning("HierarchicalPlanner: skipping invalid step with empty name: %s", s)
                    continue
                steps_data.append(s)
            
            if not steps_data:
                raise ValueError("No valid steps found in LLM response")

        except (json.JSONDecodeError, AttributeError, Exception) as e:
            # Fallback to a single-step plan on error
            step = PlanStep(
                step_id="step_" + uuid.uuid4().hex[:8],
                description=goal,
                kind="llm_call",
                name="direct_model_call",
                args={"goal": goal, "context": context},
                fingerprint=get_goal_fingerprint(goal, context),
            )
            return Plan(
                plan_id=plan_id,
                goal=goal,
                milestones=[PlanMilestone(milestone_id="m1", title="Execute", steps=[step])],
                steps=[step],
                success_criteria=list(success_criteria or []),
                hard_constraints=list(hard_constraints or []),
                estimated_total_cost_tokens=int(step.estimated_cost_tokens or 0),
            )

        steps: List[PlanStep] = []
        for i, step_data in enumerate(steps_data):
            needs_sub_plan = step_data.get("needs_sub_plan", False)
            sub_steps = []
            
            if needs_sub_plan:
                sub_plan = await self.plan(
                    goal=step_data["description"],
                    context=context,
                    current_depth=current_depth + 1
                )
                sub_steps = sub_plan.steps

            step_args = step_data.get("args", {})
            target_file = step_args.get("path") or step_args.get("file") or step_args.get("target_path")
            step = PlanStep(
                step_id=f"step_{i+1}",
                description=step_data["description"],
                kind=step_data.get("kind", "llm_call"),
                name=step_data.get("name", "sub_task"),
                args=step_args,
                sub_steps=sub_steps,
                fingerprint=get_goal_fingerprint(step_data["description"], {**context, **step_args}),
                target_file=target_file,
            )
            step.depends_on = list(step_data.get("depends_on") or [])
            step.rollback_point = step_data.get("rollback_point")
            try:
                step.estimated_cost_tokens = int(step_data.get("estimated_cost_tokens") or 0)
            except Exception:
                step.estimated_cost_tokens = 0
            steps.append(step)

        milestones = [
            PlanMilestone(milestone_id="m1", title="Plan", steps=[]),
            PlanMilestone(milestone_id="m2", title="Execute", steps=steps),
        ]
        return Plan(
            plan_id=plan_id,
            goal=goal,
            milestones=milestones,
            steps=steps,
            success_criteria=list(success_criteria or []),
            hard_constraints=list(hard_constraints or []),
            estimated_total_cost_tokens=sum(int(s.estimated_cost_tokens or 0) for s in steps),
        )

    def _build_planning_prompt(
        self,
        goal: str,
        context: Dict[str, Any],
        *,
        success_criteria: List[str],
        hard_constraints: List[str],
        project_goal: Optional[str],
    ) -> str:
        domain = context.get("domain", "generic")
        
        # 1. Recall relevant memories
        memory_records = recall_for_task(domain, goal, top_k=5)
        
        # 2. Get available skills
        active_skills = self.skill_registry.list_skills(domain=domain, status=SkillStatus.ACTIVE)
        
        coder_backend = os.getenv("CODER_BACKEND", "gemini_cli")
        primary_tool = str(os.getenv("QUENTIN_CODING_TOOL_PRIMARY", "gemini.code") or "").strip()
        fallback_raw = str(os.getenv("QUENTIN_CODING_TOOL_FALLBACKS", "coder.generate") or "")
        fallback_tools = [x.strip() for x in fallback_raw.split(",") if x.strip()]
        preferred_tools = [x for x in [primary_tool, *fallback_tools] if x]
        coding_tool_hint = (
            "/".join(preferred_tools[:3])
            if preferred_tools
            else (f"'{coder_backend}'" if coder_backend != "llm_client" else "specialized coding tools")
        )

        context_summary = {k: v for k, v in context.items() if k in ["domain", "file_path", "environment"]}

        return f"""
You are a hierarchical planner. Your task is to break down a high-level goal into a series of smaller, manageable steps.
You have access to a list of memories from past tasks and a library of available skills. Use them to create a better plan.

Project goal (mid-term): {project_goal or ""}
Goal: {goal}
Context: {json.dumps(context_summary)}
Success criteria: {json.dumps(success_criteria)}
Hard constraints (must not violate): {json.dumps(hard_constraints)}

Available Memories:
{json.dumps([m.to_dict() for m in memory_records], indent=2)}

Available Skills:
{json.dumps([s.to_dict() for s in active_skills], indent=2)}

Respond with a JSON object containing a "steps" array. Do not add any explanatory text. 
IMPORTANT: DO NOT output Python code blocks or any other text. Output ONLY a raw JSON object.

CRITICAL (Dead Loop Prevention): 
1. Before creating directories (mkdir) or writing files (fs.write_file), ALWAYS include a probe step (e.g., 'fs.exists' or 'ls') to check the current state.
2. If a tool returns a status 'ok' with a result like 'skipped', 'already_exists', or 'idempotent_hit', DO NOT repeat that step. Proceed to the next logical step.
3. If a tool call fails, DO NOT generate a plan that retries the exact same command with the same arguments. Use 'pwd', 'ls -la', or 'id' to investigate environment blockers first.

CRITICAL (Coding Preference): For ANY programming, bug fixing, or code refactoring task, you SHOULD use {coding_tool_hint}. Do not attempt to write large code blocks manually using 'fs.write_file'. The system is configured to prefer {coding_tool_hint} for all code generation.

CRITICAL (Verification): If the goal involves modifying files or writing code, you MUST include a final verification step (e.g. using 'pytest' via 'shell.run_command' or a specific 's_test' skill) to provide green evidence of success.

Example JSON output:
{{
  "steps": [
    {{
      "step_id": "s1",
      "description": "Scan codebase",
      "kind": "tool",
      "name": "ls",
      "args": {{"path": "."}}
    }},
    {{
      "step_id": "s2",
      "description": "Generate patch using Gemini",
      "kind": "skill",
      "name": "{primary_tool or 'gemini.code'}",
      "args": {{"prompt": "...", "context_files": ["..."]}}
    }}
  ]
}}

Format for each step in "steps":
{{
  "step_id": "s1",
  "description": "Clear explanation of what this step does",
  "kind": "tool" | "skill" | "llm_call",
  "name": "The specific tool/skill name (e.g. 'fs.write_file', 'shell.run_command', 'mkdir')",
  "args": {{ ... arguments for the tool or skill ... }},
  "needs_sub_plan": false
}}

If a step is complex and needs further breakdown, mark it with "needs_sub_plan": true.
Each step may optionally include:
- depends_on: list of step_id strings
- rollback_point: short note about how to rollback
- estimated_cost_tokens: integer estimate
"""
