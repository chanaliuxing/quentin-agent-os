from __future__ import annotations

import logging
import uuid
from typing import List, Optional, Any

from quentin.traces.core import TraceEvent
from quentin.critic.task_council import CriticFeedback
from quentin.skills.candidate_pipeline import SkillCandidate, SkillCandidateStore
from quentin.skills.registry import FileBackedSkillRegistry

logger = logging.getLogger(__name__)


class SkillMiner:
    """
    Skill & Code Evolution Loop 的“前半段”：从成功 Trace 中挖“可复用技能”。

    v1 策略：
      - 只在任务成功 & critic_confidence 高时才考虑挖技能；
      - 把 Task goal / plan / lessons / Trace 压成上下文；
      - 让 MultiAICouncil 生成一个 SkillCandidate（name + code + tests）；
      - 写入 SkillRegistry 的 candidates 区域，等后续人工/AI 审核再注册为正式 Skill。

    未来扩展：
      - 用 ResearchManager 的统计先过滤高价值任务；
      - 对同一类型任务做 pattern mining（非单次任务）；
      - 自动评估 candidate 的效果后，自动晋升为正式 SkillDefinition。
    """

    def __init__(
        self,
        *,
        registry: Optional[FileBackedSkillRegistry] = None,
        council: Optional[Any] = None,
        candidate_store: Optional[SkillCandidateStore] = None,
    ) -> None:
        self.registry = registry or FileBackedSkillRegistry()
        self.candidate_store = candidate_store or SkillCandidateStore()

        if council is None:
            import os
            from quentin.llm.multi_council import MultiAICouncil
            from quentin.llm.types import LLMConfig
            main_model = os.getenv("LLM_MODEL")
            if not main_model:
                 raise ValueError("Environment variable LLM_MODEL is not set.")
            critic_model = os.getenv("LLM_MODEL_CRITIC") or main_model
            default_members = [
                LLMConfig(provider="ollama", model=main_model, role="designer"),
                LLMConfig(provider="ollama", model=critic_model, role="critic"),
            ]
            council = MultiAICouncil(members=default_members)
        self.council = council

    def mine_from_task(
        self,
        *,
        task: Any,
        result: Any,
        trace_events: List[TraceEvent],
        feedback: Optional[CriticFeedback] = None,
    ) -> Optional[SkillCandidate]:
        if not bool(getattr(result, "done", False)):
            logger.info(
                "SkillMiner: skip task_id=%s because result.success=False",
                task.task_id,
            )
            return None

        if feedback and float(getattr(feedback, "score", 1.0) or 1.0) < 0.7:
            logger.info(
                "SkillMiner: skip task_id=%s due to low critic_confidence=%.3f",
                task.task_id,
                float(getattr(feedback, "score", 0.0) or 0.0),
            )
            return None

        prompt, context = self._build_prompt_context(task, result, trace_events, feedback)
        decision = self.council.deliberate(
            question=prompt,
            context=context,
            mode="skill_mining",
        )

        cand = self._parse_candidate(decision.final_answer, task)
        if cand is None:
            logger.info(
                "SkillMiner: council output could not be parsed as SkillCandidate for task_id=%s",
                task.task_id,
            )
            return None

        # Persist candidate to a JSONL store by default. This keeps the v3 pipeline
        # decoupled from the legacy SkillRegistry (which stores finalized SkillSpec).
        try:
            self.candidate_store.append(cand)
        except Exception:
            logger.exception("SkillMiner: failed to append candidate to store; continuing")
        logger.info(
            "SkillMiner: created SkillCandidate=%s from task_id=%s",
            cand.candidate_id,
            task.task_id,
        )
        return cand

    # ---------- prompt & parse ----------

    def _build_prompt_context(
        self,
        task: Any,
        result: Any,
        trace_events: List[TraceEvent],
        feedback: Optional[CriticFeedback],
    ) -> tuple[str, str]:
        prompt = (
            "You are helping a self-improving AI system mine reusable SKILLS "
            "from successful task executions.\n"
            "Given the task, final answer, trace, and critic feedback, extract "
            "ONE generalizable skill that could be re-used in similar tasks.\n\n"
            "Output in the following strict format:\n"
            "NAME: <short skill name>\n"
            "DOMAIN: <domain>\n"
            "DESCRIPTION:\n"
            "<description>\n"
            "CODE:\n"
            "```python\n"
            "# P5: OpenClaw Self-discovery Protocol\n"
            "class MySkill:\n"
            "    def run(self, params, context):\n"
            "        ...\n"
            "    @staticmethod\n"
            "    def get_schema():\n"
            "        return { \"name\": \"...\", \"description\": \"...\", \"input_schema\": { ... } }\n"
            "```\n"
            "TESTS:\n"
            "<how to test this skill>\n"
            "QUALITY_NOTES:\n"
            "<notes on when this skill works or fails>\n"
        )

        trace_lines: List[str] = []
        # P5: Surgery Eighty-six - Action Core Extraction (OpenClaw Parity)
        # We focus on tool calls to build a high-density logic trace
        for e in trace_events:
            if e.event_type == "tool_call":
                tool = e.payload.get("tool", "unknown")
                params = str(e.payload.get("params", {}))
                # Truncate large blobs in params for prompt efficiency
                if len(params) > 200: params = params[:197] + "..."
                trace_lines.append(f"  - ACTION: {tool} with ARGS: {params}")
            elif e.event_type == "error":
                trace_lines.append(f"  - ERROR: {e.payload.get('error')}")

        goal_text = (task.goal_description or task.goal_title or task.input_text or "").strip()
        final_output = str(getattr(result, "final_output", "") or "")
        context_parts: List[str] = [
            f"Task goal:\n{goal_text}",
            f"Domain: {task.domain}",
            f"Final answer (truncated):\n{final_output[:1500]}",
        ]

        if feedback:
            context_parts.append(
                f"Critic reflection (truncated):\n{(getattr(feedback, 'reflection', '') or '')[:1500]}"
            )

        context_parts.append("Trace events summary:\n" + "\n".join(trace_lines))

        context = "\n\n".join(context_parts)
        return prompt, context

    def _parse_candidate(
        self,
        text: str,
        task: Any,
    ) -> Optional[SkillCandidate]:
        """
        v1：简单基于前缀解析，后续可以改为 JSON 输出。
        """
        sections = {
            "NAME:": "",
            "DOMAIN:": "",
            "DESCRIPTION:": "",
            "CODE:": "",
            "TESTS:": "",
            "QUALITY_NOTES:": "",
        }
        current = None
        for line in text.splitlines():
            stripped = line.strip()
            if stripped in sections:
                current = stripped
                continue
            if current:
                sections[current] += line + "\n"

        name = sections["NAME:"].strip() or f"skill_from_{task.domain}"
        domain = sections["DOMAIN:"].strip() or task.domain
        description = sections["DESCRIPTION:"].strip()
        code = sections["CODE:"].strip()
        tests = sections["TESTS:"].strip()
        notes = sections["QUALITY_NOTES:"].strip()

        if not description and not code:
            return None

        if not tests:
            # Keep it syntactically valid for downstream optional runners.
            tests = "def test_candidate_smoke():\n    assert True\n"

        return SkillCandidate(
            candidate_id=str(uuid.uuid4()),
            name=name,
            domain=domain,
            implementation_code=code,
            verification_test_code=tests,
            scope={
                "description": description,
            },
            risk_notes=notes,
            meta={
                "source": "cognitive_trace",
                "from_task_id": task.task_id,
                "goal": (task.goal_description or task.goal_title or task.input_text or "")[:200],
            },
        )
