from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Optional, Tuple
import json
import logging

logger = logging.getLogger(__name__)


@dataclass
class CouncilMemberResponse:
    name: str
    model_name: str
    role: str
    answer: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class CouncilDeliberationResult:
    question: str
    context: Dict[str, Any]
    final_answer: str
    reasoning: str
    members: List[CouncilMemberResponse]
    raw_summary_text: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "question": self.question,
            "context": self.context,
            "final_answer": self.final_answer,
            "reasoning": self.reasoning,
            "members": [m.to_dict() for m in self.members],
            "raw_summary_text": self.raw_summary_text,
        }


class MultiModelCouncil:
    """
    多模型“开会”协调器。

    - members: [(name, llm_client)]
    - aggregator: 一个负责汇总的 llm（通常是最强/最稳的模型）

    提供：
      - deliberate(question, context) -> CouncilDeliberationResult
    """

    def __init__(
        self,
        members: List[Tuple[str, Any]],
        aggregator: Any,
        member_roles: Optional[Dict[str, str]] = None,
    ) -> None:
        self.members = members
        self.aggregator = aggregator
        self.member_roles = member_roles or {}

    # --------------------------------------------------
    # 对外主接口：多模型协商
    # --------------------------------------------------
    def deliberate(
        self,
        question: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> CouncilDeliberationResult:
        """
        让多个模型对同一个问题独立给出意见，然后由 aggregator 汇总。

        适用场景：
          - 重要计划（planner）
          - 多次失败的任务重试前
          - 代码生成/自编程时的风险评估
        """
        ctx = context or {}
        member_responses: List[CouncilMemberResponse] = []

        # 1) 每个成员单独思考
        for name, llm in self.members:
            role = self.member_roles.get(name, "general-specialist")
            model_name = getattr(llm, "model", getattr(llm, "name", "unknown"))

            prompt = self._build_member_prompt(
                member_name=name,
                member_role=role,
                question=question,
                context=ctx,
            )
            try:
                answer_text = _call_llm(llm, prompt)
            except Exception:
                logger.exception("MultiModelCouncil: member %s failed", name)
                answer_text = "[ERROR] member failed to respond."

            member_responses.append(
                CouncilMemberResponse(
                    name=name,
                    model_name=model_name,
                    role=role,
                    answer=answer_text,
                )
            )

        # 2) aggregator 汇总 / 做最终决策建议
        summary_prompt = self._build_aggregator_prompt(
            question=question,
            context=ctx,
            member_responses=member_responses,
        )
        try:
            summary_text = _call_llm(self.aggregator, summary_prompt)
        except Exception:
            logger.exception("MultiModelCouncil: aggregator failed, fallback to simple merge")
            summary_text = self._fallback_summary(member_responses)

        final_answer, reasoning = self._parse_summary(summary_text)

        return CouncilDeliberationResult(
            question=question,
            context=ctx,
            final_answer=final_answer,
            reasoning=reasoning,
            members=member_responses,
            raw_summary_text=summary_text,
        )

    # --------------------------------------------------
    # Prompt 构造
    # --------------------------------------------------
    def _build_member_prompt(
        self,
        *,
        member_name: str,
        member_role: str,
        question: str,
        context: Dict[str, Any],
    ) -> str:
        ctx_json = json.dumps(context, ensure_ascii=False, indent=2)
        return (
            f"你是一个多模型委员会中的成员：{member_name}，角色：{member_role}。\n"
            f"现在有一个问题需要你独立思考并给出专业意见：\n\n"
            f"【问题】\n{question}\n\n"
            f"【上下文（可能为英文或结构化 JSON）】\n{ctx_json}\n\n"
            f"请你：\n"
            f"1. 简要说明你如何理解这个问题。\n"
            f"2. 给出你的建议方案（可以是步骤、代码策略或风险分析）。\n"
            f"3. 明确指出你认为的主要风险和不确定性。\n"
            f"请用尽量清晰、结构化的中文或英文回答，不要问我问题。"
        )

    def _build_aggregator_prompt(
        self,
        *,
        question: str,
        context: Dict[str, Any],
        member_responses: List[CouncilMemberResponse],
    ) -> str:
        ctx_json = json.dumps(context, ensure_ascii=False, indent=2)

        body_parts = []
        for m in member_responses:
            body_parts.append(
                f"[成员 {m.name} / 模型 {m.model_name} / 角色 {m.role} 的意见]\n{m.answer}\n"
            )
        body = "\n\n".join(body_parts)

        return (
            "你现在扮演多模型委员会的主席（Aggregator）。\n\n"
            "下面是多个不同模型对同一问题给出的独立回答，你需要：\n"
            "1. 找出它们的共识部分。\n"
            "2. 指出主要分歧点。\n"
            "3. 在充分考虑风险的前提下，给出一个综合性的、谨慎的最终建议。\n"
            "4. 你的输出需要是一个 JSON 对象，字段包括：\n"
            '   - \"final_answer\": 综合建议（字符串，尽量简洁）。\n'
            '   - \"reasoning\": 你综合和权衡的过程说明。\n\n"'
            "【问题】\n"
            f"{question}\n\n"
            "【上下文】\n"
            f"{ctx_json}\n\n"
            "【成员回答】\n"
            f"{body}\n\n"
            "请只输出一个 JSON 对象，不要有其它文字。"
        )

    # --------------------------------------------------
    # 汇总结果解析 & fallback
    # --------------------------------------------------
    def _parse_summary(self, summary_text: str) -> (str, str):
        """
        解析 aggregator 输出的 JSON，如果失败则做一个宽松降级。
        """
        summary_text = summary_text.strip()
        try:
            # Try to find JSON block if marked
            if "```json" in summary_text:
                parts = summary_text.split("```json")
                if len(parts) > 1:
                    summary_text = parts[1].split("```")[0].strip()
            elif "```" in summary_text: # generic code block
                 parts = summary_text.split("```")
                 if len(parts) > 1:
                    summary_text = parts[1].strip()

            data = json.loads(summary_text)
            final_answer = data.get("final_answer") or ""
            reasoning = data.get("reasoning") or ""
            return final_answer, reasoning
        except Exception:
            # fallback：当成普通文本，final_answer=全文，reasoning=简单说明
            logger.warning("MultiModelCouncil: summary not valid JSON, use fallback")
            return summary_text, "Aggregator summary was not valid JSON; using raw text as final_answer."

    def _fallback_summary(self, members: List[CouncilMemberResponse]) -> str:
        parts = []
        for m in members:
            parts.append(f"[{m.name}] {m.answer}")
        return "\n\n".join(parts)


def _call_llm(llm: Any, prompt: str) -> str:
    """
    统一 LLM 调用接口，兼容多种实现：

    优先：
      - llm.complete(prompt=...)
      - llm.generate(prompt=...)
      - llm(prompt)
    """
    from quentin.llm.context_budget import apply_context_budget
    guarded_prompt, guard = apply_context_budget(prompt_text=prompt)
    if guard.should_block:
        raise ValueError(
            f"context budget blocked: reason={guard.reason} total={guard.total_tokens} window={guard.tokens}"
        )
    if hasattr(llm, "complete"):
        return llm.complete(guarded_prompt)
    if hasattr(llm, "generate"):
        # quentin.orchestrator.core.LanguageModel expects generate(messages, ...) usually, 
        # but here we are passing a prompt string.
        # OllamaLLM implementation I wrote in step 99.md expects generate(messages: List[Dict]).
        # So I need to adapt this _call_llm to construct messages if needed.
        # Checking OllamaLLM implementation... yes, it expects messages.
        
        # Let's try to detect if it's OllamaLLM-like or just text generation.
        # If it's our OllamaLLM, we should wrap prompt in messages.
        try:
             # Try as if it supports prompt argument (some libs do)
             return llm.generate(prompt=guarded_prompt)
        except TypeError:
             # If it fails, try messages
             return llm.generate(messages=[{"role": "user", "content": guarded_prompt}])
        except Exception:
             # Reraise or try generic call
             pass

    if callable(llm):
        return llm(guarded_prompt)
    raise RuntimeError("LLM client has no complete/generate/callable interface")
