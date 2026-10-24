from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional

from quentin.kernel.policy import ActionRequest
from quentin.kernel.safety import SafetyKernel
from quentin.kernel.taxonomy import ACTION_STORAGE_WRITE, RISK_LOW, DOMAIN_CORE, ENV_SANDBOX
from quentin.memory.models import MemoryTier
from quentin.infra.sessions.dirty_sync import dirty_sync
from quentin.infra.sessions.session_store import SessionStore


@dataclass
class SessionDeltaConfig:
    enabled: bool = False
    throttle_seconds: float = 5.0
    min_events: int = 1
    max_chars: int = 800
    allow_in_prod: bool = False
    importance: float = 0.2
    delta_bytes: int = 512
    delta_messages: int = 4

    @classmethod
    def from_env(cls) -> "SessionDeltaConfig":
        enabled = os.getenv("QUENTIN_SESSION_DELTAS", "").strip().lower() in ("1", "true", "yes", "on")
        allow_in_prod = os.getenv("QUENTIN_SESSION_DELTAS_ALLOW_PROD", "").strip().lower() in ("1", "true", "yes", "on")
        try:
            throttle_seconds = float(os.getenv("QUENTIN_SESSION_DELTAS_THROTTLE_SEC", "5"))
        except Exception:
            throttle_seconds = 5.0
        try:
            min_events = int(os.getenv("QUENTIN_SESSION_DELTAS_MIN_EVENTS", "1"))
        except Exception:
            min_events = 1
        try:
            max_chars = int(os.getenv("QUENTIN_SESSION_DELTAS_MAX_CHARS", "800"))
        except Exception:
            max_chars = 800
        try:
            importance = float(os.getenv("QUENTIN_SESSION_DELTAS_IMPORTANCE", "0.2"))
        except Exception:
            importance = 0.2
        try:
            delta_bytes = int(
                os.getenv(
                    "QUENTIN_SESSION_DELTAS_DELTA_BYTES",
                    os.getenv("QUENTIN_DIRTY_BYTE_THRESHOLD", "512"),
                )
            )
        except Exception:
            delta_bytes = 512
        try:
            delta_messages = int(os.getenv("QUENTIN_SESSION_DELTAS_DELTA_MESSAGES", "4"))
        except Exception:
            delta_messages = 4
        return cls(
            enabled=enabled,
            throttle_seconds=throttle_seconds,
            min_events=min_events,
            max_chars=max_chars,
            allow_in_prod=allow_in_prod,
            importance=importance,
            delta_bytes=delta_bytes,
            delta_messages=delta_messages,
        )


class SessionDeltaWriter:
    def __init__(
        self,
        *,
        memory_fabric: Any,
        safety_kernel: Optional[SafetyKernel] = None,
        config: Optional[SessionDeltaConfig] = None,
        session_store: Optional[SessionStore] = None,
    ) -> None:
        self.memory_fabric = memory_fabric
        self.safety_kernel = safety_kernel or SafetyKernel()
        self.config = config or SessionDeltaConfig.from_env()
        self.session_store = session_store
        self._last_write_ts: Dict[str, float] = {}
        self._pending_counts: Dict[str, int] = {}
        self._pending_bytes: Dict[str, int] = {} # P5: DirtyTracker
        self._pending_messages: Dict[str, int] = {}
        self._blocked_sessions: Dict[str, bool] = {}

    def observe_execution(
        self,
        *,
        session_id: str,
        trace_id: str,
        attempt_index: int,
        task_domain: str,
        task_environment: str,
        plan_summary: str,
        actions_summary: str,
        final_output: str,
        extra_metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        if not self.config.enabled:
            return
        if task_environment == "prod" and not self.config.allow_in_prod:
            return
        if self._blocked_sessions.get(session_id):
            return

        now = time.monotonic()
        last_ts = self._last_write_ts.get(session_id, 0.0)
        
        # Calculate delta bytes
        content_len = len(plan_summary) + len(actions_summary) + len(final_output)
        self._pending_bytes[session_id] = self._pending_bytes.get(session_id, 0) + content_len
        self._pending_counts[session_id] = self._pending_counts.get(session_id, 0) + 1
        self._pending_messages[session_id] = self._pending_messages.get(session_id, 0) + 1
        
        # P5: Surgery Twenty-one - Debounced Process Sync
        # Push to dirty_sync so even if the full loop doesn't finish, we have the state.
        session_state_path = ""
        session_state_version = 0
        if self.session_store is not None:
            try:
                state = self.session_store.load_or_create(session_id)
                state.metadata["last_trace_id"] = trace_id
                state.metadata["last_attempt_index"] = int(attempt_index)
                state.deltas_cursor["pending_bytes"] = int(self._pending_bytes.get(session_id, 0))
                state.deltas_cursor["pending_messages"] = int(self._pending_messages.get(session_id, 0))
                state.deltas_cursor["pending_events"] = int(self._pending_counts.get(session_id, 0))
                state.dirty_flags["session_delta"] = True
                state.touch()
                state = self.session_store.save(state)
                session_state_path = str(self.session_store.state_file_path(session_id))
                session_state_version = int(state.version)
            except Exception:
                pass
        dirty_sync.track_change(
            session_id,
            {
                "plan_summary": plan_summary,
                "actions_summary": actions_summary,
                "final_output": final_output,
                "executed_skill_ids": extra_metadata.get("executed_skill_ids", []) if extra_metadata else [],
                "session_state_path": session_state_path,
                "session_state_version": session_state_version,
            },
        )
        
        byte_threshold = max(1, int(self.config.delta_bytes))
        message_threshold = max(1, int(self.config.delta_messages))
        
        if last_ts <= 0.0:
            # First write should not be blocked by throttle.
            time_triggered = self._pending_counts[session_id] >= self.config.min_events
        else:
            time_triggered = (now - last_ts) >= self.config.throttle_seconds and self._pending_counts[session_id] >= self.config.min_events
        dirty_triggered = (
            self._pending_bytes[session_id] >= byte_threshold
            or self._pending_messages[session_id] >= message_threshold
            or dirty_sync.should_sync(session_id)
        )
        
        if not (time_triggered or dirty_triggered):
            return

        content = self._build_content(plan_summary, actions_summary, final_output)
        if not content:
            return

        est_tokens = max(1, int(len(content) / 4))
        action = ActionRequest.new(
            actor="session_delta_writer",
            action_type=ACTION_STORAGE_WRITE,
            domain=task_domain or DOMAIN_CORE,
            environment=task_environment or ENV_SANDBOX,
            risk_level=RISK_LOW,
            estimated_cost_tokens=est_tokens,
            description="session delta memory write",
            metadata={
                "session_id": session_id,
                "trace_id": trace_id,
                "attempt_index": attempt_index,
            },
        )
        guard = self.safety_kernel.guard_action(action)
        if not guard.allow:
            self._blocked_sessions[session_id] = True
            return

        self.memory_fabric.remember_atomic(
            content=content,
            source=f"session_delta:{session_id}",
            tier=MemoryTier.STS,
            importance=self.config.importance,
            tags=["session_delta", task_domain, task_environment],
            metadata={
                "session_delta": True,
                "trace_id": trace_id,
                "attempt_index": attempt_index,
                **(extra_metadata or {}),
            },
        )
        self._last_write_ts[session_id] = now
        self._pending_counts[session_id] = 0
        self._pending_bytes[session_id] = 0
        self._pending_messages[session_id] = 0
        if self.session_store is not None:
            try:
                state = self.session_store.load_or_create(session_id)
                state.deltas_cursor["pending_bytes"] = 0
                state.deltas_cursor["pending_messages"] = 0
                state.deltas_cursor["pending_events"] = 0
                state.dirty_flags["session_delta"] = False
                state.touch()
                self.session_store.save(state)
            except Exception:
                pass
        dirty_sync.mark_synced(session_id)

    def _build_content(self, plan_summary: str, actions_summary: str, final_output: str) -> str:
        parts = []
        if plan_summary:
            parts.append(f"Plan: {plan_summary.strip()}")
        if actions_summary:
            parts.append(f"Actions: {actions_summary.strip()}")
        if final_output:
            parts.append(f"Result: {final_output.strip()}")
        content = "\n".join(p for p in parts if p)
        if not content:
            return ""
        if len(content) > self.config.max_chars:
            content = content[: max(0, self.config.max_chars - 3)] + "..."
        return content
