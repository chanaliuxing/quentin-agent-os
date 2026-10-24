from __future__ import annotations

import logging
import os
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger(__name__)

from meta_agent.skills.manager import SkillManager
from meta_agent.skills.schema import SkillDefinition, SkillImplType, SkillStatus

class SkillExecutor:
    def __init__(
        self,
        *,
        skill_manager: Optional[SkillManager] = None,
        builtins: Optional[Dict[str, Callable[[Dict[str, Any], Dict[str, Any]], Dict[str, Any]]]] = None,
    ) -> None:
        self.skill_manager = skill_manager or SkillManager()
        self._builtins = builtins or {
            "builtin/echo": self._builtin_echo,
        }

    def execute(
        self, skill_id: str, inputs: Dict[str, Any], task_context: Dict[str, Any]
    ) -> Dict[str, Any]:
        if not skill_id:
            raise ValueError("skill_id is required")

        builtin = self._builtins.get(skill_id)
        if builtin:
            return builtin(inputs, task_context)

        skill = self.skill_manager.get(skill_id)
        if not skill:
            return {"status": "error", "error": f"skill_not_found: {skill_id}"}
        if skill.status != SkillStatus.ACTIVE:
            return {"status": "error", "error": f"skill_not_active: {skill_id}", "skill_status": skill.status}

        outcome: Dict[str, Any]
        try:
            if skill.impl_type == SkillImplType.LLM_PROMPT:
                outcome = self._execute_llm_prompt(skill, inputs, task_context)
                return outcome
            if skill.impl_type == SkillImplType.PYTHON_CODE:
                if os.getenv("ENABLE_SKILL_PYTHON_CODE", "0").lower() not in {"1", "true", "yes"}:
                    outcome = {"status": "error", "error": "python_code_skill_disabled"}
                    return outcome
                outcome = self._execute_python_code(skill, inputs, task_context)
                return outcome
            if skill.impl_type == SkillImplType.WORKFLOW_REF:
                outcome = {"status": "error", "error": "workflow_ref_not_supported_yet"}
                return outcome
            outcome = {"status": "error", "error": f"unknown_impl_type: {skill.impl_type}"}
            return outcome
        finally:
            # Best-effort usage recording.
            try:
                success = False
                if isinstance(locals().get("outcome"), dict):
                    success = str(locals()["outcome"].get("status") or "").lower() == "ok"
                self.skill_manager.record_usage(skill_id, success=success)
            except Exception:
                pass

    def _builtin_echo(self, inputs: Dict[str, Any], task_context: Dict[str, Any]) -> Dict[str, Any]:
        return {"status": "ok", "output": {"inputs": inputs, "task_context": task_context}}

    def _execute_llm_prompt(
        self, skill: SkillDefinition, inputs: Dict[str, Any], task_context: Dict[str, Any]
    ) -> Dict[str, Any]:
        prompt = skill.impl_payload.get("prompt") or skill.impl_payload.get("template") or ""
        if not isinstance(prompt, str):
            prompt = str(prompt)

        render_ctx = {"inputs": inputs, "task": task_context, "skill": skill.to_dict()}
        try:
            rendered = prompt.format(**render_ctx)
        except Exception:
            rendered = prompt

        try:
            from quentin.llm.client import call_llm
        except Exception:
            return {"status": "error", "error": "llm_client_unavailable"}

        model_name = os.getenv("LLM_MODEL")
        if not model_name:
             raise ValueError("Environment variable LLM_MODEL is not set.")
        out = call_llm(
            model_name,
            user_prompt=rendered,
            system_prompt=str(skill.impl_payload.get("system_prompt") or ""),
            provider=skill.impl_payload.get("provider"),
            model_name=skill.impl_payload.get("model") or model_name,
            auth_profile_id=skill.impl_payload.get("auth_profile_id"),
            auth_store_path=skill.impl_payload.get("auth_store_path"),
            reserve_tokens=int(skill.impl_payload.get("reserve_tokens") or 0),
            action_metadata={"topic": "skill_executor_llm_prompt", "skill_id": skill.skill_id},
        )
        return {"status": "ok", "output": out}

    def _execute_python_code(
        self, skill: SkillDefinition, inputs: Dict[str, Any], task_context: Dict[str, Any]
    ) -> Dict[str, Any]:
        code = skill.impl_payload.get("code") or ""
        if not isinstance(code, str):
            return {"status": "error", "error": "invalid_python_code_payload"}

        # Minimal, opt-in execution environment.
        glb: Dict[str, Any] = {"__builtins__": {"len": len, "min": min, "max": max, "sum": sum}}
        loc: Dict[str, Any] = {}
        exec(code, glb, loc)
        fn = loc.get("run") or glb.get("run")
        if not callable(fn):
            return {"status": "error", "error": "python_code_missing_run"}
        return {"status": "ok", "output": fn(inputs, task_context)}
