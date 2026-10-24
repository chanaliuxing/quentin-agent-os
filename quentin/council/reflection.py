# quentin/council/reflection.py
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Optional
import logging
import json
import os
from pathlib import Path

from quentin.council.manager import CouncilManager, CouncilQuestion, CouncilDecision
from quentin.cognitive.phase_payloads import build_phase_payload
from quentin.cognitive.prompt_factory import RuntimeInfo, build_system_prompt
from quentin.infra.llm.error_classifier import error_classifier

logger = logging.getLogger(__name__)


@dataclass
class ReflectionAdvice:
    """
    多 AI 反省后的建议。

    约定：
    - action:
        - "retry"           : 建议继续重试当前 goal（可以结合 new_plan 使用）
        - "abort"           : 建议停止本 goal
        - "adjust_goal"     : 建议调整目标（例如降低难度/范围）
        - "request_skill"   : 建议引入/实现新的技能
        - "other"           : 其他情况
    - new_plan        : 若提供，替代旧的 plan（结构与 PlannerResult.steps 兼容）
    - goal_adjustment : 对 goal 的修改建议（自然语言/结构化都可以）
    - skill_ideas     : 请求创造的新技能列表（后续可喂给 SkillManager / 自编程引擎）
    - notes           : 关键说明
    - raw             : 完整 CouncilDecision 用于 Trace / Research Layer
    """
    action: str
    new_plan: Optional[Dict[str, Any]]
    goal_adjustment: Optional[Dict[str, Any]]
    skill_ideas: List[Dict[str, Any]]
    notes: str
    raw: CouncilDecision

    @property
    def summary(self) -> str:
        # Backward-compatible alias used by some trace hooks.
        return self.notes

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["raw"] = self.raw.to_dict()
        return d
        

class ReflectionCouncil:
    """
    使用 CouncilManager 的“错误反省”封装。

    触发场景：
    - 同一个 goal 多次失败
    - 某次执行出现严重异常 / 指标异常（高 error_rate / 超预算等）
    """

    def __init__(self, council_manager: Optional[CouncilManager] = None) -> None:
        self.council_manager = council_manager or CouncilManager()

    @staticmethod
    def _env_int(name: str, default: int) -> int:
        raw = os.getenv(name)
        if raw is None:
            return default
        try:
            return int(raw)
        except Exception:
            return default

    @staticmethod
    def _truncate_text(value: Any, limit: int) -> str:
        text = str(value or "")
        if limit <= 0:
            return ""
        if len(text) <= limit:
            return text
        return text[:limit] + "...<truncated>"

    def _compact_step(self, step: Dict[str, Any], *, text_limit: int) -> Dict[str, Any]:
        return {
            "step_id": step.get("step_id"),
            "description": self._truncate_text(step.get("description"), text_limit),
            "executor_mode": step.get("executor_mode"),
            "success": bool(step.get("success")),
            "error": self._truncate_text(step.get("error"), text_limit),
            "result": self._truncate_text(step.get("result"), text_limit),
        }

    def _compact_exec_result(self, last_exec_result: Dict[str, Any]) -> Dict[str, Any]:
        max_steps = self._env_int("QUENTIN_REFLECTION_MAX_EXEC_STEPS", 8)
        text_limit = self._env_int("QUENTIN_REFLECTION_MAX_TEXT_CHARS", 320)
        raw = last_exec_result.get("raw") if isinstance(last_exec_result.get("raw"), dict) else {}
        steps = raw.get("steps") if isinstance(raw.get("steps"), list) else []
        compact_steps = [self._compact_step(s, text_limit=text_limit) for s in steps[:max_steps] if isinstance(s, dict)]
        return {
            "is_system_error": bool(last_exec_result.get("is_system_error", False)),
            "final_output": self._truncate_text(last_exec_result.get("final_output"), text_limit),
            "actions_summary": self._truncate_text(last_exec_result.get("actions_summary"), text_limit),
            "raw": {
                "success": bool(raw.get("success", False)),
                "steps": compact_steps,
                "steps_truncated": len(steps) > max_steps,
            },
        }

    def _compact_plan(self, last_plan: Dict[str, Any]) -> Dict[str, Any]:
        max_steps = self._env_int("QUENTIN_REFLECTION_MAX_PLAN_STEPS", 8)
        text_limit = self._env_int("QUENTIN_REFLECTION_MAX_TEXT_CHARS", 320)
        max_raw_chars = self._env_int("QUENTIN_REFLECTION_MAX_PLAN_RAW_CHARS", 2000)
        raw_steps = last_plan.get("steps") if isinstance(last_plan.get("steps"), list) else []
        compact_steps: List[Dict[str, Any]] = []
        for s in raw_steps[:max_steps]:
            if isinstance(s, dict):
                compact_steps.append(
                    {
                        "step_id": s.get("step_id"),
                        "description": self._truncate_text(s.get("description"), text_limit),
                        "skill_id": s.get("skill_id"),
                    }
                )
            else:
                compact_steps.append({"description": self._truncate_text(s, text_limit)})
        return {
            "steps": compact_steps,
            "steps_truncated": len(raw_steps) > max_steps,
            "raw": self._truncate_text(last_plan.get("raw"), max_raw_chars),
        }

    def _compact_recent_traces(self, recent_traces: Optional[List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
        max_traces = self._env_int("QUENTIN_REFLECTION_MAX_TRACES", 3)
        max_steps = self._env_int("QUENTIN_REFLECTION_MAX_TRACE_STEPS", 6)
        text_limit = self._env_int("QUENTIN_REFLECTION_MAX_TEXT_CHARS", 320)
        traces = recent_traces or []
        compact: List[Dict[str, Any]] = []
        for tr in traces[-max_traces:]:
            if not isinstance(tr, dict):
                continue
            steps = tr.get("steps") if isinstance(tr.get("steps"), list) else []
            compact.append(
                {
                    "attempt_index": tr.get("attempt_index"),
                    "steps": [self._compact_step(s, text_limit=text_limit) for s in steps[:max_steps] if isinstance(s, dict)],
                    "steps_truncated": len(steps) > max_steps,
                }
            )
        return compact

    def _get_recent_audit_logs(self, limit: int = 5) -> List[Dict[str, Any]]:
        """
        P5: Empirical Grounding - Fetch real tool execution status from audit log.
        """
        try:
            from quentin.diagnostics.intelligence_auditor import _read_jsonl
            repo_root = getattr(self.council_manager, "repo_root", None)
            root = Path(repo_root).resolve() if repo_root is not None else Path(".").resolve()
            audit_path = root / "data" / "audit_events.jsonl"
            all_audits = _read_jsonl(audit_path, limit=limit * 3)
            
            # Filter for meaningful action results
            relevant = []
            for a in reversed(all_audits):
                action = a.get("action", "")
                if "tool_call" in action or "guard_action" in action:
                    relevant.append({
                        "ts": a.get("ts"),
                        "action": action,
                        "decision": a.get("decision"),
                        "reason": a.get("reason"),
                        "tool": a.get("resource"),
                        "params": (a.get("metadata", {}).get("params") or {}) if isinstance(a.get("metadata"), dict) else {}
                    })
                if len(relevant) >= limit:
                    break
            return relevant
        except Exception:
            return []

    @staticmethod
    def _parse_answer_payload(answer: Any) -> Dict[str, Any]:
        if isinstance(answer, dict):
            return answer
        if not isinstance(answer, str):
            return {}
        text = answer.strip()
        if not text:
            return {}
        try:
            parsed = json.loads(text)
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            pass
        # Try extracting a JSON object from fenced/prose output.
        left = text.find("{")
        right = text.rfind("}")
        if left >= 0 and right > left:
            try:
                parsed = json.loads(text[left : right + 1])
                return parsed if isinstance(parsed, dict) else {}
            except Exception:
                pass
        # Last-resort: common single-token actions.
        token = text.lower().strip("`\"' ")
        if token in {"retry", "abort", "adjust_goal", "request_skill", "other"}:
            return {"action": token}
        return {}

    @staticmethod
    def _is_low_information_reasoning(notes: str) -> bool:
        text = str(notes or "").strip().lower()
        if not text:
            return True
        boilerplate_markers = (
            "analyze why",
            "root cause",
            "diagnose",
            "retry",
            "improved plan",
            "attempt",
        )
        if len(text) < 80:
            return True
        return sum(1 for m in boilerplate_markers if m in text) >= 2

    @staticmethod
    def _contains_known_loop_signal(compact_exec: Dict[str, Any]) -> bool:
        hay = " ".join(
            [
                str(compact_exec.get("final_output") or ""),
                str(compact_exec.get("actions_summary") or ""),
                str((compact_exec.get("raw") or {}).get("steps") or ""),
            ]
        ).lower()
        loop_markers = (
            "repeated_tool_call_loop",
            "max_step_iterations_reached",
            "no_progress_threshold_reached",
            "path is a directory",
            "is a directory",
            "missing path",
        )
        return any(m in hay for m in loop_markers)

    def _apply_stale_retry_breaker(
        self,
        *,
        action: str,
        new_plan: Optional[Dict[str, Any]],
        goal_adjustment: Optional[Dict[str, Any]],
        skill_ideas: List[Dict[str, Any]],
        notes: str,
        compact_exec: Dict[str, Any],
        failure_count: int,
    ) -> tuple[str, Optional[Dict[str, Any]], str]:
        if action != "retry":
            return action, goal_adjustment, notes
        if new_plan or goal_adjustment or skill_ideas:
            return action, goal_adjustment, notes

        stale_after = self._env_int("QUENTIN_REFLECTION_STALE_RETRY_FAILCOUNT", 3)
        abort_after = self._env_int("QUENTIN_REFLECTION_ABORT_FAILCOUNT", 6)
        if failure_count < max(1, stale_after):
            return action, goal_adjustment, notes

        if not (self._is_low_information_reasoning(notes) or self._contains_known_loop_signal(compact_exec)):
            return action, goal_adjustment, notes

        if failure_count >= max(stale_after, abort_after):
            return "abort", goal_adjustment, f"{notes} [stale_retry_breaker:forced_abort]"

        forced_adjustment = goal_adjustment or {
            "strategy": "stale_retry_breaker",
            "constraints": [
                "Do not retry identical plan steps.",
                "Use directory-safe probes (`ls`/`fs.exists`) before any file read/write on path-like targets.",
                "Generate a concretely different plan with tool-level changes.",
            ],
        }
        return "adjust_goal", forced_adjustment, f"{notes} [stale_retry_breaker:adjust_goal]"

    def reflect(
        self,
        *,
        goal: Any,
        last_plan: Dict[str, Any],
        last_exec_result: Dict[str, Any],
        metrics: Dict[str, Any],
        failure_count: int,
        attempt_evaluation: Optional[Dict[str, Any]] = None,
        importance: str = "normal",
        recent_traces: Optional[List[Dict[str, Any]]] = None,
    ) -> ReflectionAdvice:
        """
        发起一次多 AI 反省。

        - goal            : 当前目标（对象或 dict）
        - last_plan       : 上一次使用的 plan（PlannerResult 序列化的 dict）
        - last_exec_result: Executor 返回的结构化结果
        - metrics         : 本 goal 的累计/最近指标（失败次数、error_rate 等）
        - failure_count   : 当前 goal 已经失败了几轮
        - recent_traces   : 可选，最近几次执行的 Trace 摘要
        """
        goal_dict: Dict[str, Any]
        if isinstance(goal, dict):
            goal_dict = goal
        else:
            goal_dict = {}
            for attr in ("id", "title", "description", "domain", "metadata"):
                if hasattr(goal, attr):
                    goal_dict[attr] = getattr(goal, attr)

        compact_plan = self._compact_plan(last_plan if isinstance(last_plan, dict) else {})
        compact_exec = self._compact_exec_result(last_exec_result if isinstance(last_exec_result, dict) else {})
        compact_traces = self._compact_recent_traces(recent_traces)
        recent_audits = self._get_recent_audit_logs()
        
        # P5: OpenClaw Parity - Error Classification
        raw_err = last_exec_result.get("raw", {}).get("error") if isinstance(last_exec_result.get("raw"), dict) else None
        error_kind = error_classifier.classify(str(raw_err)) if raw_err else "none"
        correction_intensity = "medium"
        if isinstance(attempt_evaluation, dict):
            correction_intensity = str(attempt_evaluation.get("correction_intensity") or "medium").strip().lower() or "medium"
        phase_payload = build_phase_payload(
            phase="reflecting",
            correction_intensity=correction_intensity,
            reason="reflection_entry",
        ).to_dict()
        phase_system_prompt = build_system_prompt(
            mode="full",
            identity="You are a reflection agent in Quentin cognitive loop.",
            safety_rules=[
                "Ground all claims in actual execution/audit evidence.",
                "Explicitly separate tool execution failure from planning/logic failure.",
                "Return schema-compliant JSON under answer.",
            ],
            runtime_info=RuntimeInfo(
                agent_id="quentin-reflector",
                workspace=str(Path(getattr(self.council_manager, "repo_root", ".")).resolve()),
                os_name="unknown",
                model="reflection-council",
                extras={
                    "failure_count": str(failure_count),
                    "error_kind": str(error_kind),
                },
            ),
            phase_payload=phase_payload,
        )

        payload = {
            "goal": goal_dict,
            "last_plan": compact_plan,
            "last_execution": compact_exec,
            "error_kind": error_kind,
            "metrics": metrics,
            "failure_count": failure_count,
            "attempt_evaluation": attempt_evaluation or {},
            "recent_traces": compact_traces,
            "recent_audit_logs": recent_audits,
            "phase_payload": phase_payload,
            "phase_system_prompt": phase_system_prompt,
        }

        question = CouncilQuestion(
            topic="reflection",
            importance=importance,
            prompt=(
                "Analyze why the previous attempt(s) failed and propose a better strategy.\n"
                "You MUST:\n"
                "- diagnose the likely root causes,\n"
                "- decide what to do next (retry / abort / adjust_goal / request_skill / other),\n"
                "- if retry, optionally propose an IMPROVED PLAN compatible with the original plan schema,\n"
                "- if request_skill, describe the missing skills clearly.\n\n"
                "IMPORTANT: Cross-reference 'last_execution' with 'recent_audit_logs'. "
                "If the execution summary claims a tool call succeeded but the audit logs show it was BLOCKED or had a validation error, "
                "the agent is HALLUCINATING progress. You must identify this grounding gap as a P0 root cause.\n\n"
                "HALLUCINATION GUARD: Do NOT invent or suggest calling external URLs or third-party APIs (e.g., api.qwen.com, search.google.com) unless they are explicitly provided as available tools in the session context. "
                "The environment is isolated; you must rely on REGISTERED LOCAL TOOLS only."
            ),
            payload=payload,
        )

        decision = self.council_manager.run_council("reflection", question)

        if str(decision.final.get("verdict") or "").lower() == "all_failed":
            return ReflectionAdvice(
                action="abort",
                new_plan=None,
                goal_adjustment=None,
                skill_ideas=[],
                notes="reflection council failed at transport/model layer; aborting to avoid dead loop",
                raw=decision,
            )

        # 期望仲裁结果 final.answer 大致是：
        # {
        #   "action": "retry" | "abort" | "adjust_goal" | "request_skill" | "other",
        #   "new_plan": {...} | null,
        #   "goal_adjustment": {...} | null,
        #   "skill_ideas": [{...}, ...]
        # }
        answer = self._parse_answer_payload(decision.final.get("answer"))
        if not answer:
            # Compatibility: some arbiters return flat fields on `final` instead of nested `final.answer`.
            answer = self._parse_answer_payload(decision.final)
        if not answer:
            logger.warning("ReflectionCouncil: non-JSON answer payload, fallback to retry.")

        action = str(answer.get("action") or "retry")
        if action not in {"retry", "abort", "adjust_goal", "request_skill", "other"}:
            action = "retry"
        new_plan = answer.get("new_plan")
        goal_adjustment = answer.get("goal_adjustment")
        skill_ideas = answer.get("skill_ideas") or []
        if not isinstance(skill_ideas, list):
            skill_ideas = []

        notes = decision.final.get("reasoning") or ""
        action, goal_adjustment, notes = self._apply_stale_retry_breaker(
            action=action,
            new_plan=new_plan if isinstance(new_plan, dict) else None,
            goal_adjustment=goal_adjustment if isinstance(goal_adjustment, dict) else None,
            skill_ideas=skill_ideas,
            notes=str(notes),
            compact_exec=compact_exec,
            failure_count=failure_count,
        )

        return ReflectionAdvice(
            action=action,
            new_plan=new_plan if isinstance(new_plan, dict) else None,
            goal_adjustment=goal_adjustment if isinstance(goal_adjustment, dict) else None,
            skill_ideas=skill_ideas,
            notes=notes,
            raw=decision,
        )
