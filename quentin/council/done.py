# quentin/council/done.py
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Dict, Optional
import logging
import os
from datetime import datetime, timezone

from quentin.council.manager import CouncilManager, CouncilQuestion, CouncilDecision
from quentin.kernel.audit import AuditEvent, default_audit_logger

logger = logging.getLogger(__name__)


@dataclass
class DoneDecision:
    """
    对一个 goal 是否“完成”的判断。
    - is_done   : 是否可以认为完成
    - verdict   : 来自 council 的原始 verdict
    - reason    : 关键理由
    - raw       : 完整 CouncilDecision（方便后续分析）
    """
    is_done: bool
    verdict: str
    reason: str
    raw: CouncilDecision

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["raw"] = self.raw.to_dict()
        return d


class CouncilQualityError(RuntimeError):
    pass


class DoneCouncil:
    """
    使用 CouncilManager 的 Definition-of-Done 封装。

    使用方式：
    done_council = DoneCouncil(council_manager)
    decision = done_council.assess(goal, exec_summary, metrics)
    """

    def __init__(self, council_manager: Optional[CouncilManager] = None, memory_fabric: Optional[Any] = None) -> None:
        self.council_manager = council_manager or CouncilManager()
        self.memory_fabric = memory_fabric

    def assess(
        self,
        *,
        goal: Any,
        execution_summary: Dict[str, Any],
        metrics: Dict[str, Any],
        importance: str = "normal",
    ) -> DoneDecision:
        """
        让 'done' council 决定目标是否已经完成。
        - goal               : Goal 对象或 dict
        - execution_summary  : 当前执行的结构化总结（CognitiveLoop 写的）
        - metrics            : 某些关键指标（成功率、错误数、cost 等）
        """
        goal_dict: Dict[str, Any]
        if isinstance(goal, dict):
            goal_dict = goal
        else:
            goal_dict = {}
            for attr in ("id", "title", "description", "domain", "metadata"):
                if hasattr(goal, attr):
                    goal_dict[attr] = getattr(goal, attr)

        enabled = os.getenv("QUENTIN_DONE_COUNCIL_ENABLED", "1").strip().lower() in {"1", "true", "yes", "on"}
        if not enabled:
            verdict, is_done, reason = self._heuristic_done_without_council(
                execution_summary=execution_summary,
                metrics=metrics,
            )
            return DoneDecision(
                is_done=is_done,
                verdict=verdict,
                reason=reason,
                raw=CouncilDecision(
                    council_name="done",
                    topic="done_check",
                    final={"verdict": verdict, "reasoning": reason, "is_done": is_done},
                    member_replies=[],
                    arbiter_raw=None,
                    created_at=datetime.now(timezone.utc).isoformat(),
                ),
            )

        payload = {
            "goal": goal_dict,
            "execution_summary": execution_summary,
            "metrics": metrics,
        }
        decision = self.council_manager.run_council(
            "done",
            self._build_question(payload=payload, importance=importance, strict_reasoning=False),
        )

        verdict = str(decision.final.get("verdict", "undecided"))
        reason = str(decision.final.get("reasoning") or "").strip()
        verdict, is_done = self._resolve_done_from_final(decision.final, fallback_verdict=verdict)

        if (not is_done) and self._is_weak_reasoning(reason):
            self._audit_quality_event(
                phase="weak_reasoning_detected",
                payload={"verdict": verdict, "reasoning": reason[:240]},
            )
            
            # P4-B: Anti-pattern memory injection
            if self.memory_fabric:
                try:
                    from quentin.memory.models import MemoryTier
                    self.memory_fabric.remember_atomic(
                        content=f"ANTI-PATTERN: Task was not marked done because model returned weak reasoning: '{reason[:100]}...'",
                        source="done_council:anti_pattern",
                        tier=MemoryTier.STS,
                        importance=0.6,
                        tags=["anti_pattern", "weak_reasoning"]
                    )
                except Exception: pass

            retry = self.council_manager.run_council(
                "done",
                self._build_question(payload=payload, importance=importance, strict_reasoning=True),
            )
            retry_reason = str(retry.final.get("reasoning") or "").strip()
            retry_verdict = str(retry.final.get("verdict") or verdict)
            retry_verdict, retry_is_done = self._resolve_done_from_final(retry.final, fallback_verdict=retry_verdict)
            if not self._is_weak_reasoning(retry_reason):
                self._audit_quality_event(
                    phase="retry_improved",
                    payload={"verdict": retry_verdict, "reasoning": retry_reason[:240]},
                )
                decision = retry
                reason = retry_reason
                verdict = retry_verdict
                is_done = retry_is_done
            else:
                fallback_reason = self._derive_evidence_reason(
                    execution_summary=execution_summary,
                    metrics=metrics,
                )
                self._audit_quality_event(
                    phase="fallback_reason_applied",
                    payload={"fallback_reason": fallback_reason[:240]},
                )
                reason = f"council_quality_fallback: {fallback_reason}"
                strict = os.getenv("QUENTIN_DONE_COUNCIL_STRICT_REASONING", "0").strip().lower() in {"1", "true", "yes", "on"}
                strict_raise = os.getenv("QUENTIN_DONE_COUNCIL_STRICT_RAISE", "0").strip().lower() in {"1", "true", "yes", "on"}
                if strict and strict_raise:
                    raise CouncilQualityError("Done council returned non-completion verdict without actionable reasoning.")

        return DoneDecision(
            is_done=is_done,
            verdict=verdict,
            reason=reason,
            raw=decision,
        )

    @staticmethod
    def _build_question(*, payload: Dict[str, Any], importance: str, strict_reasoning: bool) -> CouncilQuestion:
        prompt = (
            "Decide whether the given goal can be considered sufficiently done.\n"
            "CRITICAL RULES:\n"
            "0. RESPONSE JSON: final must include keys: verdict, reasoning, is_done.\n"
            "   - verdict must be one of: done, not_done, undecided.\n"
            "   - is_done must be a boolean and must match verdict.\n"
            "1. STATE VERIFICATION: You must base your verdict on the REAL STATE of the system as shown in 'execution_summary', not just your intent.\n"
            "2. MANDATORY EVIDENCE: Your 'reasoning' MUST cite at least one piece of concrete evidence from a tool output (e.g., specific file content read, successful command exit code, or verify_system report).\n"
            "3. TEST EVIDENCE REQUIREMENT: If the task involved modifying or creating code, you MUST see evidence of a 'pytest' or 's_test' run with 'green' results. Without test evidence, the task is NOT done.\n"
            "4. INTENT VS STATE: Even if you intended to save a file, if the last 'fs_write_file' call returned an error or was blocked by SafetyKernel, the task is NOT done.\n"
            "\nYou must consider:\n"
            "- Whether the execution summary satisfies the goal.\n"
            "- Whether the metrics are above acceptable thresholds.\n"
            "- Whether further iterations are likely to improve outcome significantly.\n"
        )
        if strict_reasoning:
            prompt += (
                "\nSTRICT QUALITY RULE:\n"
                "If verdict is not done/complete, reasoning MUST cite concrete evidence from execution_summary or metrics "
                "(for example: failed verification command, missing artifact, specific error text, unmet criteria). "
                "Do not return empty reasoning or generic text like 'no reasoning'."
            )
        return CouncilQuestion(
            topic="done_check",
            importance=importance,
            prompt=prompt,
            payload=payload,
        )

    @staticmethod
    def _is_weak_reasoning(reason: str) -> bool:
        r = str(reason or "").strip().lower()
        if not r:
            return True
        weak_markers = {
            "no reasoning",
            "n/a",
            "unknown",
            "insufficient",
            "not sure",
            "unclear",
        }
        if r in weak_markers:
            return True
        return len(r) < 12

    @staticmethod
    def _resolve_done_from_final(final: Dict[str, Any], fallback_verdict: str = "undecided") -> tuple[str, bool]:
        verdict = str(final.get("verdict") or fallback_verdict or "undecided").strip()
        v_lower = verdict.lower()
        if any(x in v_lower for x in ["reject", "redo", "continue", "not_done", "not done", "incomplete"]):
            return "not_done", False
        if any(x in v_lower for x in ["approve", "accept", "done", "complete"]):
            return "done", True

        bool_hint = DoneCouncil._parse_bool_like(final.get("is_done"))
        if bool_hint is None:
            bool_hint = DoneCouncil._parse_bool_like(final.get("done"))
        if bool_hint is not None:
            return ("done" if bool_hint else "not_done"), bool_hint
        return "undecided", False

    @staticmethod
    def _parse_bool_like(value: Any) -> Optional[bool]:
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return bool(value)
        if isinstance(value, str):
            v = value.strip().lower()
            if v in {"1", "true", "yes", "y", "done", "complete"}:
                return True
            if v in {"0", "false", "no", "n", "not_done", "not done", "incomplete"}:
                return False
        return None

    @staticmethod
    def _derive_evidence_reason(*, execution_summary: Dict[str, Any], metrics: Dict[str, Any]) -> str:
        final_output = str(execution_summary.get("final_output") or "").strip()
        actions_summary = str(execution_summary.get("actions_summary") or "").strip()
        logs_excerpt = str(execution_summary.get("logs_excerpt") or "").strip()
        if final_output and any(k in final_output.lower() for k in ("error", "failed", "exception", "timeout")):
            return f"final_output indicates failure: {final_output[:180]}"
        if actions_summary and any(k in actions_summary.lower() for k in ("error", "failed", "denied", "blocked")):
            return f"actions_summary indicates unresolved issues: {actions_summary[:180]}"
        if logs_excerpt:
            return f"logs_excerpt shows incomplete execution context: {logs_excerpt[:180]}"
        if metrics:
            return "metrics do not indicate reliable completion state"
        return "non-completion decision lacked verifiable evidence"

    @staticmethod
    def _heuristic_done_without_council(*, execution_summary: Dict[str, Any], metrics: Dict[str, Any]) -> tuple[str, bool, str]:
        final_output = str(execution_summary.get("final_output") or "").strip()
        actions_summary = str(execution_summary.get("actions_summary") or "").strip()
        logs_excerpt = str(execution_summary.get("logs_excerpt") or "").strip()
        combined = "\n".join(x for x in (final_output, actions_summary, logs_excerpt) if x).lower()
        failure_markers = ("error", "failed", "exception", "timeout", "blocked", "denied", "missing")
        if any(marker in combined for marker in failure_markers):
            return "not_done", False, DoneCouncil._derive_evidence_reason(
                execution_summary=execution_summary,
                metrics=metrics,
            )
        attempt_count = int(metrics.get("total_attempts", 0) or 0) if isinstance(metrics, dict) else 0
        if final_output or actions_summary or attempt_count > 0:
            return "done", True, "done_council_disabled: accepted via heuristic execution evidence"
        return "undecided", False, "done_council_disabled: insufficient execution evidence"

    @staticmethod
    def _audit_quality_event(*, phase: str, payload: Dict[str, Any]) -> None:
        try:
            default_audit_logger().append(
                AuditEvent(
                    action_id=f"done_council_quality::{phase}",
                    event_type="done_council_quality",
                    phase=phase,
                    actor="done_council",
                    payload=dict(payload or {}),
                )
            )
        except Exception:
            pass
