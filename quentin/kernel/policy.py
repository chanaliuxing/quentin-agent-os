from __future__ import annotations

from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Any, Dict, Optional
import json
import logging
import uuid
from datetime import datetime, timezone

from quentin.llm.multi_council import MultiAICouncil, CouncilDecision
from quentin.llm.types import LLMConfig
from quentin.runtime.session_write_lock import acquire_session_write_lock
from quentin.kernel.taxonomy import ActionType, Domain, Environment, RiskLevel, ENV_SANDBOX, DOMAIN_CORE, RISK_MEDIUM

logger = logging.getLogger(__name__)


# ---------- Action & Decision ----------

@dataclass
class ActionRequest:
    """
    一次“重要动作”的申请：

    - action_id     : 全局唯一 ID（可由调用方预先生成，也可留空自动生成）
    - actor         : 谁发起的（如 'cognitive_loop', 'selfprog_engine', 'sleep_loop'）
    - action_type   : 动作类型（'llm_call', 'tool_call', 'code_patch', 'experiment_run', ...）
    - domain        : 领域（'core', 'desktop', 'legal', 'trading', 'cross', ...）
    - environment   : 执行环境（'sandbox', 'staging', 'prod'）
    - risk_level    : 风险等级（'low', 'medium', 'high', 'critical'）

    - estimated_cost_tokens : 预估 token 消耗
    - estimated_cost_usd    : 预估费用（可以为 0，先作为抽象字段）
    - description           : 人类可读描述
    - metadata              : 任何额外信息（如 patch diff 摘要、实验 config 摘要等）
    """

    action_id: str
    actor: str
    action_type: ActionType
    domain: Domain
    environment: Environment
    risk_level: RiskLevel

    estimated_cost_tokens: int = 0
    estimated_cost_usd: float = 0.0
    description: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def new(
        cls,
        *,
        actor: str,
        action_type: ActionType,
        domain: Domain = DOMAIN_CORE,
        environment: Environment = ENV_SANDBOX,
        risk_level: RiskLevel = RISK_MEDIUM,
        estimated_cost_tokens: int = 0,
        estimated_cost_usd: float = 0.0,
        description: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> "ActionRequest":
        return cls(
            action_id=str(uuid.uuid4()),
            actor=actor,
            action_type=action_type,
            domain=domain,
            environment=environment,
            risk_level=risk_level,
            estimated_cost_tokens=estimated_cost_tokens,
            estimated_cost_usd=estimated_cost_usd,
            description=description,
            metadata=metadata or {},
        )


@dataclass
class PolicyDecision:
    """
    宪法层对一次动作的决定：

    - allow       : 是否允许
    - reason      : 简短理由（给人或上层日志看）
    - severity    : 信息等级（'info', 'warning', 'error', 'critical'）
    - modifications:
        允许但需要做的小改动，例如：
        {
          "downgrade_environment": "sandbox",
          "max_cost_tokens": 20000,
          "require_canary": true
        }
    """

    allow: bool
    reason: str
    severity: str = "info"
    modifications: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ---------- Policy Engine ----------

class PolicyEngine:
    """
    PolicyEngine v1：

    - 从 config/constitution.json 读取“宪法规则”
    - 基于 environment / domain / action_type / risk_level 做快速决策
    - 对于边界情况（如 high risk in prod），可以调用 MultiAICouncil 做 AI 审议

    宪法配置示例（config/constitution.json）：

    {
      "version": "v1",
      "global": {
        "max_risk_in_prod": "medium",
        "allow_self_programming": true
      },
      "environments": {
        "sandbox": {
          "max_risk": "critical"
        },
        "staging": {
          "max_risk": "high"
        },
        "prod": {
          "max_risk": "medium"
        }
      },
      "domains": {
        "trading": {
          "allow_self_programming": false
        },
        "legal": {
          "allow_self_programming": false
        },
        "desktop": {
          "allow_self_programming": true
        }
      },
      "action_types": {
        "code_patch": {
          "require_review": true
        },
        "experiment_run": {
          "max_parallel": 3
        }
      }
    }
    """

    _RISK_LEVEL_ORDER = {
        "low": 0,
        "medium": 1,
        "high": 2,
        "critical": 3,
    }

    def __init__(
        self,
        *,
        repo_root: str | Path = ".",
        constitution_path: str | Path = "config/constitution.json",
        decision_log_path: str | Path = "data/policy_decisions.jsonl",
        council: Optional[MultiAICouncil] = None,
    ) -> None:
        import os
        self.repo_root = Path(repo_root).resolve()
        self.constitution_path = self.repo_root / constitution_path
        override = (os.getenv("QUENTIN_POLICY_DECISIONS_PATH") or "").strip()
        if override:
            p = Path(override).expanduser()
            if not p.is_absolute():
                p = (self.repo_root / p).resolve()
            self.decision_log_path = p
        else:
            self.decision_log_path = self.repo_root / decision_log_path
        self.decision_log_path.parent.mkdir(parents=True, exist_ok=True)

        self._constitution: Dict[str, Any] = {}
        self._load_constitution()

        if council is None:
            # Blueprint v3 fixed four roles (multi-agent), matching OpenClaw takeaways:
            # Speed / Safety / Cost / Domain-Expert. Each role can map to different models.
            import os

            provider = (os.getenv("LLM_PROVIDER") or "ollama").strip().lower()
            default_model = os.getenv("LLM_MODEL")
            if not default_model:
                # Allow static-policy-only mode when no model is configured (common in unit tests).
                # Borderline cases will skip AI council consultation when council is unavailable.
                logger.warning("PolicyEngine: LLM_MODEL not set; running in static-policy-only mode.")
                self.council = None
                return

            if provider != "ollama":
                # For remote providers, don't default to Ollama-only model ids.
                model_speed = os.getenv("LLM_MODEL_SPEED") or default_model
                model_safety = os.getenv("LLM_MODEL_SAFETY") or default_model
                model_cost = os.getenv("LLM_MODEL_COST") or default_model
                model_expert = os.getenv("LLM_MODEL_EXPERT") or default_model
            else:
                model_speed = os.getenv("LLM_MODEL_SPEED") or default_model
                model_safety = os.getenv("LLM_MODEL_SAFETY") or os.getenv("LLM_MODEL_CRITIC") or default_model
                model_cost = os.getenv("LLM_MODEL_COST") or os.getenv("LLM_MODEL_CHEAP") or default_model
                model_expert = os.getenv("LLM_MODEL_EXPERT") or default_model

            members = [
                LLMConfig(provider=provider, model=model_speed, role="Speed-Agent"),
                LLMConfig(provider=provider, model=model_safety, role="Safety-Agent"),
                LLMConfig(provider=provider, model=model_cost, role="Cost-Agent"),
                LLMConfig(provider=provider, model=model_expert, role="Domain-Expert-Agent"),
            ]
            council = MultiAICouncil(members=members)
        self.council = council

    # ---------- 公共接口 ----------

    def evaluate(self, action: ActionRequest) -> PolicyDecision:
        """
        主入口：同步返回决策结果。
        """
        base_decision = self._eval_static_rules(action)

        if not base_decision.allow:
            # 明确违反宪法，直接拒绝
            self._log_decision(action, base_decision)
            return base_decision

        # borderline case：risk 高、在 prod / staging、或者 estimated_cost 特别大
        if self._is_borderline(action) and self.council is not None:
            ai_decision = self._consult_council(action, base_decision)
            self._log_decision(action, ai_decision)
            return ai_decision

        # 正常通过
        self._log_decision(action, base_decision)
        return base_decision

    # ---------- 内部：静态规则 ----------

    def _eval_static_rules(self, action: ActionRequest) -> PolicyDecision:
        import os
        is_canary = os.getenv("QUENTIN_CANARY", "0").strip().lower() in ("1", "true", "yes", "on")
        
        env_cfg = (self._constitution.get("environments") or {}).get(action.environment, {})
        dom_cfg = (self._constitution.get("domains") or {}).get(action.domain, {})
        act_cfg = (self._constitution.get("action_types") or {}).get(action.action_type, {})
        global_cfg = self._constitution.get("global") or {}

        # Canary enforcement: strict risk limits
        if is_canary:
            canary_max_risk = "medium"
            if self._RISK_LEVEL_ORDER.get(action.risk_level, 0) > self._RISK_LEVEL_ORDER.get(canary_max_risk, 1):
                return PolicyDecision(
                    allow=False,
                    severity="critical",
                    reason=f"Canary mode active: risk level '{action.risk_level}' exceeds canary limit '{canary_max_risk}'."
                )

        # 1. 环境下的最大 risk
        env_max_risk = env_cfg.get("max_risk") or global_cfg.get("max_risk_in_prod", "medium")
        if not self._risk_allowed(action.risk_level, env_max_risk):
            return PolicyDecision(
                allow=False,
                severity="error",
                reason=(
                    f"Risk level '{action.risk_level}' exceeds environment '{action.environment}' "
                    f"max_risk '{env_max_risk}'."
                ),
            )

        # 1.5. Experiments default to sandbox-only (can be relaxed by constitution config).
        if action.action_type == "experiment_run":
            sandbox_only = bool(act_cfg.get("sandbox_only", True))
            if sandbox_only and action.environment != "sandbox":
                return PolicyDecision(
                    allow=True,
                    severity="warning",
                    reason=(
                        f"Experiment runs are sandbox-only by default; requested environment='{action.environment}'. "
                        "Allow with downgrade to sandbox."
                    ),
                    modifications={"downgrade_environment": "sandbox"},
                )

        # 1.75. Deploy gating: allow but emit required gates via modifications.
        # This is consumed by higher-level automation (release protocol / research promotions).
        if action.action_type == "deploy":
            mods: Dict[str, Any] = {}

            # Prod is always gated.
            if action.environment == "prod":
                mods["require_canary"] = True
                mods["require_human_gate"] = True

            # Staging: canary is strongly recommended; high-risk requires a human gate.
            if action.environment == "staging":
                mods["require_canary"] = True
                if action.risk_level in ("high", "critical"):
                    mods["require_human_gate"] = True

            # High-risk domains default to human gating for deploy-like changes.
            if action.domain in ("legal", "trading", "cross"):
                mods["require_canary"] = True
                mods["require_human_gate"] = True

            if mods:
                return PolicyDecision(
                    allow=True,
                    severity="warning",
                    reason="Deploy allowed with gates (require_canary/require_human_gate).",
                    modifications=mods,
                )

        # 2. 自编程限制（按 domain + global）
        if action.action_type == "code_patch":
            if is_canary:
                return PolicyDecision(
                    allow=True,
                    severity="warning",
                    reason="Canary mode active: code_patch allowed but auto-apply forbidden.",
                    modifications={"require_review": True, "allow_auto_apply": False}
                )
            allow_self_prog = dom_cfg.get("allow_self_programming")
            if allow_self_prog is None:
                allow_self_prog = global_cfg.get("allow_self_programming", False)
            if not allow_self_prog:
                return PolicyDecision(
                    allow=False,
                    severity="error",
                    reason=f"Self-programming is disabled for domain '{action.domain}'.",
                )

        # 3. 简单 cost 约束（示例：单次动作 token 超出阈值则需要 degrade）
        max_tokens_per_action = int(global_cfg.get("max_tokens_per_action", 200_000))
        if action.estimated_cost_tokens > max_tokens_per_action:
            return PolicyDecision(
                allow=True,
                severity="warning",
                reason=(
                    f"Estimated tokens {action.estimated_cost_tokens} exceed "
                    f"global.soft_limit {max_tokens_per_action}. Allow with downgrade."
                ),
                modifications={
                    "max_cost_tokens": max_tokens_per_action,
                    "require_canary": True,
                },
            )

        # 4. action_types 级别的一些标志（示例：code_patch 必须 require_review）
        if act_cfg.get("require_review") and action.environment == "prod":
            return PolicyDecision(
                allow=True,
                severity="warning",
                reason="Production code_patch requires review. Marking require_review flag.",
                modifications={"require_review": True},
            )

        # 默认允许
        return PolicyDecision(
            allow=True,
            severity="info",
            reason="Allowed by static policy.",
            modifications={},
        )

    # ---------- 内部：AI 审议 ----------

    def _is_borderline(self, action: ActionRequest) -> bool:
        try:
            meta = action.metadata or {}
            if bool(meta.get("bypass_ai_council")):
                return False
            if str(action.actor or "").startswith("multi_ai_council"):
                return False
        except Exception:
            pass
        # 简单规则：高风险 + staging/prod；或者 tokens 特别大
        risk_order = self._RISK_LEVEL_ORDER.get(action.risk_level, 1)
        is_high_risk = risk_order >= self._RISK_LEVEL_ORDER["high"]
        is_prod_like = action.environment in ("prod", "staging")
        high_cost = action.estimated_cost_tokens > 150_000

        return (is_high_risk and is_prod_like) or high_cost

    def _consult_council(
        self,
        action: ActionRequest,
        base_decision: PolicyDecision,
    ) -> PolicyDecision:
        """
        用多 AI 会议审议边界情况。

        约定：
        - Council 返回 JSON：
          {
            "allow": true/false,
            "severity": "info|warning|error|critical",
            "reason": "...",
            "modifications": {...}
          }
        """
        context = json.dumps(action.to_dict(), ensure_ascii=False, indent=2)
        question = (
            "You are a CONSTITUTIONAL COUNCIL for a self-evolving AI system.\n" 
            "Given the following action request and a baseline static policy decision,\n" 
            "you must decide whether to allow it, and if allowed, whether to impose\n" 
            "additional constraints.\n\n" 
            "Return ONLY one JSON object:\n" 
            "{\n" 
            "  \"allow\": true/false,\n" 
            "  \"severity\": \"info|warning|error|critical\",\n" 
            "  \"reason\": \"...\",\n" 
            "  \"modifications\": {\"key\": \"value\", ...}\n" 
            "}\n"
        )

        merged_context = (
            "=== ACTION REQUEST ===\n"
            f"{context}\n\n"
            "=== STATIC POLICY DECISION ===\n"
            f"{json.dumps(base_decision.to_dict(), ensure_ascii=False, indent=2)}\n"
        )

        decision: CouncilDecision = self.council.deliberate(
            question=question,
            context=merged_context,
            mode="policy_decision",
        )
        ans = decision.final_answer or "{}"
        # Best-effort audit: record multi-agent participation for traceability.
        try:
            from quentin.kernel.audit import AuditEvent, default_audit_logger
            from quentin.traces.core import JsonlTraceRecorder, new_trace_event, TraceEventType

            opinions = []
            for op in (decision.opinions or [])[:8]:
                opinions.append(
                    {
                        "model": getattr(op, "model", ""),
                        "role": getattr(op, "role", ""),
                        "answer_preview": (getattr(op, "answer", "") or "")[:1200],
                    }
                )
            default_audit_logger().append(
                AuditEvent(
                    action_id=action.action_id,
                    event_type="multi_agent",
                    phase="policy_borderline_council",
                    actor="policy_engine",
                    payload={
                        "base_decision": base_decision.to_dict(),
                        "council_reasoning": (decision.reasoning or "")[:1200],
                        "council_final_answer_preview": (ans or "")[:1200],
                        "opinions": opinions,
                    },
                )
            )
            JsonlTraceRecorder(repo_root=str(self.repo_root)).record_event(
                new_trace_event(
                    trace_id=action.action_id,
                    event_type=TraceEventType.DECISION,
                    payload={
                        "kind": "policy_borderline",
                        "base_decision": base_decision.to_dict(),
                        "council_reasoning": (decision.reasoning or "")[:1200],
                        "council_final_answer_preview": (ans or "")[:1200],
                        "opinions": opinions,
                    },
                )
            )
        except Exception:
            pass

        try:
            s = ans.strip()
            first = s.find("{")
            last = s.rfind("}")
            if first != -1 and last != -1 and last > first:
                s = s[first : last + 1]
            data = json.loads(s)
            allow = bool(data.get("allow", base_decision.allow))
            severity = str(data.get("severity", base_decision.severity))
            reason = str(data.get("reason", base_decision.reason))
            mods = data.get("modifications") or {}
            if not isinstance(mods, dict):
                mods = {}
            return PolicyDecision(
                allow=allow,
                severity=severity,
                reason=reason,
                modifications=mods,
            )
        except Exception:
            logger.exception("PolicyEngine._consult_council: parse error: %r", ans)
            # 回退到 static 决策
            return base_decision

    # ---------- 内部工具 ----------

    def _risk_allowed(self, req: str, max_level: str) -> bool:
        return self._RISK_LEVEL_ORDER.get(req, 0) <= self._RISK_LEVEL_ORDER.get(max_level, 1)

    def _load_constitution(self) -> None:
        if not self.constitution_path.exists():
            # 给一个保守默认值
            self._constitution = {
                "version": "v1-default",
                "global": {
                    "max_risk_in_prod": "medium",
                    "allow_self_programming": True,
                    "max_tokens_per_action": 200_000,
                },
                "environments": {
                    "sandbox": {"max_risk": "critical"},
                    "staging": {"max_risk": "high"},
                    "prod": {"max_risk": "medium"},
                },
                "domains": {
                    # Default high-risk domains require human gating for self-programming.
                    "legal": {"allow_self_programming": False},
                    "trading": {"allow_self_programming": False},
                    "desktop": {"allow_self_programming": True},
                },
                "action_types": {
                    # Conservative default: experiments should not run outside sandbox unless explicitly configured.
                    "experiment_run": {"sandbox_only": True},
                },
            }
            return
        try:
            raw = json.loads(self.constitution_path.read_text(encoding="utf-8") or "{}")
            self._constitution = raw or {}
        except Exception:
            logger.exception(
                "PolicyEngine._load_constitution: failed to read %s",
                self.constitution_path,
            )
            self._constitution = {}

    def _log_decision(self, action: ActionRequest, decision: PolicyDecision) -> None:
        record = {
            "action": action.to_dict(),
            "decision": decision.to_dict(),
            "logged_at": datetime.now(timezone.utc).isoformat(),
        }
        try:
            lock = acquire_session_write_lock(session_file=self.decision_log_path)
            try:
                with self.decision_log_path.open("a", encoding="utf-8") as f:
                    f.write(json.dumps(record, ensure_ascii=False) + "\n")
            finally:
                lock["release"]()
        except Exception:
            logger.exception(
                "PolicyEngine._log_decision: failed to append to %s",
                self.decision_log_path,
            )
