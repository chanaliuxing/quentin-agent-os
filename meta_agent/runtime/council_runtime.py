# meta_agent/runtime/council_runtime.py

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

import json
import textwrap

from meta_agent.runtime.council_config import DEFAULT_COUNCIL_CONFIG, ModelConfig
from meta_agent.llm.ollama_client import OllamaClient
from meta_agent.llm.client import LLMRequest
from meta_agent.config.feature_flags import PROMPT_MIGRATION_M1_SYSTEM_FACTORY, feature_flags
from quentin.cognitive.prompt_factory import build_system_prompt, RuntimeInfo


@dataclass
class CouncilTask:
    role: str
    question: str
    context: Dict[str, Any] = field(default_factory=dict)
    json_schema_hint: str = "{}"


@dataclass
class CouncilResult:
    raw_planner: str
    raw_critic: str
    raw_judge: str
    final_json: Dict[str, Any]


class CouncilRuntime:
    def __init__(
        self,
        ollama_client: Optional[OllamaClient] = None,
    ) -> None:
        self.ollama = ollama_client or OllamaClient()
        self.cfg = DEFAULT_COUNCIL_CONFIG

    @staticmethod
    def _clean(v: Any) -> str:
        return str(v or "").strip()

    def _use_prompt_factory(self) -> bool:
        return feature_flags.is_prompt_migration_enabled(PROMPT_MIGRATION_M1_SYSTEM_FACTORY, default=False)

    def _prompt_mode(self, task: CouncilTask) -> str:
        ctx = task.context or {}
        mode = self._clean(ctx.get("prompt_mode")).lower()
        if mode in {"full", "minimal"}:
            return mode
        if bool(ctx.get("is_subagent")):
            return "minimal"
        return "full"

    def _enabled_tools_from_context(self, ctx: Dict[str, Any]) -> Dict[str, str]:
        raw = ctx.get("enabled_tools")
        out: Dict[str, str] = {}
        if isinstance(raw, dict):
            for k, v in raw.items():
                name = self._clean(k)
                if not name:
                    continue
                out[name] = self._clean(v) or "tool available"
            return out
        if isinstance(raw, list):
            for item in raw:
                if isinstance(item, str) and self._clean(item):
                    out[self._clean(item)] = "tool available"
                elif isinstance(item, dict):
                    name = self._clean(item.get("name"))
                    if name:
                        out[name] = self._clean(item.get("summary")) or "tool available"
        return out

    def _runtime_info(self, cfg: ModelConfig, task: CouncilTask) -> RuntimeInfo:
        ctx = task.context or {}
        extras = {}
        role = self._clean(task.role)
        if role:
            extras["role"] = role
        return RuntimeInfo(
            agent_id=self._clean(ctx.get("agent_id")) or "quentin-council",
            workspace=self._clean(ctx.get("workspace")) or ".",
            os_name=self._clean(ctx.get("os")) or "unknown",
            model=self._clean(cfg.name) or "unknown",
            budget_remaining=self._clean(ctx.get("budget_remaining")) or None,
            extras=extras,
        )

    @staticmethod
    def _compose_prompt(system_prompt: str, user_prompt: str) -> str:
        return (
            f"[SYSTEM]\n{system_prompt.strip()}\n\n"
            f"[USER]\n{user_prompt.strip()}\n"
        ).strip()

    async def deliberate(self, task: CouncilTask) -> CouncilResult:
        planner_out = await self._run_planner(task)
        critic_out = await self._run_critic(task, planner_out)
        judge_out = await self._run_judge(task, planner_out, critic_out)

        final_json = self._extract_json(judge_out, task)

        return CouncilResult(
            raw_planner=planner_out, raw_critic=critic_out, raw_judge=judge_out, final_json=final_json,
        )

    async def ask_json(self, role: str, question: str, context: Dict[str, Any], json_schema_hint: str) -> Dict[str, Any]:
        task = CouncilTask(role=role, question=question, context=context, json_schema_hint=json_schema_hint)
        result = await self.deliberate(task)
        return result.final_json

    async def _run_planner(self, task: CouncilTask) -> str:
        cfg = self.cfg.planner
        prompt = self._build_planner_prompt(task)
        res = self.ollama.generate(
            LLMRequest(
                model=cfg.name, prompt=prompt, max_tokens=cfg.max_tokens, temperature=cfg.temperature,
            )
        )
        if hasattr(res, "__await__"):
            return await res
        return res

    async def _run_critic(self, task: CouncilTask, planner_out: str) -> str:
        cfg = self.cfg.critic
        prompt = self._build_critic_prompt(task, planner_out)
        res = self.ollama.generate(
            LLMRequest(
                model=cfg.name, prompt=prompt, max_tokens=cfg.max_tokens, temperature=cfg.temperature,
            )
        )
        if hasattr(res, "__await__"):
            return await res
        return res

    async def _run_judge(self, task: CouncilTask, planner_out: str, critic_out: str) -> str:
        cfg = self.cfg.judge
        prompt = self._build_judge_prompt(task, planner_out, critic_out)
        res = self.ollama.generate(
            LLMRequest(
                model=cfg.name, prompt=prompt, max_tokens=cfg.max_tokens, temperature=cfg.temperature,
            )
        )
        if hasattr(res, "__await__"):
            return await res
        return res

    def _build_planner_prompt(self, task: CouncilTask) -> str:
        ctx_json = json.dumps(task.context, ensure_ascii=False, indent=2)
        schema_hint = task.json_schema_hint.strip()
        if self._use_prompt_factory():
            system_prompt = build_system_prompt(
                mode=self._prompt_mode(task),
                identity="You are Planner in Quentin council runtime.",
                safety_rules=[
                    "You have no independent goals.",
                    "Follow task constraints and return schema-compliant output.",
                    "Do not fabricate missing context.",
                ],
                enabled_tools=self._enabled_tools_from_context(task.context or {}),
                runtime_info=self._runtime_info(self.cfg.planner, task),
                hints=[
                    "First reason briefly, then output one JSON object only.",
                    "JSON must satisfy the provided schema hint.",
                ],
            )
            user_prompt = textwrap.dedent(
                f"""
                当前决策角色: {task.role}
                问题：{task.question}
                上下文（JSON）:```json {ctx_json} ```
                请分两部分回答：
                1. 用自然语言分析问题，指出关键考虑点、风险与备选方案。
                2. 在最后一段，用一个 JSON 结构草案，尽量遵守以下约束：{schema_hint}
                注意：- 先分析，再给 JSON。- JSON 部分使用单独一段，以 {{ 开头，以 }} 结束。- 不要在 JSON 里夹带解释文字。
                """
            )
            return self._compose_prompt(system_prompt, user_prompt)

        return textwrap.dedent(f"""
        你是 Planner 模型，负责为一个自我迭代系统做决策草案。
        当前决策角色: {task.role}
        问题：{task.question}
        上下文（JSON）:```json {ctx_json} ```
        请分两部分回答：
        1. 用自然语言分析问题，指出关键考虑点、风险与备选方案。
        2. 在最后一段，用一个 JSON 结构草案，尽量遵守以下约束：{schema_hint}
        注意：- 先分析，再给 JSON。- JSON 部分使用单独一段，以 {{ 开头，以 }} 结束。- 不要在 JSON 里夹带解释文字。
        """)

    def _build_critic_prompt(self, task: CouncilTask, planner_out: str) -> str:
        schema_hint = task.json_schema_hint.strip()
        if self._use_prompt_factory():
            system_prompt = build_system_prompt(
                mode=self._prompt_mode(task),
                identity="You are Critic in Quentin council runtime.",
                safety_rules=[
                    "Focus on risk, omissions, and schema mismatches.",
                    "Do not output final JSON decision.",
                ],
                enabled_tools=self._enabled_tools_from_context(task.context or {}),
                runtime_info=self._runtime_info(self.cfg.critic, task),
                hints=[
                    "Give actionable critique.",
                    "Keep output concise.",
                ],
            )
            user_prompt = textwrap.dedent(
                f"""
                决策角色: {task.role}
                问题: {task.question}
                下面是 Planner 的完整输出：
                {planner_out}
                请：1. 找出 Planner 决策中的问题：逻辑漏洞、风险点、遗漏的情况、与约束不一致的地方。
                2. 指出它的 JSON 草案是否符合下面这些约束，并指出偏差：{schema_hint}
                3. 不要给最终 JSON，只给批评和改进建议。
                """
            )
            return self._compose_prompt(system_prompt, user_prompt)

        return textwrap.dedent(f"""
        你是 Critic 模型，负责审查 Planner 的草案。
        决策角色: {task.role}
        问题: {task.question}
        下面是 Planner 的完整输出：
        {planner_out}
        请：1. 找出 Planner 决策中的问题：逻辑漏洞、风险点、遗漏的情况、与约束不一致的地方。
        2. 指出它的 JSON 草案是否符合下面这些约束，并指出偏差：{schema_hint}
        3. 不要给最终 JSON，只给批评和改进建议。
        """)

    def _build_judge_prompt(self, task: CouncilTask, planner_out: str, critic_out: str) -> str:
        ctx_json = json.dumps(task.context, ensure_ascii=False, indent=2)
        schema_hint = task.json_schema_hint.strip()
        if self._use_prompt_factory():
            system_prompt = build_system_prompt(
                mode=self._prompt_mode(task),
                identity="You are Judge in Quentin council runtime.",
                safety_rules=[
                    "Decide using planner+critic evidence and constraints.",
                    "Output one valid JSON object at the end.",
                ],
                enabled_tools=self._enabled_tools_from_context(task.context or {}),
                runtime_info=self._runtime_info(self.cfg.judge, task),
                hints=[
                    "Summarize key critic issues in <=5 bullets.",
                    "Then provide final JSON only once.",
                ],
            )
            user_prompt = textwrap.dedent(
                f"""
                决策角色: {task.role}
                问题: {task.question}
                上下文（JSON）:```json {ctx_json} ```
                Planner 的输出：
                {planner_out}
                Critic 的意见：
                {critic_out}
                请你：1. 简要总结 Critic 提出的关键问题（不超过 5 条）。
                2. 在综合 Planner 和 Critic 的基础上，给出最终 JSON 决策，必须满足：{schema_hint}
                输出格式：- 先给 3-5 行中文解释你的决策理由。- 然后单独给出一段 JSON，使用 {{ 开头，以 }} 结束，不要在 JSON 中添加注释或多余字段。
                """
            )
            return self._compose_prompt(system_prompt, user_prompt)

        return textwrap.dedent(f"""
        你是 Judge 模型，负责在 Planner 和 Critic 的基础上，给出最终决策 JSON。
        决策角色: {task.role}
        问题: {task.question}
        上下文（JSON）:```json {ctx_json} ```
        Planner 的输出：
        {planner_out}
        Critic 的意见：
        {critic_out}
        请你：1. 简要总结 Critic 提出的关键问题（不超过 5 条）。
        2. 在综合 Planner 和 Critic 的基础上，给出最终 JSON 决策，必须满足：{schema_hint}
        输出格式：- 先给 3-5 行中文解释你的决策理由。- 然后单独给出一段 JSON，使用 {{ 开头，以 }} 结束，不要在 JSON 中添加注释或多余字段。
        """)

    def _extract_json(self, judge_out: str, task: CouncilTask) -> Dict[str, Any]:
        text = judge_out.strip()
        
        # Strategy: find all potential JSON blocks using regex and try to load the last one
        import re
        json_blocks = re.findall(r"\{[^{}]*\}", text) # Simple regex, might need more robust
        
        extracted_json = None
        for block in reversed(json_blocks): # Try to parse the last block first
            try:
                extracted_json = json.loads(block)
                break # Found a valid JSON
            except json.JSONDecodeError:
                continue
        
        if extracted_json:
            return extracted_json
        
        # Fallback to original logic if regex fails, or if it's a markdown-wrapped block
        start = text.find("{")
        end = text.rfind("}")
        if "```json" in text: # Prioritize markdown-wrapped JSON
            try:
                json_str_wrapped = text.split("```json")[1].split("```")[0].strip()
                return json.loads(json_str_wrapped)
            except Exception:
                pass # Fallback to other methods
        elif "```" in text and start != -1 and end != -1: # Generic markdown block
            try:
                json_str_wrapped = text.split("```")[1].split("```")[0].strip()
                return json.loads(json_str_wrapped)
            except Exception:
                pass # Fallback
                
        if start != -1 and end != -1 and end > start:
            json_str = text[start : end + 1]
            try: return json.loads(json_str)
            except Exception as e:
                return {"status": "parse_error", "raw": judge_out, "reason": f"json_decode_error: {e}"}

        return {"status": "parse_error", "raw": judge_out, "reason": "no_json_block"}
