from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Dict, List, Optional
import os
import logging
import json

from quentin.llm.ollama_client import OllamaChatClient, ChatMessage

logger = logging.getLogger(__name__)


@dataclass
class CouncilConfig:
    planner_model: str
    critic_model: Optional[str] = None
    referee_model: Optional[str] = None
    temperature_planner: float = 0.2
    temperature_critic: float = 0.3
    temperature_referee: float = 0.2


class CouncilRuntime:
    """
    多模型议会的统一入口。
    """

    def __init__(self, client: OllamaChatClient, config: CouncilConfig):
        self.client = client
        self.config = config

    # ---------- 工具方法 ----------

    def _chat(
        self,
        model: str,
        system_prompt: str,
        user_content: str,
        temperature: float,
    ) -> str:
        messages = [
            ChatMessage(role="system", content=system_prompt),
            ChatMessage(role="user", content=user_content),
        ]
        return self.client.chat(model=model, messages=messages, temperature=temperature)

    def _chat_json(
        self,
        model: str,
        system_prompt: str,
        user_content: str,
        temperature: float,
    ) -> Any:
        raw = self._chat(model, system_prompt, user_content, temperature)
        try:
            return self.client.extract_json(raw)
        except Exception:
            logger.warning("Failed to parse JSON from model output: %s", raw)
            raise

    # ---------- 1. 反思：ask_for_reflection ----------

    def ask_for_reflection(self, payload: Dict[str, Any]) -> str:
        system_prompt = """You are a meta-cognition assistant for an AI agent.
Given a task result and its context, produce a short reflection:

- What went well
- What went wrong (if anything)
- What should be done differently next time

Return plain text (no JSON), concise but specific.
"""
        user_content = json.dumps(payload, ensure_ascii=False, indent=2)
        return self._chat(
            model=self.config.planner_model,
            system_prompt=system_prompt,
            user_content=user_content,
            temperature=self.config.temperature_planner,
        )

    # ---------- 2. 记忆总结：summarize_memories ----------

    def summarize_memories(self, payload: Dict[str, Any]) -> str:
        system_prompt = """You are a consolidation module of a self-improving AI agent.
You receive a list of short-term reflections (memories) and should write a compact
mid-term summary focusing on reusable patterns, stable lessons, and key insights.

Return plain text, structured in bullet points or short paragraphs. Avoid redundancy.
"""
        user_content = json.dumps(payload, ensure_ascii=False, indent=2)
        return self._chat(
            model=self.config.planner_model,
            system_prompt=system_prompt,
            user_content=user_content,
            temperature=self.config.temperature_planner,
        )

    # ---------- 3. Skill 抽象：propose_skill_from_examples ----------

    def propose_skill_from_examples(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        system_prompt_planner = """You are a skill architect for a self-improving AI agent.

From the given successful task examples, extract ONE reusable, general-purpose skill that
could be implemented as a callable function/tool.

You MUST respond with a JSON object ONLY, with the following fields:
- name: string
- domain: string
- short_description: string
- detailed_description: string
- tags: string[]
- parameters: object (parameter schema, keys are parameter names, values describe types & meaning)
- examples: array of {input: object, output: object, notes: string}
- notes: string

Do NOT include any extra commentary outside the JSON.
"""
        user_content = json.dumps(payload, ensure_ascii=False, indent=2)

        draft = self._chat(
            model=self.config.planner_model,
            system_prompt=system_prompt_planner,
            user_content=user_content,
            temperature=self.config.temperature_planner,
        )

        if self.config.critic_model:
            critic_prompt = """You are an AI skill design critic.

You are given:
1) The original request and examples.
2) A draft JSON describing a proposed skill.

Your job:
- Check if the JSON is syntactically valid (keys present, JSON-only).
- Check if the skill is sufficiently GENERAL and REUSABLE across similar tasks.
- Propose concrete fixes if something is off (e.g., parameters unclear, examples missing).

Output a JSON object:
{
  "is_valid": bool,
  "should_revise": bool,
  "revision_instructions": \"string (if should_revise is true, explain concretely how to modify the draft)\",
  "final_json_if_small_fix": {{
      // optional: if you can directly fix small issues, put the full corrected JSON here
  }}
}"""
            critic_input = {
                "original_payload": payload,
                "draft_output": draft,
            }
            critic_raw = self._chat(
                model=self.config.critic_model,
                system_prompt=critic_prompt,
                user_content=json.dumps(critic_input, ensure_ascii=False, indent=2),
                temperature=self.config.temperature_critic,
            )

            try:
                critic_json = self.client.extract_json(critic_raw)
            except Exception:
                critic_json = {"is_valid": False, "should_revise": False}

            if isinstance(critic_json, dict) and critic_json.get("final_json_if_small_fix"):
                return critic_json["final_json_if_small_fix"]

            if isinstance(critic_json, dict) and critic_json.get("should_revise"):
                revision_prompt = {
                    "original_payload": payload,
                    "draft_output": draft,
                    "critic_feedback": critic_json,
                }
                draft = self._chat(
                    model=self.config.planner_model,
                    system_prompt=system_prompt_planner
                    + "\n\nAdditional instructions from critic:\n" 
                    + critic_json.get("revision_instructions", ""),
                    user_content=json.dumps(revision_prompt, ensure_ascii=False, indent=2),
                    temperature=self.config.temperature_planner,
                )

        return self.client.extract_json(draft)

    # ---------- 4. 规划：plan_with_skills ----------

    def plan_with_skills(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        system_prompt_planner = """You are the main planner of a self-improving meta-agent.

You receive:
- task_spec: description of what needs to be done
- runtime_ctx: current context/state
- memory_context: relevant mid/long-term memories
- available_skills: tools/functions that can be invoked

Your job:
- Break the task into a small number of clear steps.
- Each step can optionally call one of the available skills (or be a simple internal reasoning step).
- When using a skill, you MUST specify `skill_id` and `skill_params`.

Return JSON ONLY with the following structure:
{
  "steps": [
    {
      "id": "string",
      "description": "string",
      "skill_id": "string or null",
      "skill_params": { ... } or null
    }
  ],
  "notes": "string"
}

No extra keys, no extra commentary.
"""
        user_content = json.dumps(payload, ensure_ascii=False, indent=2)

        draft = self._chat(
            model=self.config.planner_model,
            system_prompt=system_prompt_planner,
            user_content=user_content,
            temperature=self.config.temperature_planner,
        )

        if self.config.critic_model:
            critic_prompt = """You are a planning critic.

Given a task planning JSON, check:
- Are the steps logically ordered and sufficient?
- Are skill calls sensible and parameters plausible?
- Are there obvious missing safety checks or validation steps?

Return JSON ONLY:
{
  "is_ok": bool,
  "issues": ["..."],
  "suggested_changes": "string (instructions to improve the plan)"
}"""
            critic_input = {
                "planner_payload": payload,
                "draft_plan": draft,
            }
            critic_raw = self._chat(
                model=self.config.critic_model,
                system_prompt=critic_prompt,
                user_content=json.dumps(critic_input, ensure_ascii=False, indent=2),
                temperature=self.config.temperature_critic,
            )

            try:
                critic_json = self.client.extract_json(critic_raw)
            except Exception:
                critic_json = {"is_ok": True, "issues": []}

            if isinstance(critic_json, dict) and not critic_json.get("is_ok", True):
                revision_prompt = {
                    "planner_payload": payload,
                    "draft_plan": draft,
                    "critic_feedback": critic_json,
                }
                draft = self._chat(
                    model=self.config.planner_model,
                    system_prompt=system_prompt_planner
                    + "\nPlease revise the plan using the critic_feedback.",
                    user_content=json.dumps(revision_prompt, ensure_ascii=False, indent=2),
                    temperature=self.config.temperature_planner,
                )

        return self.client.extract_json(draft)

    @classmethod
    def from_env(cls) -> "CouncilRuntime":
        planner_model = os.getenv("COUNCIL_PLANNER_MODEL") or os.getenv("LLM_MODEL")
        if not planner_model:
             raise ValueError("Environment variable LLM_MODEL or COUNCIL_PLANNER_MODEL must be set.")
        critic_model = os.getenv("COUNCIL_CRITIC_MODEL") or os.getenv("LLM_MODEL_CRITIC")
        referee_model = os.getenv("COUNCIL_REFEREE_MODEL")

        cfg = CouncilConfig(
            planner_model=planner_model,
            critic_model=critic_model,
            referee_model=referee_model,
        )
        client = OllamaChatClient()
        return cls(client=client, config=cfg)


council = CouncilRuntime.from_env()
