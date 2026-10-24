# quentin/l3/research/interface.py
from __future__ import annotations

from typing import Any, Dict, List, Optional
import logging

from quentin.immune.store import ImmuneCase

logger = logging.getLogger(__name__)


from quentin.l3.research.experiments import ExperimentStore, VariantConfig
from quentin.l3.research.orchestrator import ExperimentOrchestrator
from quentin.l3.research.runners.planner_offline_runner import PlannerOfflineRunner
from quentin.l3.research.runners.model_router_offline_runner import ModelRouterOfflineRunner
from quentin.l3.research.runners.skill_eval_runner import SkillEvalRunner
from quentin.l3.research.runners.skill_evolution_runner import SkillEvolutionRunner
from quentin.l3.research.runners.patch_eval_runner import PatchEvalRunner # NEW
from quentin.self_programming.engine import SelfProgrammingEngine
from quentin.l3.research.runners.patch_test_runner import PatchTestRunner
from quentin.l3.research.runners.skill_candidate_runner import SkillCandidateRunner

logger = logging.getLogger(__name__)


class ResearchInterface:
    """
    v1：一个轻量的 Research Layer 接口壳子 + ExperimentOrchestrator 适配层。

    主要职责：
    - 接收 ImmuneCase，做统一入口（当前打日志 + 可选自动生成实验）
    - 对上层暴露 create_experiment / run_experiment / compare_variants 等方法
    """

    def __init__(
        self,
        *,
        repo_root: str | None = None,
        orchestrator: Optional[ExperimentOrchestrator] = None,
        store: Optional[ExperimentStore] = None,
    ) -> None:
        from pathlib import Path

        self.repo_root = Path(repo_root or ".").resolve()
        self.store = store or ExperimentStore(repo_root=self.repo_root)
        self.orchestrator = orchestrator or ExperimentOrchestrator(
            repo_root=self.repo_root,
            store=self.store,
        )

        # SelfProgrammingEngine may have a minimal signature; ignore extra kwargs if unsupported.
        try:
            self.self_programming_engine = SelfProgrammingEngine(
                repo_root=self.repo_root,
                experiment_store=self.store,
                experiment_orchestrator=self.orchestrator,
            )
        except TypeError:
            try:
                self.self_programming_engine = SelfProgrammingEngine()
            except Exception:
                self.self_programming_engine = None

        # ✅ 默认注册一个 planner 的离线 Runner（使用 stub_planner_fn）
        try:
            planner_runner = PlannerOfflineRunner()
            self.orchestrator.register_runner("planner", planner_runner)
        except Exception:
            logger.exception("ResearchInterface: failed to register default PlannerOfflineRunner")
            
        # ✅ 默认注册一个 model_router 的离线 Runner（使用 stub_model_router_fn）
        try:
            model_router_runner = ModelRouterOfflineRunner()
            self.orchestrator.register_runner("model_router", model_router_runner)
        except Exception:
            logger.exception("ResearchInterface: failed to register default ModelRouterOfflineRunner")

        # ✅ 默认注册一个 skill_eval 的离线 Runner
        try:
            skill_eval_runner = SkillEvalRunner()
            self.orchestrator.register_runner("skill_eval", skill_eval_runner)
        except Exception:
            logger.exception("ResearchInterface: failed to register default SkillEvalRunner")
            
        # ✅ 默认注册一个 skill_evolution 的离线 Runner
        try:
            allow_stub = os.getenv("ALLOW_STUB_RESEARCH_RUNNERS", "0").lower() in {"1", "true", "yes"}
            if allow_stub:
                skill_evolution_runner = SkillEvolutionRunner()
                self.orchestrator.register_runner("skill_evolution", skill_evolution_runner)
            else:
                logger.info("ResearchInterface: skip registering SkillEvolutionRunner (disabled by default)")
        except Exception:
            logger.exception("ResearchInterface: failed to register default SkillEvolutionRunner")

        # ✅ 默认注册一个 patch_eval 的离线 Runner
        try:
            allow_stub = os.getenv("ALLOW_STUB_RESEARCH_RUNNERS", "0").lower() in {"1", "true", "yes"}
            if allow_stub:
                patch_eval_runner = PatchEvalRunner()
                self.orchestrator.register_runner("patch_eval", patch_eval_runner)
            else:
                logger.info("ResearchInterface: skip registering PatchEvalRunner (disabled by default)")
        except Exception:
            logger.exception("ResearchInterface: failed to register default PatchEvalRunner")

        # ✅ PatchTestRunner
        try:
            patch_runner = PatchTestRunner(engine=self.self_programming_engine)
            self.orchestrator.register_runner("patch_test", patch_runner)
        except Exception:
            logger.exception("ResearchInterface: failed to register PatchTestRunner")

        # ✅ SkillCandidateRunner
        try:
            skill_runner = SkillCandidateRunner(engine=self.self_programming_engine)
            self.orchestrator.register_runner("skill_candidate", skill_runner)
        except Exception:
            logger.exception("ResearchInterface: failed to register SkillCandidateRunner")

    # ---- ImmuneCase 接口 ---- #
    def submit_immune_case(self, case: ImmuneCase) -> None:
        """
        ImmuneLoop 检测到异常后调用：
        - 当前：打日志；
        - 将来：可以自动生成实验，或推送到队列，由人/AI 决定是否开实验。
        """
        logger.info(
            "ResearchInterface: received immune case %s (type=%s severity=%s)",
            case.case_id,
            case.anomaly.get("anomaly_type"),
            case.anomaly.get("severity"),
        )
        # v1 不自动建实验，只是记录。
        # 若你想试验“全自动自演化”，可以在这里调用 create_experiment_from_case。

    # ---- 实验 API ---- #
    def create_experiment_from_case(self, case: ImmuneCase) -> str:
        """
        根据 ImmuneCase 创建一个简单的实验占位：
        比如：
        - 目标组件：planner / model_router / skill_evolution 等
        - 暂时创建两个占位 Variant（baseline / candidate），后续可以由 AI 来填充 params。
        """
        anomaly_type = case.anomaly.get("anomaly_type", "unknown")
        target_component = self._infer_target_component_from_case(case)

        name = f"auto_from_case_{case.case_id[:8]}"
        purpose = f"Auto experiment derived from immune case {case.case_id} ({anomaly_type})"

        # v1: 先生成两个占位 Variant，具体 params 由你后续填
        variants = [
            VariantConfig(
                variant_id="baseline",
                name="baseline",
                description="Current / previous stable configuration",
                target_component=target_component,
                params={"mode": "baseline"},
            ),
            VariantConfig(
                variant_id="candidate",
                name="candidate",
                description="New configuration to try (to be filled by AI/human).",
                target_component=target_component,
                params={"mode": "candidate"},
            ),
        ]

        cfg = self.orchestrator.create_experiment(
            name=name,
            purpose=purpose,
            target_component=target_component,
            created_by="immune_auto",
            metadata={
                "source_case_id": case.case_id,
                "anomaly_type": anomaly_type,
            },
            variants=variants,
        )
        logger.info(
            "ResearchInterface: created experiment %s from immune case %s",
            cfg.experiment_id,
            case.case_id,
        )
        return cfg.experiment_id

    def run_experiment(self, experiment_id: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        运行某个实验，并返回结果的 dict。
        """
        result = self.orchestrator.run_experiment(experiment_id, context=context)
        return result.to_dict()

    def compare_variants(
        self,
        experiment_id: str,
        metric_name: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        比较实验中的各变体表现。
        """
        return self.orchestrator.compare_variants(experiment_id, metric_name=metric_name)

    def eval_patches(self, patch_ids: List[str], *, test_suites=None, extra_context=None):
        exp = self.self_programming_engine.create_patch_experiment(patch_ids=patch_ids)
        return self.self_programming_engine.run_patch_experiment(
            exp.experiment_id,
            test_suites=test_suites,
            extra_context=extra_context,
        )

    def eval_skill_candidates(self, candidate_ids: List[str], *, context=None):
        exp = self.self_programming_engine.create_skill_experiment(candidate_ids=candidate_ids)
        return self.self_programming_engine.run_skill_experiment(
            exp.experiment_id,
            context=context,
        )

    # ---- 内部辅助 ---- #
    def _infer_target_component_from_case(self, case: ImmuneCase) -> str:
        """
        从 ImmuneCase 推断目标组件。
        v1: 极简版——只看 anomaly_type 和 goal_summary.domain。
        将来可以接更智能的推断（甚至让 AI 决定）。
        """
        domain = (case.goal_summary.get("domain") or "").lower()
        anomaly_type = case.anomaly.get("anomaly_type", "")

        # 示例规则：Trading 域优先给 model_router / risk_manager 做实验
        if "trading" in domain:
            return "model_router"
        # Legal 域优先给 planner / reasoning 做实验
        if "legal" in domain:
            return "planner"
        # 其他默认 planner
        if "high_failure_rate" in anomaly_type:
            return "planner"
        return "planner"


# ---------------------------------------------------------------------------
# v3 canonical Research API wrapper (blueprint v3)
# ---------------------------------------------------------------------------

class ResearchInterfaceV3:
    """
    Canonical stable Research API surface (v3):

    - create_experiment(config)
    - run_experiment(experiment_id)
    - compare_variants(variant_a, variant_b)
    - export_results(experiment_id)

    Backwards-compatible: `submit_immune_case` is supported as a no-op logger.
    """

    def __init__(
        self,
        *,
        repo_root: str | None = None,
        orchestrator: Optional[Any] = None,
        domain: str = "core",
        environment: str = "sandbox",
        risk_level: str = "medium",
        safety_kernel: Optional[Any] = None,
    ) -> None:
        from pathlib import Path
        import asyncio

        self.repo_root = Path(repo_root or ".").resolve()
        self.domain = domain
        self.environment = environment
        self.risk_level = risk_level

        if orchestrator is not None:
            self.orchestrator = orchestrator
            return

        from quentin.infra.storage.kv_store import KVStore
        from quentin.infra.logging import Tracer
        from quentin.l3.research.eval_harness import EvalHarness
        from quentin.l3.research.experiment_orchestrator import ExperimentOrchestrator

        self.kv = KVStore()
        self.tracer = Tracer(store=self.kv, repo_root=str(self.repo_root))
        self.eval_harness = EvalHarness(kv=self.kv, tracer=self.tracer)
        self.orchestrator = ExperimentOrchestrator(
            tracer=self.tracer,
            kv=self.kv,
            eval_harness=self.eval_harness,
            safety_kernel=safety_kernel,
            domain=domain,
            environment=environment,
            risk_level=risk_level,
        )

    def submit_immune_case(self, case: Any) -> None:
        try:
            logger.info("ResearchInterfaceV3: received immune case %s", getattr(case, "case_id", "unknown"))
        except Exception:
            return

    # ------------------- Stable API (sync wrappers)
    def create_experiment(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """
        config schema (stable, minimal):
          {
            "name": str,
            "description": str,
            "target_type": str,        # e.g. "planner"
            "metrics": [str, ...],
            "variants": [{"variant_id": str, "name": str, "params": {...}}, ...]
          }
        """
        import asyncio

        async def _run() -> Dict[str, Any]:
            from quentin.l3.research.experiment_schemas import ExperimentConfig, ExperimentVariant

            name = str(config.get("name") or "experiment")
            desc = str(config.get("description") or "")
            target_type = str(config.get("target_type") or config.get("target_module") or "")
            metrics = list(config.get("metrics") or [])
            variants_in = list(config.get("variants") or [])
            variants = [
                ExperimentVariant(
                    variant_id=str(v.get("variant_id") or v.get("name") or "variant"),
                    name=str(v.get("name") or v.get("variant_id") or "variant"),
                    params=dict(v.get("params") or {}),
                )
                for v in variants_in
            ]
            exp_cfg = ExperimentConfig(target_module=target_type, metrics=[str(m) for m in metrics])
            rec = await self.orchestrator.create_experiment(
                name=name,
                description=desc,
                config=exp_cfg,
                variants=variants,
            )
            return rec.model_dump()

        return asyncio.run(_run())

    def run_experiment(self, experiment_id: str, *, cases: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
        import asyncio

        async def _run() -> Dict[str, Any]:
            from quentin.l3.research.eval_harness import EvalCase

            eval_cases = None
            if cases is not None:
                eval_cases = [EvalCase(**c) for c in cases]
            run = await self.orchestrator.run_experiment(experiment_id, cases=eval_cases)
            return run.to_dict()

        return asyncio.run(_run())

    def compare_variants(self, variant_a: Dict[str, Any], variant_b: Dict[str, Any]) -> Dict[str, Any]:
        """
        Minimal stable compare:
          - Inputs are two variant metric dicts (e.g. from run results)
          - Output is a shallow delta map.
        """
        a = dict(variant_a or {})
        b = dict(variant_b or {})
        keys = sorted(set(a.keys()) | set(b.keys()))
        delta: Dict[str, Any] = {}
        for k in keys:
            av = a.get(k)
            bv = b.get(k)
            try:
                if isinstance(av, (int, float)) and isinstance(bv, (int, float)):
                    delta[k] = bv - av
                else:
                    delta[k] = {"a": av, "b": bv}
            except Exception:
                delta[k] = {"a": av, "b": bv}
        return {"delta": delta}

    def export_results(self, experiment_id: str) -> Dict[str, Any]:
        import asyncio

        async def _run() -> Dict[str, Any]:
            rec = await self.orchestrator.get_experiment(experiment_id)
            runs = await self.orchestrator.list_runs(experiment_id)
            return {
                "experiment": rec.model_dump() if rec else None,
                "runs": [r.to_dict() for r in runs],
            }

        return asyncio.run(_run())

    # ------------------- Online A/B (small traffic) skeleton
    def route_online_variant(
        self,
        experiment_id: str,
        *,
        routing_key: str,
        baseline_variant_id: str = "baseline",
        candidate_variant_id: str = "candidate",
        fraction: Optional[float] = None,
        meta: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Minimal online A/B routing decision:
        - Uses a stable hash bucket on routing_key.
        - Persists decision to JSONL for later aggregation.
        """
        import asyncio

        async def _run() -> Dict[str, Any]:
            from quentin.l3.research.online_ab import OnlineABStore, OnlineABDecision, choose_variant

            rec = await self.orchestrator.get_experiment(experiment_id)
            frac = float(fraction) if fraction is not None else float(getattr(getattr(rec, "config", None), "traffic_fraction", 0.1) or 0.1)
            vid = choose_variant(
                routing_key=routing_key,
                baseline_variant_id=baseline_variant_id,
                candidate_variant_id=candidate_variant_id,
                fraction=frac,
            )
            store = OnlineABStore()
            store.append_decision(
                OnlineABDecision(
                    experiment_id=experiment_id,
                    routing_key=routing_key,
                    variant_id=vid,
                    fraction=frac,
                    meta=dict(meta or {}),
                )
            )
            return {"experiment_id": experiment_id, "variant_id": vid, "fraction": frac}

        return asyncio.run(_run())

    def record_online_metric(
        self,
        experiment_id: str,
        *,
        routing_key: str,
        variant_id: str,
        success: Optional[bool] = None,
        latency_ms: Optional[float] = None,
        cost_tokens: Optional[float] = None,
        meta: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        from quentin.l3.research.online_ab import OnlineABStore, OnlineABMetric

        store = OnlineABStore()
        store.append_metric(
            OnlineABMetric(
                experiment_id=experiment_id,
                routing_key=routing_key,
                variant_id=variant_id,
                success=success,
                latency_ms=latency_ms,
                cost_tokens=cost_tokens,
                meta=dict(meta or {}),
            )
        )
        return {"ok": True}

    # ------------------- Decision -> Promotion (A/B -> decide -> apply)
    def decide_and_promote_variant(
        self,
        experiment_id: str,
        *,
        promote_policy: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Decide a winner based on the most recent run results and (optionally) apply the decision.

        promote_policy schema (minimal, stable):
          {
            "metric": "success_rate",
            "min_delta": 0.01,
            "max_cost_increase_ratio": 0.25,
            "apply": true/false,
            "human_approved": true/false,
            "rules_path": "config/model_router_rules.json"   # optional override for apply
          }
        """
        import asyncio
        import json
        import os
        import time
        import uuid
        from pathlib import Path

        from quentin.l3.research.schemas import PromotionDecision

        pp = dict(promote_policy or {})
        metric = str(pp.get("metric") or "success_rate")
        min_delta = float(pp.get("min_delta") or 0.0)
        max_cost_increase_ratio = float(pp.get("max_cost_increase_ratio") or 10.0)
        do_apply = bool(pp.get("apply", True))
        human_approved = bool(pp.get("human_approved", False))
        rules_path = str(pp.get("rules_path") or "").strip()

        async def _run() -> Dict[str, Any]:
            rec = await self.orchestrator.get_experiment(experiment_id)
            if not rec:
                return {"ok": False, "error": "experiment_not_found", "experiment_id": experiment_id}
            target = str(getattr(getattr(rec, "config", None), "target_module", "") or "")
            if not rules_path:
                if "memory_fabric" in target or "memory.fabric" in target or target == "memory":
                    rules_path_val = os.getenv("QUENTIN_MEMORY_RECALL_DEFAULTS_PATH", "config/memory_recall_config.json")
                elif "immune_loop" in target or target == "immune_loop" or target == "immune":
                    rules_path_val = os.getenv("QUENTIN_IMMUNE_DEFAULTS_PATH", "config/immune_loop_config.json")
                else:
                    rules_path_val = "config/model_router_rules.json"
            else:
                rules_path_val = rules_path

            runs = await self.orchestrator.list_runs(experiment_id, limit=50)
            last_run = runs[-1] if runs else None
            results = None
            if last_run and isinstance(last_run.variant_results, dict) and last_run.variant_results:
                results = last_run.variant_results
            elif getattr(rec, "results", None):
                results = rec.results
            else:
                results = {}

            # Pick winner/loser by metric.
            best_vid = ""
            best_val = None
            second_vid = ""
            second_val = None

            for vid, m in (results or {}).items():
                if not isinstance(m, dict):
                    continue
                val = m.get(metric)
                if not isinstance(val, (int, float)):
                    continue
                if best_val is None or float(val) > float(best_val):
                    second_vid, second_val = best_vid, best_val
                    best_vid, best_val = str(vid), float(val)
                elif second_val is None or float(val) > float(second_val):
                    second_vid, second_val = str(vid), float(val)

            if not best_vid or best_val is None:
                return {
                    "ok": False,
                    "error": "missing_metric",
                    "metric": metric,
                    "experiment_id": experiment_id,
                    "available_variants": list((results or {}).keys()),
                }
            if not second_vid or second_val is None:
                # Single-variant experiment; allow decision but cannot compare.
                second_vid, second_val = best_vid, best_val

            delta = float(best_val) - float(second_val)

            # Optional cost gate: compare avg_cost_tokens if present.
            best_cost = None
            second_cost = None
            try:
                best_cost = (results.get(best_vid) or {}).get("avg_cost_tokens")
                second_cost = (results.get(second_vid) or {}).get("avg_cost_tokens")
                if not isinstance(best_cost, (int, float)):
                    best_cost = None
                if not isinstance(second_cost, (int, float)):
                    second_cost = None
            except Exception:
                best_cost = None
                second_cost = None

            cost_ratio = None
            if best_cost is not None and second_cost is not None and float(second_cost) > 0:
                cost_ratio = float(best_cost) / float(second_cost)

            required_gates: list[str] = []
            allow_apply = True
            reason = ""

            if delta < min_delta:
                allow_apply = False
                reason = f"delta_below_threshold delta={delta:.6f} min_delta={min_delta:.6f}"

            if cost_ratio is not None and cost_ratio > max_cost_increase_ratio:
                allow_apply = False
                reason = f"cost_increase_too_high ratio={cost_ratio:.3f} max={max_cost_increase_ratio:.3f}"

            # Governance: SafetyKernel + DomainPolicy.
            sk = getattr(self.orchestrator, "safety_kernel", None)
            if sk is not None:
                try:
                    from quentin.kernel.policy import ActionRequest

                    action = ActionRequest.new(
                        actor="research_interface_v3",
                        action_type="deploy",
                        domain=self.domain,
                        environment=self.environment,
                        risk_level=self.risk_level,
                        estimated_cost_tokens=0,
                        description="Promote experiment variant to online config.",
                        metadata={
                            "experiment_id": experiment_id,
                            "target_module": getattr(getattr(rec, "config", None), "target_module", ""),
                            "winner_variant_id": best_vid,
                            "metric": metric,
                            "delta": delta,
                        },
                    )
                    guard = sk.guard_action(action)
                    if not guard.allow:
                        allow_apply = False
                        required_gates.append("policy_denied")
                        reason = guard.reason
                    else:
                        mods = guard.policy_decision.modifications or {}
                        if bool(mods.get("require_human_gate", False)):
                            required_gates.append("human_gate")
                            if not human_approved:
                                allow_apply = False
                                if not reason:
                                    reason = "blocked_human_gate"
                        if bool(mods.get("require_canary", False)):
                            required_gates.append("require_canary")
                except Exception:
                    pass

            try:
                from quentin.domain.policies import get_domain_policy

                dp = get_domain_policy(self.domain)
                if not dp.allow_self_programming and "human_gate" not in required_gates:
                    required_gates.append("human_gate")
                    if not human_approved:
                        allow_apply = False
                        if not reason:
                            reason = "domain_policy_requires_human_gate"
            except Exception:
                pass

            decision = PromotionDecision(
                decision_id=f"promo::{uuid.uuid4().hex}",
                experiment_id=experiment_id,
                target_module=str(getattr(getattr(rec, "config", None), "target_module", "") or ""),
                metric=metric,
                winner_variant_id=best_vid,
                loser_variant_id=second_vid,
                metrics_delta={
                    "metric": metric,
                    "winner": best_val,
                    "loser": second_val,
                    "delta": delta,
                    "winner_avg_cost_tokens": best_cost,
                    "loser_avg_cost_tokens": second_cost,
                    "cost_ratio": cost_ratio,
                },
                promote_policy={
                    "min_delta": min_delta,
                    "max_cost_increase_ratio": max_cost_increase_ratio,
                    "apply": do_apply,
                },
                required_gates=required_gates,
                allow_apply=bool(allow_apply),
                reason=str(reason or "ok"),
                created_at=time.time(),
            )

            # Persist decision to KV (best-effort) for auditability.
            try:
                await self.kv.save(f"research:promotion:{decision.decision_id}", decision.to_dict())
                await self.kv.append_list("research:promotions:index", decision.decision_id)
            except Exception:
                pass

            # Trace/audit (best-effort).
            try:
                self.tracer.span(
                    "L3",
                    "promotion_decision",
                    module="research",
                    input={"experiment_id": experiment_id},
                    output=decision.to_dict(),
                )
            except Exception:
                pass

            applied = False
            apply_error = ""
            if do_apply and allow_apply:
                applied, apply_error = self._apply_promotion_best_effort(
                    rec=rec,
                    decision=decision,
                    rules_path=rules_path_val,
                )

            return {"ok": True, "decision": decision.to_dict(), "applied": applied, "apply_error": apply_error}

        return asyncio.run(_run())

    def _apply_promotion_best_effort(
        self,
        *,
        rec: Any,
        decision: Any,
        rules_path: str,
    ) -> tuple[bool, str]:
        """
        Apply promotion to a minimal "online effective config".
        Current v1 supports:
        - model_router: update `config/model_router_rules.json`
        - memory_fabric: update `config/memory_recall_config.json`
        """
        try:
            import json
            from datetime import datetime, UTC
            import time
            from pathlib import Path

            if str(self.environment) == "prod":
                return False, "refused_in_prod"

            target = str(getattr(getattr(rec, "config", None), "target_module", "") or "")
            winner_id = str(decision.winner_variant_id)
            winner = None
            for v in list(getattr(rec, "variants", []) or []):
                if getattr(v, "variant_id", None) == winner_id:
                    winner = v
                    break
            if winner is None:
                return False, "winner_variant_not_found"

            params = getattr(winner, "params", None)
            if not isinstance(params, dict):
                params = {}

            # Always persist winner params as an "online override" artifact (research-friendly, untracked).
            try:
                repo_root = Path(str(self.repo_root))
                out_path = (repo_root / "data" / "research" / "online_variant_overrides.json").resolve()
                out_path.parent.mkdir(parents=True, exist_ok=True)
                try:
                    existing = json.loads(out_path.read_text(encoding="utf-8") or "{}") if out_path.exists() else {}
                except Exception:
                    existing = {}
                if not isinstance(existing, dict):
                    existing = {}
                key = f"{self.environment}:{self.domain}:{target or 'unknown'}"
                existing[key] = {
                    "experiment_id": str(getattr(rec, "experiment_id", "") or ""),
                    "winner_variant_id": winner_id,
                    "params": params,
                    "recorded_at": time.time(),
                }
                out_path.write_text(json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8")
            except Exception:
                pass

            if target in ("memory_fabric", "memory", "memory.fabric"):
                repo_root = Path(str(self.repo_root))
                p = (repo_root / rules_path).resolve()
                p.parent.mkdir(parents=True, exist_ok=True)
                try:
                    raw = json.loads(p.read_text(encoding="utf-8") or "{}") if p.exists() else {}
                except Exception:
                    raw = {}
                if not isinstance(raw, dict):
                    raw = {}
                raw["updated_at"] = datetime.now(UTC).isoformat()
                raw["source"] = {"experiment_id": str(getattr(rec, "experiment_id", "") or ""), "variant_id": winner_id}
                raw["defaults"] = params.get("defaults") or params
                tmp = p.with_suffix(p.suffix + ".tmp")
                tmp.write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")
                tmp.replace(p)
                return True, ""

            if target in ("immune_loop", "immune"):
                repo_root = Path(str(self.repo_root))
                p = (repo_root / rules_path).resolve()
                p.parent.mkdir(parents=True, exist_ok=True)
                try:
                    raw = json.loads(p.read_text(encoding="utf-8") or "{}") if p.exists() else {}
                except Exception:
                    raw = {}
                if not isinstance(raw, dict):
                    raw = {}
                raw["updated_at"] = datetime.now(UTC).isoformat()
                raw["source"] = {"experiment_id": str(getattr(rec, "experiment_id", "") or ""), "variant_id": winner_id}
                raw["defaults"] = params.get("defaults") or params
                tmp = p.with_suffix(p.suffix + ".tmp")
                tmp.write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")
                tmp.replace(p)
                return True, ""

            if target not in ("model_router", "router"):
                # Persisted overrides are still useful even if we cannot auto-apply to a runtime component yet.
                return False, f"unsupported_target:{target or 'unknown'}"

            # Apply rule: route_key -> {"model": "..."}.
            route_key = params.get("route_key")
            model = params.get("model")
            if not isinstance(route_key, str) or not route_key:
                # Fallback: derive from (mode, task_type)
                mode = params.get("mode")
                task_type = params.get("task_type")
                if isinstance(mode, str) and isinstance(task_type, str) and mode and task_type:
                    route_key = f"{mode.lower()}::{task_type.lower()}"
            if not isinstance(model, str) or not model:
                return False, "missing_model_in_variant_params"
            if not isinstance(route_key, str) or not route_key:
                return False, "missing_route_key_in_variant_params"

            repo_root = Path(str(self.repo_root))
            p = (repo_root / rules_path).resolve()
            p.parent.mkdir(parents=True, exist_ok=True)
            try:
                raw = json.loads(p.read_text(encoding="utf-8") or "{}") if p.exists() else {}
            except Exception:
                raw = {}
            if not isinstance(raw, dict):
                raw = {}

            raw[str(route_key)] = {"model": str(model)}
            p.write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")
            return True, ""
        except Exception as e:
            return False, str(e)


# Back-compat alias: keep old implementation available by name.
LegacyResearchInterface = ResearchInterface
ResearchInterface = ResearchInterfaceV3
