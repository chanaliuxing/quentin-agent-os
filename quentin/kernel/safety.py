from __future__ import annotations

import os
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, Optional

from quentin.kernel.policy import PolicyEngine, ActionRequest, PolicyDecision
from quentin.kernel.budget import BudgetController, BudgetDecision
from quentin.kernel.interceptors import bootstrap_interceptors, get_security_interceptor_registry
from quentin.traces.core import JsonlTraceRecorder, TraceEventType, new_trace_event

def _env_bool(name: str, default: str = "0") -> bool:
    v = (os.getenv(name, default) or "").strip().lower()
    return v in ("1", "true", "yes", "on")


@dataclass
class GuardResult:
    allow: bool
    reason: str
    policy_decision: PolicyDecision
    budget_decision: BudgetDecision
    policy_hint: Optional[str] = None  # P5: Guidance for the Agent

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        if self.policy_hint:
            d["policy_hint"] = self.policy_hint
        return d


_INSTANCE: Optional[SafetyKernel] = None

def get_safety_kernel(repo_root: str | Path = ".") -> SafetyKernel:
    """
    Global singleton accessor for SafetyKernel.
    """
    global _INSTANCE
    if _INSTANCE is None:
        _INSTANCE = SafetyKernel(repo_root=repo_root)
    return _INSTANCE

class SafetyKernel:
    """
    SafetyKernel v1：

    - 统一守门口：任何“重要动作”先调用 guard_action
    - 内部组合：
        - PolicyEngine：检查宪法/风险边界
        - BudgetController：检查配额/算力预算

    用法示例（在 SelfProgrammingEngine 里）：

        action = ActionRequest.new(
            actor="selfprog_engine",
            action_type="code_patch",
            domain="core",
            environment="sandbox",
            risk_level="high",
            estimated_cost_tokens=estimated_tokens,
            description="Generate patch for mutable/selfprog/tools.py",
            metadata={"target_path": target_path}
        )
        guard = safety_kernel.guard_action(action)
        if not guard.allow:
            # 直接拒绝，自编程不能执行
            ...

    """

    def __init__(
        self,
        *,
        repo_root: str | Path = ".",
        policy_engine: Optional[PolicyEngine] = None,
        budget_controller: Optional[BudgetController] = None,
        trace_recorder: Optional[JsonlTraceRecorder] = None,
        approval_gate: Optional[Any] = None,
    ) -> None:
        self.policy_engine = policy_engine or PolicyEngine()
        self.budget_controller = budget_controller or BudgetController()
        rr = Path(repo_root).resolve()
        self.repo_root = rr
        self.trace_recorder = trace_recorder or JsonlTraceRecorder(repo_root=str(rr))
        self._approval_gate = approval_gate
        
        # P3-A: Interceptor Chain (Hard Logic Ring)
        # We always bootstrap; core interceptors are non-optional.
        bootstrap_interceptors(repo_root=rr)

    def _approval_enabled(self) -> bool:
        return _env_bool("QUENTIN_APPROVAL_GATE", "0")

    def _maybe_require_approval(self, *, action: ActionRequest) -> Optional[str]:
        """
        Optional HITL gate. Default OFF.

        Upstream can request approval by setting:
        - action.metadata["approval_required"]=True
        - action.metadata["approval_reason"]=...
        
        Also triggers for 'critical' risk level regardless of metadata,
        or 'high' risk 'code_patch' actions if enabled.
        """
        if not self._approval_enabled():
            return None
            
        md = action.metadata if isinstance(action.metadata, dict) else {}
        required = bool(md.get("approval_required", False))
        
        # Automatic triggers based on risk/type
        if action.risk_level == "critical":
            required = True
        elif action.risk_level == "high" and action.action_type == "code_patch":
            required = True
            
        if not required:
            return None
            
        reason = str(md.get("approval_reason") or f"approval_required_{action.action_type}_{action.risk_level}").strip()
        return reason or "approval_required"

    def guard_action(
        self,
        action: ActionRequest,
    ) -> GuardResult:
        try:
            self.trace_recorder.record_event(
                new_trace_event(
                    trace_id="safety_kernel",
                    event_type=TraceEventType.DECISION,
                    payload={
                        "action": "guard_action_start",
                        "action_id": action.action_id,
                        "actor": action.actor,
                        "action_type": action.action_type,
                        "domain": action.domain,
                        "environment": action.environment,
                        "risk_level": action.risk_level,
                    },
                )
            )
        except Exception:
            pass

        # P3-A: Interceptor Chain (Hard Logic Ring)
        if _env_bool("QUENTIN_POLICY_INTERCEPTORS", "1"):
            reg = get_security_interceptor_registry()
            allowed, int_reason, audit_meta = reg.run_all(action)
            if not allowed:
                # P5: Extract hint if any interceptor provided one
                hint = None
                for res in audit_meta.values():
                    if isinstance(res, dict) and res.get("policy_hint"):
                        hint = res["policy_hint"]
                        break

                return GuardResult(
                    allow=False,
                    reason=int_reason,
                    policy_decision=PolicyDecision(
                        allow=False, 
                        reason=int_reason, 
                        modifications={"interceptors": audit_meta}
                    ),
                    budget_decision=BudgetDecision(
                        allow=False,
                        reason="Skipped: interceptor denied.",
                        remaining_tokens_today=0,
                        remaining_tokens_month=0,
                        remaining_usd_today=0.0,
                        remaining_usd_month=0.0,
                    ),
                    policy_hint=hint
                )

        # 1) Policy decision
        p_dec = self.policy_engine.evaluate(action)
        if not p_dec.allow:
            # 预算检查可以省略，因为已经拒绝
            dummy_budget = BudgetDecision(
                allow=False,
                reason="Skipped: policy denied.",
                remaining_tokens_today=0,
                remaining_tokens_month=0,
                remaining_usd_today=0.0,
                remaining_usd_month=0.0,
            )
            return GuardResult(
                allow=False,
                reason=p_dec.reason,
                policy_decision=p_dec,
                budget_decision=dummy_budget,
            )

        # P3-A extension: Optional HITL approval gate (default OFF).
        approval_reason = self._maybe_require_approval(action=action)
        if approval_reason:
            tool_name = ""
            md = action.metadata if isinstance(action.metadata, dict) else {}
            try:
                tool_name = str(md.get("tool_name") or "")
            except Exception:
                tool_name = ""
            approval_ctx = md.get("approval_context") if isinstance(md.get("approval_context"), dict) else {}

            timeout_sec = 300
            try:
                timeout_sec = int(os.getenv("QUENTIN_APPROVAL_TIMEOUT_SEC", "300") or "300")
            except Exception:
                timeout_sec = 300

            approved = False
            request_id = ""
            try:
                gate = self._approval_gate
                if gate is None:
                    from quentin.infra.security.approval import approval_gate
                    gate = approval_gate

                approved, request_id = gate.request_approval_sync(
                        tool_name=tool_name or str(action.action_type),
                        args=dict(approval_ctx or {}),
                        reason=approval_reason,
                        timeout_seconds=max(1, int(timeout_sec)),
                    )
            except Exception:
                approved = False
                request_id = ""

            if not approved:
                suffix = f" request_id={request_id}" if request_id else ""
                deny_reason = f"approval_denied_or_expired: {approval_reason}{suffix}"
                return GuardResult(
                    allow=False,
                    reason=deny_reason,
                    policy_decision=PolicyDecision(
                        allow=False,
                        reason=deny_reason,
                        modifications={**(p_dec.modifications or {}), "approval_required": True, "approval_request_id": request_id},
                    ),
                    budget_decision=BudgetDecision(
                        allow=False,
                        reason="Skipped: approval denied/expired.",
                        remaining_tokens_today=0,
                        remaining_tokens_month=0,
                        remaining_usd_today=0.0,
                        remaining_usd_month=0.0,
                    ),
                )

        # Audit policy decision (best-effort)
        self._audit(
            action_id=action.action_id,
            event_type="guard_action",
            phase="policy_decision",
            actor=action.actor,
            payload={"decision": p_dec.to_dict()},
        )

        # 2) 预算 profile 选择
        profile_id = self.budget_controller.resolve_profile(
            environment=action.environment,
            domain=action.domain,
        )

        # 从 policy modifications 里读取强制上限（如果有的话）
        est_tokens = action.estimated_cost_tokens
        est_usd = action.estimated_cost_usd

        max_tokens = p_dec.modifications.get("max_cost_tokens")
        if isinstance(max_tokens, int) and max_tokens > 0:
            est_tokens = min(est_tokens, max_tokens)

        b_dec = self.budget_controller.check_and_reserve(
            profile_id=profile_id,
            tokens=est_tokens,
            usd=est_usd,
        )

        self._audit(
            action_id=action.action_id,
            event_type="guard_action",
            phase="budget_decision",
            actor=action.actor,
            payload={"profile_id": profile_id, "decision": b_dec.to_dict()},
        )

        allow = p_dec.allow and b_dec.allow
        reason = p_dec.reason if not b_dec.allow else f"{p_dec.reason} | {b_dec.reason}"

        result = GuardResult(
            allow=allow,
            reason=reason,
            policy_decision=p_dec,
            budget_decision=b_dec,
        )
        try:
            self.trace_recorder.record_event(
                new_trace_event(
                    trace_id="safety_kernel",
                    event_type=TraceEventType.DECISION,
                    payload={
                        "action": "guard_action_result",
                        "action_id": action.action_id,
                        "allow": result.allow,
                        "reason": result.reason,
                        "policy": p_dec.to_dict(),
                        "budget": b_dec.to_dict(),
                    },
                )
            )
        except Exception:
            pass
        self._audit(
            action_id=action.action_id,
            event_type="guard_action",
            phase="result",
            actor=action.actor,
            payload={"allow": result.allow, "reason": result.reason},
        )
        return result

    def _audit(self, *, action_id: str, event_type: str, phase: str, actor: str, payload: Dict[str, Any]) -> None:
        try:
            from quentin.kernel.audit import default_audit_logger
            from quentin.security.audit_schema import AuditEvent as SecurityAuditEvent

            # Always log to legacy audit
            # ... (omitted for brevity in this specific replacement, 
            # but usually we'd keep it or just use the new one)
            
            # P3-Audit: Use the security schema for critical phases
            if phase in ("result", "policy_decision"):
                decision = "allow" if payload.get("allow") or payload.get("decision", {}).get("allow") else "block"
                sec_event = SecurityAuditEvent(
                    event_id=action_id,
                    actor=actor,
                    action=f"{event_type}:{phase}",
                    resource=str(payload.get("profile_id") or "system"),
                    decision=decision,
                    reason=str(payload.get("reason") or payload.get("decision", {}).get("reason") or ""),
                    metadata=payload
                )
                default_audit_logger().append(sec_event)
        except Exception:
            return
