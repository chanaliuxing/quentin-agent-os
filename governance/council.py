from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List

from quentin.infra.logging import Tracer
from quentin.agents.coordinator import MultiAgentCoordinator
from quentin.agents.roles import AgentInput
from governance.constitution import Constitution # Real Constitution class
from quentin.self_programming.schemas import PatchDraft # For review_draft type hint
from quentin.self_improvement.schemas import ImprovementTask # For review_draft type hint

@dataclass
class GovernanceCouncil:
    """
    AI Governance Council v1:
    - Uses a MultiAgentCoordinator to review patches and experiments.
    - Makes decisions based on a 'Constitution'.
    """
    coordinator: MultiAgentCoordinator
    constitution: Constitution
    tracer: Tracer

    def _build_governance_prompt(self, patch_report: Dict[str, Any], domain: str) -> str:
        """
        Helper to build a prompt for the governance agents.
        """
        # Simplified prompt construction
        prompt = "Review the following patch based on our constitution.\n"
        prompt += f"Constitution Principles: {self.constitution.raw_spec.get('global_principles', [])}\n"
        prompt += f"Domain Goals for '{domain}': {self.constitution.raw_spec.get('domains', {}).get(domain, {})}\n"
        prompt += f"Patch Report: {patch_report}\n"
        prompt += "Decision (approve/reject/revise) and Rationale:"
        return prompt

    def _aggregate_decision(self, views: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Simple aggregation: for now, just a placeholder.
        A real implementation would have voting, debate, etc.
        """
        # Placeholder: if any agent says "reject", reject. Otherwise approve.
        for view in views:
            if "reject" in view.get("content", "").lower():
                return {"decision": "reject", "rationale": "An agent voted to reject."}
        
        return {"decision": "approve", "rationale": "All agents approved (or did not explicitly reject)."}

    async def review_draft(self, draft: "PatchDraft", task: "ImprovementTask", constitution: "Constitution") -> Dict[str, Any]:
        # This is a placeholder for reviewing a design draft.
        # The logic would be similar to review_patch.
        # For now, we'll just approve it.
        return {"decision": "approve", "rationale": "Draft approved by placeholder logic."}

    async def review_patch(self, patch_report: Dict[str, Any], domain: str) -> Dict[str, Any]:
        """
        由多个 AI 角色在宪法+目标下共同审查 patch，给出 approve/reject/revise。
        """

        # 1. 准备 prompt（包含宪法、目标、patch内容、实验指标）
        prompt = self._build_governance_prompt(patch_report, domain)

        # 2. 让不同角色给出意见
        inp = AgentInput(
            role="governance",
            task_type="patch_review",
            domain=domain,
            prompt=prompt,
        )
        result = await self.coordinator.run_multi_view(inp)

        # 3. 在这里可以加入简单的“投票规则”
        decision = self._aggregate_decision(result["views"])

        # 4. 写 Trace
        self.tracer.span(
            "L3",
            "governance_review",
            module="governance",
            input={"patch_id": patch_report.get("patch_id"), "domain": domain},
            output={"decision": decision["decision"]},
        )

        return decision
