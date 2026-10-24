from __future__ import annotations

from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import json
import logging
import os
import time

import yaml

from quentin.models.router import ModelRouter
from quentin.llm.client import call_llm
from quentin.cognitive.prompt_layers import build_layered_system_prompt

logger = logging.getLogger(__name__)


class SafeJSONEncoder(json.JSONEncoder):
    """
    Handles non-serializable objects like CancellationToken by converting them to string or skipping.
    """
    def default(self, obj):
        try:
            return super().default(obj)
        except TypeError:
            return f"<<non-serializable: {type(obj).__name__}>>"


def _strip_code_fences(raw: str) -> str:
    raw = (raw or "").strip()
    if "```" not in raw:
        return raw
    # Common patterns: ```json ... ```
    if "```json" in raw:
        raw = raw.split("```json", 1)[1]
    else:
        raw = raw.split("```", 1)[1]
    raw = raw.split("```", 1)[0].strip()
    return raw.strip()


def _parse_jsonish(raw: str) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """
    Best-effort parse LLM output into a dict.
    Supports:
    - raw JSON
    - fenced JSON
    - YAML-as-JSON (some models output YAML-like dicts)
    """
    text = _strip_code_fences(raw)
    if not text:
        return None, "empty"
    try:
        obj = json.loads(text)
        if isinstance(obj, dict):
            return obj, None
        return None, "not_dict_json"
    except Exception:
        pass
    try:
        obj = yaml.safe_load(text)
        if isinstance(obj, dict):
            return obj, None
        return None, "not_dict_yaml"
    except Exception:
        return None, "parse_error"

def _truncate_text(text: str, limit: int = 4000) -> str:
    t = (text or "").strip()
    if limit <= 0:
        return ""
    if len(t) <= limit:
        return t
    return t[:limit] + "...<truncated>"


def _compact_json_value(value: Any, *, max_chars: int) -> Any:
    if value is None:
        return None
    try:
        text = json.dumps(value, ensure_ascii=False, cls=SafeJSONEncoder)
    except Exception:
        text = str(value)
    if len(text) <= max_chars:
        return value
    return {"_truncated": _truncate_text(text, max_chars)}


def _council_timeout_seconds(*, is_arbiter: bool) -> float:
    """
    Council-specific timeout controls.
    Falls back to QUENTIN_LLM_TIMEOUT_S when council-specific vars are not set.
    """
    if is_arbiter:
        raw = os.getenv("QUENTIN_COUNCIL_ARBITER_TIMEOUT_S")
        default = os.getenv("QUENTIN_LLM_TIMEOUT_LOCAL_S", os.getenv("QUENTIN_LLM_TIMEOUT_S", "300"))
    else:
        raw = os.getenv("QUENTIN_COUNCIL_MEMBER_TIMEOUT_S")
        default = os.getenv("QUENTIN_LLM_TIMEOUT_LOCAL_S", os.getenv("QUENTIN_LLM_TIMEOUT_S", "180"))
    try:
        return float((raw or default).strip() or default)
    except Exception:
        return float(default)

def _looks_local_endpoint(url: Optional[str]) -> bool:
    raw = str(url or "").strip().lower()
    if not raw:
        return False
    for marker in ("localhost", "127.0.0.1", "::1", ".local", "192.168.", "10."):
        if marker in raw:
            return True
    if "172." in raw:
        return True
    return False


def _resolve_council_timeout_for_route(*, route: Any, is_arbiter: bool) -> float:
    base = _council_timeout_seconds(is_arbiter=is_arbiter)
    provider = str(getattr(route, "provider", "") or "").strip().lower()
    base_url = str(getattr(route, "base_url", "") or "").strip()
    is_local = provider == "ollama" or _looks_local_endpoint(base_url)
    if not is_local:
        return base
    env_name = "QUENTIN_COUNCIL_LOCAL_ARBITER_TIMEOUT_S" if is_arbiter else "QUENTIN_COUNCIL_LOCAL_MEMBER_TIMEOUT_S"
    try:
        raw = os.getenv(env_name)
        if raw not in (None, ""):
            return float(raw)
    except Exception:
        return base
    return base


def _is_local_llm_runtime() -> bool:
    provider = str(os.getenv("LLM_PROVIDER", "") or "").strip().lower()
    if provider in {"ollama", "local", "lmstudio"}:
        return True
    base_url = str(os.getenv("LLM_BASE_URL", "") or "").strip()
    return _looks_local_endpoint(base_url)


def _fallback_parse(*, council_name: str, topic: str, raw: str) -> Dict[str, Any]:
    """
    When a model returns non-JSON, keep the council operational by wrapping raw text
    into a predictable envelope, instead of treating the whole council as failed.
    """
    txt = _truncate_text(raw, 4000)
    council = str(council_name or "").strip().lower()
    tp = str(topic or "").strip().lower()
    if council == "reflection" or tp == "reflection":
        return {
            "verdict": "undecided",
            "reasoning": txt,
            "answer": {"action": "retry", "new_plan": None, "goal_adjustment": None, "skill_ideas": []},
        }
    if council == "done" or tp == "done_check":
        return {"verdict": "undecided", "reasoning": txt}
    return {"verdict": "undecided", "reasoning": txt, "answer": txt}


@dataclass
class CouncilMemberConfig:
    """
    One council member = a routing key + a role label.
    """

    member_id: str
    router_mode: str
    router_task_type: str
    role: str = "general"
    weight: float = 1.0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class CouncilConfig:
    """
    Council configuration loaded from `config/councils.yaml` or `config/councils.json`.
    """

    name: str
    description: str
    members: List[CouncilMemberConfig]
    decision_mode: str = "first"  # "first" | "arbiter_llm"
    arbiter_router_mode: Optional[str] = None
    arbiter_router_task_type: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "decision_mode": self.decision_mode,
            "arbiter_router_mode": self.arbiter_router_mode,
            "arbiter_router_task_type": self.arbiter_router_task_type,
            "members": [m.to_dict() for m in self.members],
        }


@dataclass
class CouncilQuestion:
    """
    The input question for a council discussion.
    """

    topic: str
    importance: str
    prompt: str
    payload: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        # Phase 5.4: Manual dict to avoid deepcopy issues with non-serializable objects
        out = {
            "topic": self.topic,
            "importance": self.importance,
            "prompt": self.prompt,
            "payload": {}
        }
        if isinstance(self.payload, dict):
            for k, v in self.payload.items():
                if isinstance(v, (str, int, float, bool, list, dict)) or v is None:
                    out["payload"][k] = v
        return out


@dataclass
class CouncilMemberReply:
    member_id: str
    raw_output: str
    parsed: Optional[Dict[str, Any]]
    error: Optional[str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "member_id": self.member_id,
            "raw_output": self.raw_output,
            "parsed": self.parsed,
            "error": self.error,
        }


@dataclass
class CouncilDecision:
    council_name: str
    topic: str
    final: Dict[str, Any]
    member_replies: List[CouncilMemberReply]
    arbiter_raw: Optional[str]
    created_at: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "council_name": self.council_name,
            "topic": self.topic,
            "final": self.final,
            "member_replies": [r.to_dict() for r in self.member_replies],
            "arbiter_raw": self.arbiter_raw,
            "created_at": self.created_at,
        }


class CouncilManager:
    """
    A small, reliable CouncilManager used by the canonical `quentin/cognitive/*` loops.

    Notes:
    - Config lives in `config/councils.yaml` (preferred) or `config/councils.json`.
    - If a council is missing, it falls back to a single-member "first" decision.
    - Member calls are routed via `quentin.models.router.ModelRouter.route()`.
    """

    def __init__(
        self,
        *,
        repo_root: str | Path = ".",
        model_router: Optional[ModelRouter] = None,
    ) -> None:
        self.repo_root = Path(repo_root).resolve()
        self.model_router = model_router or ModelRouter()
        self._councils: Dict[str, CouncilConfig] = {}
        self._member_failure_streaks: Dict[str, int] = {}
        self._load_config()

    # --------------------------------------------------------------------- config
    def _load_config(self) -> None:
        cfg_dir = self.repo_root / "config"
        yaml_path = cfg_dir / "councils.yaml"
        json_path = cfg_dir / "councils.json"

        data: Optional[Dict[str, Any]] = None
        if yaml_path.exists():
            try:
                data = yaml.safe_load(yaml_path.read_text(encoding="utf-8") or "") or {}
            except Exception:
                logger.exception("CouncilManager: failed to load %s", yaml_path)
                data = None
        if data is None and json_path.exists():
            try:
                data = json.loads(json_path.read_text(encoding="utf-8") or "{}") or {}
            except Exception:
                logger.exception("CouncilManager: failed to load %s", json_path)
                data = None

        councils_data = None
        if isinstance(data, dict):
            councils_data = data.get("councils") if isinstance(data.get("councils"), dict) else data
        if not isinstance(councils_data, dict):
            self._councils = {}
            return

        councils: Dict[str, CouncilConfig] = {}
        for name, cfg in councils_data.items():
            if not isinstance(cfg, dict):
                continue
            members_cfg = cfg.get("members") or []
            members: List[CouncilMemberConfig] = []
            for m in members_cfg:
                if not isinstance(m, dict):
                    continue
                try:
                    members.append(
                        CouncilMemberConfig(
                            member_id=str(m.get("member_id") or f"{name}_member_{len(members)+1}"),
                            router_mode=str(m.get("router_mode") or name),
                            router_task_type=str(m.get("router_task_type") or "core"),
                            role=str(m.get("role") or "general"),
                            weight=float(m.get("weight") or 1.0),
                        )
                    )
                except Exception:
                    continue
            if not members:
                continue

            arbiter_cfg = cfg.get("arbiter") or {}
            councils[name] = CouncilConfig(
                name=str(name),
                description=str(cfg.get("description") or ""),
                members=members,
                decision_mode=str(cfg.get("decision_mode") or "first"),
                arbiter_router_mode=str(arbiter_cfg.get("router_mode") or "") or None,
                arbiter_router_task_type=str(arbiter_cfg.get("router_task_type") or "") or None,
            )

        self._councils = councils

    def _build_fallback_config(self, name: str, topic: str) -> CouncilConfig:
        member = CouncilMemberConfig(
            member_id=f"{name}_default_member",
            router_mode=name,
            router_task_type=topic or "core",
            role="general",
            weight=1.0,
        )
        return CouncilConfig(
            name=name,
            description=f"Fallback single-member council for {name}",
            members=[member],
            decision_mode="first",
        )

    # --------------------------------------------------------------------- execution
    def ask(self, council_name: str, question: CouncilQuestion) -> CouncilDecision:
        return self.run_council(council_name, question)

    def run_council(self, council_name: str, question: CouncilQuestion) -> CouncilDecision:
        cfg = self._councils.get(council_name) or self._build_fallback_config(council_name, question.topic)
        complexity = self._classify_question_complexity(question)

        # P4-A: Fast Track logic
        forced_local_fast_path = self._should_force_local_fast_path(
            council_name=council_name,
            question=question,
            complexity=complexity,
        )
        is_fast_track = question.importance == "low" or complexity == "simple" or forced_local_fast_path
        
        active_members: List[CouncilMemberConfig] = []
        if is_fast_track:
            active_members = [cfg.members[0]]
            if forced_local_fast_path:
                logger.info(
                    "Council: LOCAL FAST PATH triggered for %s:%s (Single Member)",
                    cfg.name,
                    question.topic,
                )
            else:
                logger.info("Council: FAST TRACK triggered for %s:%s (Single Member)", cfg.name, question.topic)
        elif question.importance == "normal":
            # Normal: Only core members (weight > 0.5)
            active_members = [m for m in cfg.members if m.weight > 0.5] or [cfg.members[0]]
        else:
            # High + reasoning_heavy: Full Council
            active_members = list(cfg.members)

        # Ensure we don't use the same provider family for all critical votes
        used_providers = set()
        
        # Optional serialization
        serialize = os.getenv("QUENTIN_COUNCIL_SERIALIZE", "0").strip().lower() in ("1", "true", "yes", "on")

        replies: List[CouncilMemberReply] = []
        for member in active_members:
            try:
                member_key = f"{cfg.name}:{member.member_id}"
                
                # Check for provider diversity in high importance tasks
                route_task_type = self._resolve_council_task_type(member.router_task_type, complexity=complexity)
                route = self.model_router.route(mode=member.router_mode, task_type=route_task_type)
                
                if question.importance == "high" and route.provider in used_providers:
                    # Try to force a different provider if available
                    pass
                
                used_providers.add(route.provider)

                fail_streak_before = int(self._member_failure_streaks.get(member_key, 0))
                parse_failed = False
                if forced_local_fast_path:
                    parsed = self._build_local_fast_path_reply(council_name=cfg.name, question=question)
                    raw = json.dumps(parsed, ensure_ascii=False)
                    err = None
                else:
                    raw = self._ask_member(
                        cfg=cfg,
                        member=member,
                        question=question,
                        complexity=complexity,
                        force_model=None,
                        escalation_reason="",
                        fallback_chain=[],
                    )
                    parsed, err = _parse_jsonish(raw)
                    if err:
                        parse_failed = True
                if (not parsed) and str(raw or "").strip():
                    parsed = _fallback_parse(council_name=cfg.name, topic=question.topic, raw=raw)
                    # Keep council operational, but still treat this as a parse failure
                    # for escalation/streak accounting.
                    err = None
                    parse_failed = True
                
                # No escalation in fast track to keep it snappy
                if not is_fast_track and parse_failed and complexity in {"edit_heavy", "reasoning_heavy"}:
                    high_tier_model = str(os.getenv("QUENTIN_HIGH_TIER_MODEL") or "").strip()
                    escalate_after = int(os.getenv("QUENTIN_COUNCIL_ESCALATE_AFTER", "2") or "2")
                    should_escalate = bool(high_tier_model) and (fail_streak_before + 1 >= max(1, escalate_after))
                    if should_escalate:
                        fallback_chain = [str(getattr(member, "router_task_type", "") or ""), "reasoning_heavy"]
                        raw_retry = self._ask_member(
                            cfg=cfg,
                            member=member,
                            question=question,
                            complexity="reasoning_heavy",
                            force_model=high_tier_model,
                            escalation_reason="member_parse_error_streak",
                            fallback_chain=fallback_chain,
                        )
                        parsed_retry, err_retry = _parse_jsonish(raw_retry)
                        if (not parsed_retry) and str(raw_retry or "").strip():
                            parsed_retry = _fallback_parse(council_name=cfg.name, topic=question.topic, raw=raw_retry)
                            err_retry = None
                        if parsed_retry:
                            raw = raw_retry
                            parsed = parsed_retry
                            err = err_retry
                if parse_failed:
                    self._member_failure_streaks[member_key] = fail_streak_before + 1
                else:
                    self._member_failure_streaks[member_key] = 0
                replies.append(
                    CouncilMemberReply(
                        member_id=member.member_id,
                        raw_output=raw,
                        parsed=parsed,
                        error=err,
                    )
                )
            except Exception as e:
                logger.exception("CouncilManager: member %s failed completely: %s", member.member_id, e)
                replies.append(
                    CouncilMemberReply(
                        member_id=member.member_id,
                        raw_output="",
                        parsed=None,
                        error=str(e),
                    )
                )

            if (not is_fast_track) and serialize and len(active_members) > 1:
                # Small delay between members to further mitigate burst rate limits
                time.sleep(float(os.getenv("QUENTIN_COUNCIL_MEMBER_DELAY", "1.0")))

        # Check if we have at least one successful reply before aggregating
        success_count = sum(1 for r in replies if r.parsed and not r.error)
        if success_count == 0:
            logger.error("CouncilManager: all members failed for council %s", council_name)
            final = {
                "verdict": "all_failed",
                "reasoning": f"all members failed for council={council_name}",
                "answer": {},
            }
            return CouncilDecision(
                council_name=cfg.name,
                topic=question.topic,
                final=final,
                member_replies=replies,
                arbiter_raw=None,
                created_at=datetime.now(timezone.utc).isoformat(),
            )

        # In Fast Track, we skip complex aggregation entirely if the first member succeeded
        if is_fast_track and replies[0].parsed:
            final = replies[0].parsed
            arbiter_raw = None
        else:
            final, arbiter_raw = self._aggregate_decision(cfg=cfg, question=question, replies=replies)
            
        return CouncilDecision(
            council_name=cfg.name,
            topic=question.topic,
            final=final,
            member_replies=replies,
            arbiter_raw=arbiter_raw,
            created_at=datetime.now(timezone.utc).isoformat(),
        )

    def _should_force_local_fast_path(
        self,
        *,
        council_name: str,
        question: CouncilQuestion,
        complexity: str,
    ) -> bool:
        flag = str(os.getenv("QUENTIN_COUNCIL_LOCAL_FAST_PATH", "1") or "").strip().lower()
        if flag not in {"1", "true", "yes", "on"}:
            return False
        if not _is_local_llm_runtime():
            return False

        allowed = {
            x.strip().lower()
            for x in str(
                os.getenv("QUENTIN_COUNCIL_LOCAL_FAST_PATH_COUNCILS", "planner,done,pre_sensing")
            ).split(",")
            if x.strip()
        }
        normalized_name = str(council_name or "").strip().lower()
        if normalized_name not in allowed:
            return False
        # Done council should not be force-short-circuited by default.
        # Otherwise local runtime can be permanently stuck at NOT_DONE without real adjudication.
        if normalized_name == "done":
            done_fast_path_flag = str(
                os.getenv("QUENTIN_COUNCIL_LOCAL_FAST_PATH_DONE", "0") or ""
            ).strip().lower()
            if done_fast_path_flag not in {"1", "true", "yes", "on"}:
                return False

        return True

    def _build_local_fast_path_reply(
        self,
        *,
        council_name: str,
        question: CouncilQuestion,
    ) -> Dict[str, Any]:
        council = str(council_name or "").strip().lower()
        topic = str(question.topic or "").strip().lower()
        if council == "pre_sensing" or topic == "pre_sensing":
            return {
                "verdict": "not_done",
                "evidence_summary": "local_fast_path_without_remote_llm",
                "confidence": 0.0,
            }
        if council == "planner" or topic == "planner":
            return {
                "verdict": "ok",
                "reasoning": "local_fast_path_minimal_plan",
                "answer": {
                    "steps": [
                        {
                            "step_id": "s1",
                            "description": "Analyze objective and execute the safest next action",
                            "skill_id": None,
                            "notes": "local_fast_path",
                        }
                    ]
                },
            }
        if council == "done" or topic == "done_check":
            return {
                "verdict": "not_done",
                "is_done": False,
                "reasoning": "local_fast_path_requires_real_execution_evidence",
            }
        return {
            "verdict": "undecided",
            "reasoning": "local_fast_path_generic_fallback",
            "answer": {},
        }

    def _ask_member(
        self,
        *,
        cfg: CouncilConfig,
        member: CouncilMemberConfig,
        question: CouncilQuestion,
        complexity: str,
        force_model: Optional[str],
        escalation_reason: str,
        fallback_chain: List[str],
    ) -> str:
        route_task_type = self._resolve_council_task_type(member.router_task_type, complexity=complexity)
        route = self.model_router.route(mode=member.router_mode, task_type=route_task_type)
        if force_model:
            route.name = force_model
        base_system_prompt = (
            f"You are a council member with role '{member.role}'.\n"
            f"Council: {cfg.name}. Topic: {question.topic}. Importance: {question.importance}.\n"
            "Return your answer as a JSON object when possible.\n"
        )
        payload = question.payload if isinstance(question.payload, dict) else {}
        layer_payload = payload.get("prompt_layers") if isinstance(payload.get("prompt_layers"), dict) else {}
        phase_system_prompt = str(payload.get("phase_system_prompt") or "").strip()
        if phase_system_prompt:
            system_prompt = phase_system_prompt
        else:
            system_prompt = build_layered_system_prompt(
                base_system=base_system_prompt,
                soul=str(layer_payload.get("soul") or ""),
                skill=str(layer_payload.get("skill_context") or ""),
                project_context=str(layer_payload.get("project_context") or ""),
                hints=list(layer_payload.get("hints") or []),
            )
        user_prompt = json.dumps(
            {
                "prompt": question.prompt,
                "payload": question.payload,
            },
            ensure_ascii=False,
            indent=2,
            cls=SafeJSONEncoder,
        )
        return call_llm(
            route,
            user_prompt=user_prompt,
            system_prompt=system_prompt,
            timeout=_resolve_council_timeout_for_route(route=route, is_arbiter=False),
            safety_kernel=getattr(route, "safety_kernel", None),
            actor=f"council_member:{cfg.name}:{member.member_id}",
            domain=str((question.payload or {}).get("goal", {}).get("domain") or "core"),
            environment=str((question.payload or {}).get("goal", {}).get("environment") or "sandbox"),
            risk_level="medium",
            action_metadata={
                "router_mode": getattr(route, "router_mode", member.router_mode),
                "router_task_type": getattr(route, "router_task_type", route_task_type),
                "council_name": cfg.name,
                "member_id": member.member_id,
                "member_role": member.role,
                "topic": question.topic,
                "routing_tier": complexity,
                "forced_model": bool(force_model),
                "escalation_reason": str(escalation_reason or ""),
                "fallback_chain": list(fallback_chain or []),
            },
            provider=getattr(route, "provider", None),
            model_name=getattr(route, "name", None) or getattr(route, "model", None),
        )

    def _aggregate_decision(
        self,
        *,
        cfg: CouncilConfig,
        question: CouncilQuestion,
        replies: List[CouncilMemberReply],
    ) -> Tuple[Dict[str, Any], Optional[str]]:
        force_first = (os.getenv("QUENTIN_COUNCIL_FORCE_FIRST", "0") or "").strip().lower() in {"1", "true", "yes", "on"}
        mode = "first" if force_first else str(cfg.decision_mode or "first").lower()
        if mode in ("first", "single", "member_first"):
            for r in replies:
                if isinstance(r.parsed, dict) and r.parsed:
                    return r.parsed, None
            # fallback: wrap raw
            return {"answer": replies[0].raw_output if replies else "", "verdict": "undecided"}, None

        # arbiter_llm: ask a final LLM to merge.
        arb_mode = cfg.arbiter_router_mode or cfg.members[0].router_mode
        arb_task = cfg.arbiter_router_task_type or cfg.members[0].router_task_type
        route = self.model_router.route(mode=arb_mode, task_type=arb_task)
        try:
            max_member_raw = int(os.getenv("QUENTIN_COUNCIL_ARBITER_MEMBER_RAW_MAX_CHARS", "1200"))
        except Exception:
            max_member_raw = 1200
        try:
            max_member_parsed = int(os.getenv("QUENTIN_COUNCIL_ARBITER_MEMBER_PARSED_MAX_CHARS", "2500"))
        except Exception:
            max_member_parsed = 2500
        try:
            max_question_prompt = int(os.getenv("QUENTIN_COUNCIL_ARBITER_QUESTION_PROMPT_MAX_CHARS", "1600"))
        except Exception:
            max_question_prompt = 1600
        try:
            max_question_payload = int(os.getenv("QUENTIN_COUNCIL_ARBITER_QUESTION_PAYLOAD_MAX_CHARS", "2400"))
        except Exception:
            max_question_payload = 2400

        compact_question = {
            "topic": question.topic,
            "importance": question.importance,
            "prompt": _truncate_text(question.prompt, max_question_prompt),
            "payload": _compact_json_value(question.payload, max_chars=max_question_payload),
        }
        compact_replies = []
        for r in replies:
            compact_replies.append(
                {
                    "member_id": r.member_id,
                    "error": r.error,
                    "parsed": _compact_json_value(r.parsed, max_chars=max_member_parsed),
                    "raw_output": _truncate_text(r.raw_output, max_member_raw),
                }
            )
        user_prompt = json.dumps(
            {
                "question": compact_question,
                "member_replies": compact_replies,
                "instructions": (
                    "You are the council arbiter. Merge member replies into ONE JSON object.\n"
                    "Return only JSON. If members disagree, pick the safest option and explain in 'reasoning'.\n"
                ),
            },
            ensure_ascii=False,
            indent=2,
            cls=SafeJSONEncoder,
        )
        payload = question.payload if isinstance(question.payload, dict) else {}
        layer_payload = payload.get("prompt_layers") if isinstance(payload.get("prompt_layers"), dict) else {}
        phase_system_prompt = str(payload.get("phase_system_prompt") or "").strip()
        if phase_system_prompt:
            system_prompt = phase_system_prompt
        else:
            system_prompt = build_layered_system_prompt(
                base_system=f"You are the arbiter for council '{cfg.name}'. Return only JSON.",
                soul=str(layer_payload.get("soul") or ""),
                skill=str(layer_payload.get("skill_context") or ""),
                project_context=str(layer_payload.get("project_context") or ""),
                hints=list(layer_payload.get("hints") or []),
            )
        try:
            raw = call_llm(
                route,
                user_prompt=user_prompt,
                system_prompt=system_prompt,
                timeout=_resolve_council_timeout_for_route(route=route, is_arbiter=True),
                actor=f"council_arbiter:{cfg.name}",
                domain=str((question.payload or {}).get("goal", {}).get("domain") or "core"),
                environment=str((question.payload or {}).get("goal", {}).get("environment") or "sandbox"),
                risk_level="medium",
                action_metadata={
                    "router_mode": getattr(route, "router_mode", arb_mode),
                    "router_task_type": getattr(route, "router_task_type", arb_task),
                    "council_name": cfg.name,
                    "topic": question.topic,
                },
                provider=getattr(route, "provider", None),
                model_name=getattr(route, "name", None) or getattr(route, "model", None),
            )
        except Exception as e:  # noqa: BLE001
            logger.warning("CouncilManager: arbiter call failed: council=%s error=%s", cfg.name, e)
            # Fallback to first valid member reply if arbiter times out/fails.
            for reply in replies:
                if isinstance(reply.parsed, dict) and reply.parsed:
                    return reply.parsed, None
            raw = "{}"

        parsed, _err = _parse_jsonish(raw)
        if isinstance(parsed, dict) and parsed:
            return parsed, raw
        return {"answer": raw, "verdict": "undecided"}, raw

    @staticmethod
    def _classify_question_complexity(question: CouncilQuestion) -> str:
        prompt = str(question.prompt or "")
        payload = question.payload if isinstance(question.payload, dict) else {}
        # Use SafeJSONEncoder to handle CancellationToken etc.
        payload_text = json.dumps(payload, ensure_ascii=False, cls=SafeJSONEncoder)
        text = (prompt + "\n" + payload_text).lower()
        score = 0
        for marker in ("refactor", "architecture", "tradeoff", "constraint", "rollback", "security", "multi-step"):
            if marker in text:
                score += 1
        if len(text) > 1800:
            score += 1
        if score >= 3:
            return "reasoning_heavy"
        if score >= 1:
            return "edit_heavy"
        return "simple"

    @staticmethod
    def _resolve_council_task_type(original: str, *, complexity: str) -> str:
        base = str(original or "core")
        if complexity == "reasoning_heavy":
            return "reasoning_heavy"
        if complexity == "simple":
            return "simple_edit"
        return base
