from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List, Optional, Union
import json
import logging
import os
import inspect

from quentin.router.metrics import (
    ModelRouteDecisionRecord,
    ModelRouteOutcomeRecord,
    ModelRouteRequestRecord,
    ModelRouterLogStore,
)
from quentin.traces.core import JsonlTraceRecorder, TraceEventType, new_trace_event

logger = logging.getLogger(__name__)

def _normalize_ollama_base_url(raw: Optional[str]) -> str:
    base = str(raw or "").strip()
    if not base:
        return "http://localhost:11434"
    base = base.rstrip("/")
    for suffix in ("/api/generate", "/api/chat", "/api/embeddings"):
        if base.endswith(suffix):
            return base[: -len(suffix)]
    return base


@dataclass
class ModelInfo:
    name: str
    kind: str  # "openai" / "ollama" / "anthropic" / "local" / ...
    cost_per_1k_tokens: float = 0.0
    latency_hint_ms: int = 1000
    domains: List[str] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)


@dataclass
class ModelUsageStats:
    calls: int = 0
    total_tokens: int = 0
    total_cost: float = 0.0
    total_latency_ms: int = 0
    last_called_at: Optional[datetime] = None


@dataclass
class ModelRouteRequest:
    """
    Structured route request (preferred API).
    """

    task_type: str
    importance: str = "normal"
    domain: str = "general"
    constraints: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_record(self) -> ModelRouteRequestRecord:
        return ModelRouteRequestRecord(
            task_type=self.task_type,
            importance=self.importance,
            domain=self.domain,
            constraints=self.constraints,
            metadata=self.metadata,
        )


@dataclass
class ModelRouteDecision:
    model_id: str
    provider: str
    reason: str
    params: Dict[str, Any] = field(default_factory=dict)

    def to_record(self) -> ModelRouteDecisionRecord:
        return ModelRouteDecisionRecord(
            model_id=self.model_id,
            provider=self.provider,
            reason=self.reason,
            params=self.params,
        )

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class ModelRouterConfig:
    """
    Configuration container for simple mapping-based routing.
    """

    def __init__(self, raw: Optional[Dict[str, Any]] = None) -> None:
        cfg = raw or {}
        self.default_model: str = cfg.get("default_model", os.getenv("LLM_MODEL"))
        if not self.default_model:
            # We don't raise here yet to allow manual config injection, 
            # but usually it should be set.
            pass
        self.safe_model: str = cfg.get("safe_model", self.default_model)
        self.cheap_model: str = cfg.get("cheap_model", self.default_model)
        self.by_task_type: Dict[str, str] = cfg.get("by_task_type", {}) or {}
        self.by_domain: Dict[str, str] = cfg.get("by_domain", {}) or {}
        self.extra: Dict[str, Any] = cfg.get("extra", {}) or {}

    def to_dict(self) -> Dict[str, Any]:
        return {
            "default_model": self.default_model,
            "safe_model": self.safe_model,
            "cheap_model": self.cheap_model,
            "by_task_type": dict(self.by_task_type),
            "by_domain": dict(self.by_domain),
            "extra": dict(self.extra),
        }


class ModelRouter:
    """
    Unified ModelRouter (canonical: `quentin.routing.model_router`).

    Goals:
    - One stable import path for the project (`ModelRouter`, `ModelInfo`, `ModelRouteRequest`, ...)
    - Backward compatibility:
      - `route(mode=..., task_type=...)` used by `CouncilManager` (returns a SimpleNamespace)
      - `choose_model(...)` / `record_usage(...)` used by older components
      - `route(ModelRouteRequest, ...)` used by newer code (returns `ModelRouteDecision`)
    """

    def __init__(
        self,
        *,
        repo_root: str | Path = ".",
        base_config: Optional[Dict[str, Any]] = None,
        log_store: Optional[ModelRouterLogStore] = None,
        rules_path: str | Path = "config/model_router_rules.json",
        models: Optional[Dict[str, ModelInfo]] = None,
        backend_call: Optional[Any] = None,
        trace_recorder: Optional[JsonlTraceRecorder] = None,
    ) -> None:
        self.repo_root = Path(repo_root).resolve()
        self.config = ModelRouterConfig(base_config)
        self.log_store = log_store or ModelRouterLogStore(repo_root=self.repo_root)
        
        # Ensure rules_path is relative to repo_root if not absolute
        rp = Path(rules_path)
        if not rp.is_absolute():
            rp = self.repo_root / rp
        self.rules_path = rp
        self.backend_call = backend_call
        self.trace_recorder = trace_recorder or JsonlTraceRecorder(repo_root=str(self.repo_root))

        self.models: Dict[str, ModelInfo] = dict(models or {})
        self.stats: Dict[str, ModelUsageStats] = {}
        self._rules: Dict[str, Dict[str, Any]] = {}

        if not self.models:
            default_model = os.getenv("LLM_MODEL")
            if not default_model:
                raise ValueError("Environment variable LLM_MODEL is not set.")
            self.register_model(
                ModelInfo(
                    name=default_model,
                    kind=_infer_provider_from_model_id(default_model),
                    domains=["core", "general"],
                    tags=["default"],
                )
            )
            logger.info("ModelRouter: auto-registered default model %s", default_model)

        self._load_rules()

    def __call__(self, prompt: str, **kwargs: Any) -> str:
        """
        Make the router usable as an L1 "LLM-like callable".

        This enables running the full L3->L2->L1 feedback loop locally:
        - L3 promotes router rules
        - L1 calls runtime.model_router(prompt)
        - The chosen model is recorded in the output (and optionally executed via backend_call)
        """
        task_type = str(kwargs.get("task_type") or kwargs.get("mode") or "chat")
        preference = str(kwargs.get("preference") or "balanced")
        domain = str(kwargs.get("domain") or kwargs.get("task_domain") or "general")

        model_id = self.choose_model(task_type=task_type, domain=domain, preference=preference) or self.config.default_model
        try:
            self.trace_recorder.record_event(
                new_trace_event(
                    trace_id="model_router",
                    event_type=TraceEventType.MODEL_CALL,
                    payload={
                        "action": "route",
                        "task_type": task_type,
                        "preference": preference,
                        "domain": domain,
                        "model_id": model_id,
                    },
                )
            )
        except Exception:
            pass

        # Optionally call a provider backend. This is best-effort and intentionally flexible
        # to accommodate different signatures used across this repo.
        if self.backend_call is not None:
            try:
                return self.backend_call(model_id, prompt, **kwargs)
            except TypeError:
                try:
                    provider = _infer_provider_from_model_id(model_id)
                    return self.backend_call(provider=provider, model_id=model_id, prompt=prompt, **kwargs)
                except Exception:
                    pass
            except Exception:
                pass

        return f"[{model_id}] {str(prompt)[:400]}"

    # --------------------------------------------------------------------- rules
    def _load_rules(self) -> None:
        if not self.rules_path.exists():
            self._rules = {}
            return
        try:
            self._rules = json.loads(self.rules_path.read_text(encoding="utf-8") or "{}") or {}
        except Exception:
            logger.exception("ModelRouter: failed to load rules from %s", self.rules_path)
            self._rules = {}

    def reload_rules(self) -> None:
        self._load_rules()

    # --------------------------------------------------------------------- catalog
    def register_model(self, info: ModelInfo) -> None:
        self.models[info.name] = info
        self.stats.setdefault(info.name, ModelUsageStats())

    def list_models(self) -> List[ModelInfo]:
        return list(self.models.values())

    # --------------------------------------------------------------------- legacy API
    def choose_model(
        self,
        task_type: str,
        domain: Optional[str] = None,
        preference: str = "balanced",  # "speed" | "cost" | "quality" | "balanced"
    ) -> Optional[str]:
        task_t = str(task_type or "").lower()
        high_tier = str(os.getenv("QUENTIN_HIGH_TIER_MODEL") or "").strip()
        low_tier = str(os.getenv("QUENTIN_LOW_TIER_MODEL") or "").strip()

        if task_t in {"reasoning_heavy", "complex_refactor", "high_reasoning"} and high_tier:
            if high_tier in self.models:
                return high_tier
        if task_t in {"simple_edit", "read_write_basic", "low_reasoning"} and low_tier:
            if low_tier in self.models:
                return low_tier

        # 0) Rule overrides: key is "mode::task_type".
        route_key = f"{str(preference).lower()}::{task_t}"
        rule = self._rules.get(route_key)
        if isinstance(rule, dict):
            model = rule.get("model")
            if isinstance(model, str) and model:
                return model

        preferred_env = os.getenv("LLM_MODEL")
        if preferred_env and preferred_env in self.models:
            return preferred_env

        candidates = list(self.models.values())
        if domain:
            filtered = [m for m in candidates if domain in (m.domains or [])]
            if filtered:
                candidates = filtered

        if not candidates:
            return None

        pref = str(preference).lower()
        if pref == "speed":
            candidates.sort(key=lambda m: m.latency_hint_ms)
        elif pref == "cost":
            candidates.sort(key=lambda m: m.cost_per_1k_tokens)
        else:
            candidates.sort(key=lambda m: m.name)

        return candidates[0].name

    def record_usage(self, model_name: str, tokens: int, latency_ms: int) -> None:
        s = self.stats.setdefault(model_name, ModelUsageStats())
        s.calls += 1
        s.total_tokens += int(tokens or 0)
        s.total_latency_ms += int(latency_ms or 0)
        info = self.models.get(model_name)
        cost_per_1k = info.cost_per_1k_tokens if info else 0.0
        s.total_cost += (float(tokens or 0) / 1000.0) * float(cost_per_1k or 0.0)
        s.last_called_at = datetime.now(timezone.utc)

    async def get_stats(self, limit: int = 2000) -> Dict[str, Any]:
        models_by_name: Dict[str, Any] = {}
        for name, info in self.models.items():
            s = self.stats.get(name, ModelUsageStats())
            avg_latency_ms = (s.total_latency_ms / s.calls) if s.calls else None
            avg_cost = (s.total_cost / s.calls) if s.calls else None
            models_by_name[name] = {
                "kind": info.kind,
                "domains": info.domains,
                "tags": info.tags,
                "calls": s.calls,
                "total_tokens": s.total_tokens,
                "total_cost": s.total_cost,
                "avg_latency_ms": avg_latency_ms,
                "avg_latency_sec": (avg_latency_ms / 1000.0) if avg_latency_ms is not None else None,
                "avg_cost": avg_cost,
            }
        total_calls = sum(m["calls"] for m in models_by_name.values())

        # Backward-friendly: keep `models` as a list for older multi-agent code,
        # but also return a stable `models_by_name` mapping for newer call sites.
        models_list = []
        for name, m in models_by_name.items():
            models_list.append(
                {
                    "model_name": name,
                    **m,
                }
            )

        return {"models": models_list, "models_by_name": models_by_name, "total_calls": total_calls}

    async def call_best_model(
        self,
        *,
        task_type: str,
        prompt: str,
        preferred_model: Optional[str] = None,
        extra_meta: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Minimal async API used by some legacy components.

        If `backend_call` is not configured, returns a deterministic stub string.
        """
        extra_meta = extra_meta or {}

        model_name = preferred_model if preferred_model in self.models else None
        if not model_name:
            model_name = self.choose_model(task_type=task_type, domain=extra_meta.get("domain"), preference="balanced")
        if not model_name:
            model_name = self._fallback_any_model()

        provider = self.models.get(model_name).kind if model_name in self.models else _infer_provider_from_model_id(model_name)

        started = datetime.now(timezone.utc)
        success = True
        error: Optional[str] = None
        out = ""
        try:
            if self.backend_call is None:
                out = f"[ModelRouter backend_call not configured] provider={provider} model={model_name} task_type={task_type}"
            else:
                messages = [{"role": "user", "content": prompt}]
                res = self.backend_call(model_name, messages, {"provider": provider, **extra_meta})
                out = await res if inspect.isawaitable(res) else str(res)
        except Exception as e:  # noqa: BLE001
            success = False
            error = repr(e)
            out = f"[ModelRouter error] {e}"

        # very rough token estimate
        tokens = (len(prompt) + len(out)) // 4
        latency_ms = int((datetime.now(timezone.utc) - started).total_seconds() * 1000)
        self.record_usage(model_name, tokens=tokens, latency_ms=latency_ms)

        if not success:
            logger.warning("ModelRouter.call_best_model failed: model=%s error=%s", model_name, error)

        return out

    async def choose_and_call(
        self,
        route_info: Dict[str, Any],
        messages: List[Dict[str, Any]],
        task_type: str = "generic",
        preferred_model: Optional[str] = None,
        extra_meta: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Legacy compatibility API used by older orchestration code (the old `quentin/base` layer has been removed).

        - `route_info`: typically includes `domain` and a coarse `priority`/`preference`.
        - `messages`: chat-style messages.
        """
        extra_meta = {**(extra_meta or {}), **(route_info or {})}
        domain = extra_meta.get("domain")
        preference = str(extra_meta.get("priority") or extra_meta.get("preference") or "balanced")

        model_name = preferred_model if preferred_model in self.models else None
        if not model_name:
            model_name = self.choose_model(task_type=task_type, domain=domain, preference=preference)
        if not model_name:
            model_name = self._fallback_any_model()

        provider = self.models.get(model_name).kind if model_name in self.models else _infer_provider_from_model_id(model_name)

        started = datetime.now(timezone.utc)
        success = True
        error: Optional[str] = None
        out = ""
        try:
            if self.backend_call is None:
                out = f"[ModelRouter backend_call not configured] provider={provider} model={model_name} task_type={task_type}"
            else:
                res = self.backend_call(model_name, messages, {"provider": provider, **extra_meta})
                out = await res if inspect.isawaitable(res) else str(res)
        except Exception as e:  # noqa: BLE001
            success = False
            error = repr(e)
            out = f"[ModelRouter error] {e}"

        # rough token estimate based on message + output length
        msg_chars = sum(len(str(m.get("content") or "")) for m in (messages or []))
        tokens = (msg_chars + len(out)) // 4
        latency_ms = int((datetime.now(timezone.utc) - started).total_seconds() * 1000)
        self.record_usage(model_name, tokens=tokens, latency_ms=latency_ms)

        if not success:
            logger.warning("ModelRouter.choose_and_call failed: model=%s error=%s", model_name, error)

        return out

    # --------------------------------------------------------------------- unified API
    def route(
        self,
        request: Optional[ModelRouteRequest] = None,
        *,
        runtime_flags: Optional[Dict[str, Any]] = None,
        variant_params: Optional[Dict[str, Any]] = None,
        mode: str = "",
        task_type: str = "generic",
    ) -> Union[ModelRouteDecision, Any]:
        """
        Unified entrypoint:
        - If `request` is provided -> returns `ModelRouteDecision` (structured routing).
        - Else -> legacy mode for councils: returns a SimpleNamespace with `name`, `provider`, ...
        """
        from quentin.llm.auth_profiles import get_auth_manager
        auth_mgr = get_auth_manager()

        if request is None:
            # P3-C: Pluggable Routing Policies (Blueprint v3 canonical env: QUENTIN_ROUTING_POLICY)
            name = None
            policy_id = (os.getenv("QUENTIN_ROUTING_POLICY") or "").strip().lower()
            enable_legacy_flag = os.getenv("QUENTIN_ROUTING_POLICY_PLUGINS") == "1"
            use_policy = bool(policy_id) or enable_legacy_flag
            if use_policy:
                if not policy_id:
                    policy_id = "default"
                try:
                    from quentin.models.routing_policies import get_routing_policy_registry, bootstrap_routing_policies

                    reg = get_routing_policy_registry()
                    if not reg.list_policies():
                        bootstrap_routing_policies(router=self)

                    metadata = {"mode": mode, "task_type": task_type}
                    info = reg.route_id(policy_id, mode=mode, task_type=task_type, metadata=metadata) or reg.route(
                        mode=mode, task_type=task_type, metadata=metadata
                    )
                    if info and getattr(info, "name", None):
                        name = str(info.name)
                except Exception:
                    pass

            if not name:
                name = self.choose_model(task_type=task_type, domain=(mode or None), preference="balanced")
            
            if not name:
                name = next(iter(self.models.keys()), os.getenv("LLM_MODEL"))
            if not name:
                raise ValueError("No models registered and LLM_MODEL env var is not set.")
            provider = self.models.get(name).kind if name in self.models else _infer_provider_from_model_id(name)
            
            # --- [5.4] Auth Profile Integration ---
            profile = auth_mgr.get_best_profile(provider)
            base_url = profile.base_url if profile and profile.base_url else os.getenv("LLM_BASE_URL", "http://localhost:11434")
            if str(provider or "").strip().lower() == "ollama":
                base_url = _normalize_ollama_base_url(base_url)
            api_key = profile.api_key if profile else os.getenv("OPENAI_API_KEY", "no-key")

            return SimpleNamespace(
                name=name,
                provider=provider,
                base_url=base_url,
                api_key=api_key,
                profile_id=profile.profile_id if profile else "default",
                router_mode=str(mode or ""),
                router_task_type=str(task_type or ""),
            )

        flags = runtime_flags or {}
        params = variant_params or {}

        degrade_mode = bool(flags.get("degrade_mode", False))
        cost_sensitive = bool(params.get("cost_sensitive", False))
        safety_sensitive = bool(params.get("safety_sensitive", False))

        model_id = self._select_model_id(request, degrade_mode, cost_sensitive, safety_sensitive)
        provider = self.models.get(model_id).kind if model_id in self.models else _infer_provider_from_model_id(model_id)

        reason_parts: List[str] = []
        if degrade_mode:
            reason_parts.append("degrade_mode")
        if cost_sensitive:
            reason_parts.append("cost_sensitive")
        if safety_sensitive:
            reason_parts.append("safety_sensitive")
        if not reason_parts:
            reason_parts.append("default_routing")

        decision = ModelRouteDecision(
            model_id=model_id,
            provider=provider,
            reason=",".join(reason_parts),
            params={
                "degrade_mode": degrade_mode,
                "cost_sensitive": cost_sensitive,
                "safety_sensitive": safety_sensitive,
            },
        )

        try:
            self.log_store.append(
                request=request.to_record(),
                decision=decision.to_record(),
                outcome=ModelRouteOutcomeRecord(),
                runtime_flags=flags,
                experiment_tags=params.get("experiment_tags") or {},
            )
        except Exception:
            logger.exception("ModelRouter.route: failed to log route record")

        return decision

    def record_feedback(
        self,
        *,
        request: ModelRouteRequest,
        decision: ModelRouteDecision,
        outcome: ModelRouteOutcomeRecord,
        runtime_flags: Optional[Dict[str, Any]] = None,
        experiment_tags: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Append a route log record with a real outcome (success/cost/latency/quality_score).
        """
        self.log_store.append(
            request=request.to_record(),
            decision=decision.to_record(),
            outcome=outcome,
            runtime_flags=runtime_flags or {},
            experiment_tags=experiment_tags or {},
        )

    # --------------------------------------------------------------------- internal
    def _select_model_id(
        self,
        request: ModelRouteRequest,
        degrade_mode: bool,
        cost_sensitive: bool,
        safety_sensitive: bool,
    ) -> str:
        # degrade_mode: always safe_model
        if degrade_mode:
            return self._resolve_registered(self.config.safe_model) or self._fallback_any_model()

        # safety first
        if safety_sensitive or request.domain.lower() in ("legal", "compliance"):
            return self._resolve_registered(self.config.safe_model) or self._fallback_any_model()

        # cost first
        if cost_sensitive or request.constraints.get("budget") == "low":
            return self._resolve_registered(self.config.cheap_model) or self._fallback_any_model()

        if request.task_type in self.config.by_task_type:
            return self._resolve_registered(self.config.by_task_type[request.task_type]) or self._fallback_any_model()

        if request.domain in self.config.by_domain:
            return self._resolve_registered(self.config.by_domain[request.domain]) or self._fallback_any_model()

        return self._resolve_registered(self.config.default_model) or self._fallback_any_model()

    def _resolve_registered(self, model_id: str) -> Optional[str]:
        if model_id in self.models:
            return model_id
        # allow config to specify "tags:safe" etc in future; for now best-effort.
        return None

    def _fallback_any_model(self) -> str:
        model = next(iter(self.models.keys()), os.getenv("LLM_MODEL"))
        if not model:
             raise ValueError("No models registered and LLM_MODEL env var is not set.")
        return model


def _infer_provider_from_model_id(model_id: str) -> str:
    mid = (model_id or "").lower()
    if "gpt" in mid or "openai" in mid:
        return "openai"
    if "claude" in mid or "anthropic" in mid:
        return "anthropic"
    if "deepseek" in mid:
        return "deepseek"
    if "gemini" in mid or "google" in mid:
        return "gemini"
    if "qwen" in mid or ":" in mid:
        return "ollama"
    return "unknown"
