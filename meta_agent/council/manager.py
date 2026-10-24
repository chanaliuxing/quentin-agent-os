from __future__ import annotations

import json
import logging
import re
import textwrap
from typing import Dict, List, Optional, Sequence

from meta_agent.council.models import (
    CouncilConfig,
    CouncilOutcome,
    CouncilRound,
    MemberConfig,
    MemberReply,
    ModeratorOutput,
    NextQuestion,
)
from meta_agent.llm.client import LLMClient, LLMRequest
from meta_agent.llm.ollama_client import OllamaClient

logger = logging.getLogger(__name__)


class CouncilManager:
    """
    CouncilManager v3: multi-round debate with stall handling and structured outputs.

    This is a pragmatic implementation based on docs/council/llm.md:
    - bounded rounds with stall detection
    - structured member replies and moderator outputs
    - working memory budget with trimming
    """

    def __init__(
        self,
        llm_client: Optional[LLMClient] = None,
        config: Optional[CouncilConfig] = None,
    ) -> None:
        self.llm = llm_client or OllamaClient()
        self.config = config or CouncilConfig()

    def run(
        self,
        question: str,
        *,
        context: Optional[Dict] = None,
        json_schema_hint: str = "{}",
    ) -> CouncilOutcome:
        cfg = self.config
        working_memory = self._initial_summary(question, context)
        open_issues: List[str] = []
        next_round_plan: List[NextQuestion] = [NextQuestion(target="all", question=question)]
        stalled_count = 0
        rounds: List[CouncilRound] = []

        for r in range(1, cfg.max_rounds + 1):
            replies = self._gather_replies(
                round_id=r,
                plan=next_round_plan,
                working_memory=working_memory,
                context=context or {},
                members=cfg.members,
            )
            moderator_output = self._moderate(
                question=question,
                working_memory=working_memory,
                open_issues=open_issues,
                replies=replies,
                json_schema_hint=json_schema_hint,
            )
            working_memory = self._clamp_summary(moderator_output.current_summary, cfg.summary_max_chars)
            progressed = bool(
                moderator_output.progress_notes
                or moderator_output.resolved_issues
                or moderator_output.newly_added_issues
            )

            if self._issues_equivalent(open_issues, moderator_output.open_issues) and not progressed:
                stalled_count += 1
            else:
                stalled_count = 0

            open_issues = moderator_output.open_issues
            rounds.append(
                CouncilRound(
                    round_id=r,
                    replies=replies,
                    moderator=moderator_output,
                    working_memory=working_memory,
                )
            )

            if moderator_output.verdict != "debate":
                return CouncilOutcome(
                    question=question,
                    final_output=moderator_output,
                    rounds=rounds,
                    working_memory=working_memory,
                    stalled=False,
                    forced=False,
                )

            if stalled_count >= cfg.stall_rounds:
                forced = self._force_revise(moderator_output, reason="stalled")
                return CouncilOutcome(
                    question=question,
                    final_output=forced,
                    rounds=rounds,
                    working_memory=working_memory,
                    stalled=True,
                    forced=True,
                )

            if r == cfg.max_rounds:
                forced = self._force_revise(moderator_output, reason="max_rounds")
                return CouncilOutcome(
                    question=question,
                    final_output=forced,
                    rounds=rounds,
                    working_memory=working_memory,
                    stalled=False,
                    forced=True,
                )

            next_round_plan = moderator_output.next_round_plan or [NextQuestion(target="all", question=question)]

        # Should not reach here because loop returns
        return CouncilOutcome(
            question=question,
            final_output=rounds[-1].moderator if rounds else ModeratorOutput(
                verdict="revise",
                current_summary=working_memory,
                open_issues=open_issues,
                final_answer={"status": "no_rounds"},
            ),
            rounds=rounds,
            working_memory=working_memory,
        )

    def _gather_replies(
        self,
        *,
        round_id: int,
        plan: Sequence[NextQuestion],
        working_memory: str,
        context: Dict,
        members: Sequence[MemberConfig],
    ) -> List[MemberReply]:
        plan_by_member: Dict[str, List[str]] = {}
        for q in plan:
            if q.target == "all":
                for m in members:
                    plan_by_member.setdefault(m.member_id, []).append(q.question)
            else:
                plan_by_member.setdefault(q.target, []).append(q.question)

        replies: List[MemberReply] = []
        for member in members:
            questions = plan_by_member.get(member.member_id)
            if not questions:
                continue
            prompt = self._build_member_prompt(member=member, questions=questions, working_memory=working_memory, context=context)
            raw = self.llm.generate(
                LLMRequest(
                    model=member.model,
                    prompt=prompt,
                    max_tokens=1024,
                    temperature=member.temperature,
                )
            )
            parsed = self._parse_json(raw)
            reply = MemberReply(
                member_id=member.member_id,
                stance=(parsed.get("stance") or "neutral"),
                key_points=parsed.get("key_points") or [],
                risks=parsed.get("risks") or [],
                missing_info=parsed.get("missing_info") or [],
                proposed_changes=parsed.get("proposed_changes") or [],
                confidence=float(parsed.get("confidence") or 0.6),
                raw=raw,
            )
            replies.append(reply)
        return replies

    def _moderate(
        self,
        *,
        question: str,
        working_memory: str,
        open_issues: List[str],
        replies: List[MemberReply],
        json_schema_hint: str,
    ) -> ModeratorOutput:
        prompt = self._build_moderator_prompt(
            question=question,
            working_memory=working_memory,
            open_issues=open_issues,
            replies=replies,
            json_schema_hint=json_schema_hint,
        )
        raw = self.llm.generate(
            LLMRequest(
                model=self.config.members[0].model,
                prompt=prompt,
                max_tokens=1536,
                temperature=0.2,
            )
        )
        parsed = self._parse_json(raw)
        try:
            return ModeratorOutput(**parsed)
        except Exception:
            logger.exception("Failed to parse moderator output, falling back to revise.")
            return ModeratorOutput(
                verdict="revise",
                debate_type="needs_info",
                open_issues=open_issues,
                next_round_plan=[],
                current_summary=working_memory,
                progress_notes=[],
                resolved_issues=[],
                newly_added_issues=[],
                confidence=0.5,
                final_answer={"raw": raw, "parsed": parsed},
            )

    def _force_revise(self, mod: ModeratorOutput, reason: str) -> ModeratorOutput:
        return ModeratorOutput(
            verdict="revise",
            debate_type=mod.debate_type or "needs_info",
            open_issues=mod.open_issues,
            next_round_plan=[],
            current_summary=mod.current_summary,
            progress_notes=mod.progress_notes,
            resolved_issues=mod.resolved_issues,
            newly_added_issues=mod.newly_added_issues,
            confidence=mod.confidence,
            final_answer={
                "reason": reason,
                "open_issues": mod.open_issues,
                "summary": mod.current_summary,
            },
        )

    def _initial_summary(self, question: str, context: Optional[Dict]) -> str:
        ctx = json.dumps(context or {}, ensure_ascii=False, indent=2)
        return self._structured_summary(
            agreed=[f"Question: {question}"],
            open_issues=["Pending: initial clarification"],
            evidence=[ctx],
            decision_boundary=["Constrain summary to budget, keep JSON-ready facts only"],
        )

    def _structured_summary(
        self,
        *,
        agreed: Sequence[str],
        open_issues: Sequence[str],
        evidence: Sequence[str],
        decision_boundary: Sequence[str],
    ) -> str:
        def section(title: str, items: Sequence[str]) -> str:
            body = "\n".join(f"- {item}" for item in items) if items else "- (none)"
            return f"{title}:\n{body}"

        return "\n".join(
            [
                section("Agreed", agreed),
                section("Open issues", open_issues),
                section("Evidence/Constraints", evidence),
                section("Decision boundary", decision_boundary),
            ]
        )

    def _clamp_summary(self, summary: str, budget: int) -> str:
        if len(summary) <= budget:
            return summary
        return summary[: budget - 3] + "..."

    def _issues_equivalent(self, a: Sequence[str], b: Sequence[str]) -> bool:
        # Mid-level similarity: normalized set equality with Jaccard similarity fallback.
        def norm(items: Sequence[str]) -> set[str]:
            cleaned = []
            for item in items:
                normalized = re.sub(r"[^\w\s]", "", item).strip().lower()
                cleaned.append(normalized)
            return set(cleaned)

        na, nb = norm(a), norm(b)
        if na == nb:
            return True
        if not na or not nb:
            return False
        intersection = len(na & nb)
        union = len(na | nb)
        if union == 0:
            return False
        jaccard = intersection / union
        return jaccard >= self.config.issue_similarity_threshold

    def _parse_json(self, text: str) -> Dict:
        # Try to find the last JSON block
        blocks = re.findall(r"\{.*\}", text, flags=re.S)
        for block in reversed(blocks):
            try:
                return json.loads(block)
            except Exception:
                continue
        try:
            return json.loads(text)
        except Exception:
            logger.warning("Failed to parse JSON from LLM output, returning empty dict.")
            return {}

    def _build_member_prompt(
        self,
        *,
        member: MemberConfig,
        questions: Sequence[str],
        working_memory: str,
        context: Dict,
    ) -> str:
        qs = "\n".join(f"- {q}" for q in questions)
        return textwrap.dedent(
            f"""
            你是委员会成员：{member.role}（ID: {member.member_id}）。
            请只回答被点名的问题，不要重复已知摘要。

            Summary (structured, do not restate unless needed):
            {working_memory}

            Questions:
            {qs}

            Output JSON (no extra text):
            {{
              "stance": "approve|reject|revise|neutral",
              "key_points": ["..."],
              "risks": ["..."],
              "missing_info": ["..."],
              "proposed_changes": ["..."],
              "confidence": 0.0
            }}
            """
        ).strip()

    def _build_moderator_prompt(
        self,
        *,
        question: str,
        working_memory: str,
        open_issues: Sequence[str],
        replies: Sequence[MemberReply],
        json_schema_hint: str,
    ) -> str:
        replies_json = json.dumps([r.dict() for r in replies], ensure_ascii=False, indent=2)
        open_issues_text = "\n".join(f"- {issue}" for issue in open_issues) or "- (none)"
        schema_hint = json_schema_hint.strip() or "{}"
        return textwrap.dedent(
            f"""
            你是 Moderator，维护会议纪要并做出决策。
            目标：在 1~{self.config.max_rounds} 轮内收敛，遵守硬约束，输出纯 JSON。

            Question: {question}
            Working memory (请遵守结构: Agreed / Open issues / Evidence / Decision boundary):
            {working_memory}

            Open issues:
            {open_issues_text}

            Member replies (JSON):
            {replies_json}

            请输出 ModeratorOutput JSON，字段约束：
            - verdict: "approve"|"reject"|"revise"|"debate"
            - debate_type: "conflict"|"needs_info"|"quality_gap"|null
            - open_issues: list[str]
            - next_round_plan: list[{{"target": "all|member_id", "question": str}}]
            - current_summary: string (请压缩到 {self.config.summary_max_chars} 字符以内)
            - progress_notes/resolved_issues/newly_added_issues: list[str]
            - confidence: 0..1
            - final_answer: required if verdict != debate
            - 若 verdict==debate，next_round_plan 必须非空

            同时满足下列 schema 提示：{schema_hint}
            只输出 JSON。
            """
        ).strip()
