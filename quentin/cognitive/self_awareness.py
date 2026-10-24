import logging
from collections import deque
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Any, Deque, Dict, List, Optional

from quentin.llm.failover import classify_failover_reason

logger = logging.getLogger(__name__)


@dataclass
class SelfAwarenessSnapshot:
    status: str
    failure_rate: float
    total_attempts: int
    error_attempts: int
    consecutive_system_errors: int
    degrade_mode: bool
    self_programming_enabled: bool
    last_error: str
    failover_reason: Optional[str]
    anti_pattern_reason: Optional[str]
    recent_failover_reasons: List[str]
    consecutive_no_progress: int
    suggested_actions: List[str]
    generated_at: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class SelfAwarenessEngine:
    """
    Runtime self-awareness aggregator.

    It converts low-level execution outcomes into a compact status snapshot
    that can be injected into planner/executor prompts.
    """

    def __init__(self, *, reason_window: int = 5) -> None:
        self._reason_window = max(1, int(reason_window))
        self._recent_failover_reasons: Deque[str] = deque(maxlen=self._reason_window)
        self._consecutive_system_errors = 0
        self._consecutive_no_progress = 0
        self._last_error = ""
        self._last_snapshot: Optional[SelfAwarenessSnapshot] = None

    def current_snapshot(self) -> SelfAwarenessSnapshot:
        if self._last_snapshot is not None:
            return self._last_snapshot
        return SelfAwarenessSnapshot(
            status="healthy",
            failure_rate=0.0,
            total_attempts=0,
            error_attempts=0,
            consecutive_system_errors=0,
            degrade_mode=False,
            self_programming_enabled=True,
            last_error="",
            failover_reason=None,
            anti_pattern_reason=None,
            recent_failover_reasons=[],
            consecutive_no_progress=0,
            suggested_actions=[],
            generated_at=datetime.now(timezone.utc).isoformat(),
        )

    def observe_attempt(
        self,
        *,
        exec_result: Dict[str, Any],
        metrics: Dict[str, Any],
        degrade_mode: bool,
        self_programming_enabled: bool,
    ) -> SelfAwarenessSnapshot:
        is_system_error = bool(exec_result.get("is_system_error"))
        anti_pattern_reason = self._extract_anti_pattern_reason(exec_result)
        no_progress = self._is_no_progress_attempt(exec_result)
        error_text = self._extract_error_text(exec_result)
        
        # P3.1: Split "format salvage" from "execution failure"
        failover_reason = classify_failover_reason(error_text) if error_text else None
        
        # If execution was actually successful, don't let 'format' noise trigger failover status
        if not is_system_error and not error_text and exec_result.get("final_output"):
            if failover_reason == "format":
                logger.info("SelfAwareness: Ignoring 'format' failover reason because execution succeeded.")
                failover_reason = None

        if is_system_error:
            self._consecutive_system_errors += 1
        else:
            self._consecutive_system_errors = 0
        if no_progress:
            self._consecutive_no_progress += 1
        else:
            self._consecutive_no_progress = 0

        if error_text:
            self._last_error = error_text
        if failover_reason:
            self._recent_failover_reasons.append(failover_reason)

        total_attempts = int(metrics.get("total_attempts", 0) or 0)
        error_attempts = int(metrics.get("error_attempts", 0) or 0)
        failure_rate = (error_attempts / total_attempts) if total_attempts > 0 else 0.0
        status = self._infer_status(
            failure_rate=failure_rate,
            total_attempts=total_attempts,
            has_error=bool(error_text),
            is_system_error=is_system_error,
            anti_pattern_reason=anti_pattern_reason,
            consecutive_no_progress=self._consecutive_no_progress,
        )
        suggested_actions = self._suggest_actions(
            failover_reason=failover_reason,
            status=status,
            is_system_error=is_system_error,
            anti_pattern_reason=anti_pattern_reason,
            consecutive_no_progress=self._consecutive_no_progress,
        )

        snapshot = SelfAwarenessSnapshot(
            status=status,
            failure_rate=failure_rate,
            total_attempts=total_attempts,
            error_attempts=error_attempts,
            consecutive_system_errors=self._consecutive_system_errors,
            degrade_mode=degrade_mode,
            self_programming_enabled=self_programming_enabled,
            last_error=self._last_error,
            failover_reason=failover_reason,
            anti_pattern_reason=anti_pattern_reason,
            recent_failover_reasons=list(self._recent_failover_reasons),
            consecutive_no_progress=self._consecutive_no_progress,
            suggested_actions=suggested_actions,
            generated_at=datetime.now(timezone.utc).isoformat(),
        )
        self._last_snapshot = snapshot
        return snapshot

    @staticmethod
    def _extract_error_text(exec_result: Dict[str, Any]) -> str:
        if not isinstance(exec_result, dict):
            return ""
        raw = exec_result.get("raw")
        if isinstance(raw, dict):
            value = raw.get("error")
            if value:
                return str(value).strip()
            steps = raw.get("steps") if isinstance(raw.get("steps"), list) else []
            for step in steps:
                if not isinstance(step, dict):
                    continue
                result = step.get("result")
                if isinstance(result, dict):
                    if result.get("error"):
                        return str(result.get("error")).strip()
                    tool_result = result.get("tool_result")
                    if isinstance(tool_result, dict) and tool_result.get("error"):
                        return str(tool_result.get("error")).strip()
                    tail = result.get("feedback_tail")
                    if isinstance(tail, list):
                        for fb in reversed(tail):
                            if not isinstance(fb, dict):
                                continue
                            tool_result = fb.get("tool_result")
                            if isinstance(tool_result, dict) and tool_result.get("error"):
                                return str(tool_result.get("error")).strip()
            value = raw.get("error")
            if value:
                return str(value).strip()
        actions_summary = exec_result.get("actions_summary")
        if isinstance(actions_summary, str) and "error" in actions_summary.lower():
            return actions_summary.strip()[:500]
        return ""

    @staticmethod
    def _extract_anti_pattern_reason(exec_result: Dict[str, Any]) -> Optional[str]:
        def _detect_cmd(cmd: str) -> Optional[str]:
            text = str(cmd or "").strip().lower()
            if not text:
                return None
            parts = text.split()
            base = parts[0].split("/")[-1] if parts else ""
            if base in {"nano", "vim", "vi", "emacs"} or " nano " in f" {text} ":
                return "interactive_editor_command"
            if ("wget " in text or "curl " in text) and ("github.com" in text or "releases/" in text):
                return "guessed_download_command"
            return None

        if not isinstance(exec_result, dict):
            return None
        raw = exec_result.get("raw")
        if not isinstance(raw, dict):
            return None
        steps = raw.get("steps") if isinstance(raw.get("steps"), list) else []
        for step in steps:
            if not isinstance(step, dict):
                continue
            result = step.get("result")
            if not isinstance(result, dict):
                continue
            if str(result.get("error") or "") == "repeated_tool_call_loop":
                return "repeated_tool_call_loop"
            call_tool = result.get("call_tool")
            if isinstance(call_tool, dict):
                args = call_tool.get("args") if isinstance(call_tool.get("args"), dict) else {}
                cmd = str(args.get("command") or "").strip().lower()
                if cmd:
                    reason = _detect_cmd(cmd)
                    if reason:
                        return reason
            tail = result.get("feedback_tail")
            if isinstance(tail, list):
                for fb in tail:
                    if not isinstance(fb, dict):
                        continue
                    tool_call = fb.get("tool_call") if isinstance(fb.get("tool_call"), dict) else {}
                    args = tool_call.get("args") if isinstance(tool_call.get("args"), dict) else {}
                    cmd = str(args.get("command") or "").strip().lower()
                    if not cmd:
                        continue
                    reason = _detect_cmd(cmd)
                    if reason:
                        return reason
        return None

    @staticmethod
    def _is_no_progress_attempt(exec_result: Dict[str, Any]) -> bool:
        if not isinstance(exec_result, dict):
            return False
        final_output = str(exec_result.get("final_output") or "").strip()
        if len(final_output) >= 16:
            return False
        raw = exec_result.get("raw")
        if not isinstance(raw, dict):
            return False
        steps = raw.get("steps")
        if not isinstance(steps, list) or not steps:
            return False
        for step in steps:
            if not isinstance(step, dict):
                continue
            result = step.get("result")
            if not isinstance(result, dict):
                continue
            if result.get("tool_result") is not None or result.get("call_tool") is not None:
                return True
            tail = result.get("feedback_tail")
            if isinstance(tail, list) and tail:
                return True
        return False

    @staticmethod
    def _infer_status(
        *,
        failure_rate: float,
        total_attempts: int,
        has_error: bool,
        is_system_error: bool,
        anti_pattern_reason: Optional[str],
        consecutive_no_progress: int,
    ) -> str:
        if is_system_error:
            return "critical"
        if anti_pattern_reason:
            return "warning"
        if consecutive_no_progress >= 3:
            return "critical"
        if consecutive_no_progress >= 2:
            return "warning"
        if total_attempts >= 3 and failure_rate >= 0.8:
            return "critical"
        if has_error:
            return "warning"
        if total_attempts >= 2 and failure_rate >= 0.5:
            return "warning"
        return "healthy"

    def _suggest_actions(
        self,
        *,
        failover_reason: Optional[str],
        status: str,
        is_system_error: bool,
        anti_pattern_reason: Optional[str],
        consecutive_no_progress: int,
    ) -> List[str]:
        actions: List[str] = []
        if failover_reason == "rate_limit":
            actions.append("rotate_auth_profile_or_fallback_model")
        elif failover_reason == "billing":
            actions.append("disable_current_profile_and_switch_provider")
        elif failover_reason == "auth":
            actions.append("refresh_or_switch_credentials")
        elif failover_reason == "timeout":
            actions.append("reduce_scope_and_retry")
        elif failover_reason == "format":
            actions.append("simplify_output_schema_or_use_tool_friendly_model")
        elif failover_reason == "context_overflow":
            actions.append("trigger_compaction_and_trim_context")

        if anti_pattern_reason == "interactive_editor_command":
            actions.append("switch_to_fs_read_and_write_flow")
        elif anti_pattern_reason == "guessed_download_command":
            actions.append("stop_guessing_urls_and_use_local_or_user_provided_artifacts")
        elif anti_pattern_reason == "repeated_tool_call_loop":
            actions.append("change_tool_or_parameters_immediately")
            actions.append("run_diagnostic_probes_pwd_id_ls_then_check_write_policy")
        if consecutive_no_progress >= 2:
            actions.append("force_user_visible_progress_or_finish")
        if is_system_error:
            actions.append("stop_repeating_same_path_and_change_strategy")
        if self._consecutive_system_errors >= 2:
            actions.append("escalate_to_reflection_or_abort")
        if status == "critical":
            actions.append("emit_user_visible_health_warning")
        return actions

    @staticmethod
    def to_prompt_hint(snapshot: SelfAwarenessSnapshot) -> str:
        parts: List[str] = [
            f"Self-awareness status={snapshot.status}",
            f"failure_rate={snapshot.failure_rate:.2f}",
            f"consecutive_system_errors={snapshot.consecutive_system_errors}",
            f"consecutive_no_progress={snapshot.consecutive_no_progress}",
        ]
        if snapshot.failover_reason:
            parts.append(f"failover_reason={snapshot.failover_reason}")
        if snapshot.anti_pattern_reason:
            parts.append(f"anti_pattern_reason={snapshot.anti_pattern_reason}")
        if snapshot.last_error:
            parts.append(f"last_error={snapshot.last_error[:160]}")
        if snapshot.suggested_actions:
            parts.append("actions=" + ", ".join(snapshot.suggested_actions[:3]))
        return "; ".join(parts)
