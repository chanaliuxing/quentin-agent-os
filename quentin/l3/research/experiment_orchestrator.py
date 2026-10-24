from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from datetime import datetime, UTC
from pathlib import Path
import json
import uuid

from quentin.infra.storage.kv_store import KVStore
from quentin.infra.logging import Tracer
from quentin.l3.research.experiment_schemas import (
    ExperimentRecord,
    ExperimentStatus,
    ExperimentConfig,
    ExperimentVariant,
)
from quentin.l3.research.eval_harness import EvalHarness, EvalCase, EvalSuiteResult


@dataclass
class RunRecord:
    run_id: str
    experiment_id: str
    status: ExperimentStatus
    variant_results: Dict[str, Any] = field(default_factory=dict)
    cases: List[Dict[str, Any]] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "run_id": self.run_id,
            "experiment_id": self.experiment_id,
            "status": self.status.value if isinstance(self.status, ExperimentStatus) else str(self.status),
            "variant_results": self.variant_results,
            "cases": self.cases,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RunRecord":
        return cls(
            run_id=data["run_id"],
            experiment_id=data["experiment_id"],
            status=ExperimentStatus(data.get("status", ExperimentStatus.pending)),
            variant_results=data.get("variant_results", {}),
            cases=data.get("cases", []),
            created_at=data.get("created_at"),
            updated_at=data.get("updated_at"),
        )


@dataclass
class ExperimentOrchestrator:
    """
    Research Layer 的实验编排器。

    v1 功能：
    - create_experiment：定义一个实验及其 variants
    - list_experiments / get_experiment
    - run_experiment：占位实现（记录一次“运行”，生成假数据）
    - compare_variants：简单根据某个 metric 排序

    之后你可以在 run_experiment 里：
    - 根据 config.target_module 定位具体模块
    - 挂上不同 Variant 的实现
    - 跑离线数据集或在线小流量实验
    """

    tracer: Tracer
    kv: KVStore
    eval_harness: Optional[EvalHarness] = None
    safety_kernel: Optional[Any] = None
    domain: str = "core"
    environment: str = "sandbox"
    risk_level: str = "medium"

    record_prefix: str = "exp:record:"
    index_key: str = "exp:index:all"
    run_prefix: str = "exp:run:"
    run_index_prefix: str = "exp:run_index:"

    def __post_init__(self) -> None:
        if self.eval_harness is None:
            self.eval_harness = EvalHarness(kv=self.kv, tracer=self.tracer)

    async def _save(self, rec: ExperimentRecord) -> None:
        rec.updated_at = datetime.now(UTC)
        key = f"{self.record_prefix}{rec.experiment_id}"
        await self.kv.save(key, rec.model_dump())
        await self.kv.append_list(self.index_key, rec.experiment_id)

    async def _save_run(self, run: RunRecord) -> None:
        run.updated_at = datetime.now(UTC).isoformat()
        key = f"{self.run_prefix}{run.run_id}"
        await self.kv.save(key, run.to_dict())
        await self.kv.append_list(f"{self.run_index_prefix}{run.experiment_id}", run.run_id)

    async def create_experiment(
        self,
        name: str,
        description: str,
        config: ExperimentConfig,
        variants: List[ExperimentVariant],
    ) -> ExperimentRecord:
        exp_id = "exp_" + uuid.uuid4().hex
        rec = ExperimentRecord(
            experiment_id=exp_id,
            name=name,
            description=description,
            config=config,
            variants=variants,
        )
        await self._save(rec)

        self.tracer.span(
            "L3",
            "experiment_created",
            module="research",
            input={"experiment_id": exp_id, "name": name, "target": config.target_module},
        )

        return rec

    async def get_experiment(self, experiment_id: str) -> Optional[ExperimentRecord]:
        data = await self.kv.get(f"{self.record_prefix}{experiment_id}")
        if not data:
            return None
        return ExperimentRecord(**data)

    async def list_experiments(self, limit: int = 200) -> List[ExperimentRecord]:
        ids = await self.kv.get(self.index_key) or []
        ids = list(dict.fromkeys(ids))[-limit:]

        res: List[ExperimentRecord] = []
        for eid in ids:
            data = await self.kv.get(f"{self.record_prefix}{eid}")
            if data:
                res.append(ExperimentRecord(**data))
        return res

    async def run_experiment(
        self,
        experiment_id: str,
        *,
        cases: Optional[List[EvalCase]] = None,
    ) -> RunRecord:
        """
        创建一个 run（queued），然后立即分发执行。
        """
        run = await self.submit_run(experiment_id=experiment_id, cases=cases)
        return await self.dispatch_run(run.run_id)

    async def submit_run(
        self,
        experiment_id: str,
        *,
        cases: Optional[List[EvalCase]] = None,
    ) -> RunRecord:
        exp = await self.get_experiment(experiment_id)
        if not exp:
            raise ValueError(f"experiment not found: {experiment_id}")

        run_id = f"run_{uuid.uuid4().hex}"
        stored_cases = [c.to_dict() for c in cases] if cases else []

        run = RunRecord(
            run_id=run_id,
            experiment_id=experiment_id,
            status=ExperimentStatus.pending,
            cases=stored_cases,
        )
        await self._save_run(run)

        self.tracer.span(
            "L3",
            "experiment_run_submitted",
            module="research",
            input={"experiment_id": experiment_id, "run_id": run_id, "num_cases": len(stored_cases)},
        )
        return run

    async def dispatch_run(self, run_id: str) -> RunRecord:
        run = await self.get_run(run_id)
        if not run:
            raise ValueError(f"run not found: {run_id}")

        rec = await self.get_experiment(run.experiment_id)
        if not rec:
            raise ValueError(f"experiment not found for run {run_id}: {run.experiment_id}")

        action_id = self._guard_experiment_run(
            experiment_id=rec.experiment_id,
            run_id=run_id,
            target=rec.config.target_module,
        )

        run.status = ExperimentStatus.running
        await self._save_run(run)

        try:
            cases = [EvalCase(**c) for c in run.cases]
            variant_results: Dict[str, Any] = {}
            for variant in rec.variants:
                suite: EvalSuiteResult = await self.eval_harness.run_suite(
                    experiment_id=rec.experiment_id,
                    variant=variant,
                    cases=cases,
                    target_type=rec.config.target_module,
                )
                variant_results[variant.variant_id] = suite.metrics

            run.status = ExperimentStatus.completed
            run.variant_results = variant_results
            await self._save_run(run)

            # 更新 ExperimentRecord 聚合
            rec.status = ExperimentStatus.completed
            rec.results = variant_results
            await self._save(rec)

            self.tracer.span(
                "L3",
                "experiment_run_completed",
                module="research",
                input={"experiment_id": rec.experiment_id, "run_id": run_id},
                output={"results": variant_results},
            )
            self._audit_experiment_finish(action_id=action_id, ok=True, payload={"variant_results": variant_results})
        except Exception as exc:
            run.status = ExperimentStatus.failed
            await self._save_run(run)
            rec.status = ExperimentStatus.failed
            await self._save(rec)
            self.tracer.span(
                "L3",
                "experiment_run_failed",
                module="research",
                input={"experiment_id": rec.experiment_id, "run_id": run_id},
                output={"error": str(exc)},
            )
            self._audit_experiment_finish(action_id=action_id, ok=False, payload={"error": str(exc)})
            raise

        return run

    def _guard_experiment_run(self, *, experiment_id: str, run_id: str, target: str) -> Optional[str]:
        if self.safety_kernel is None:
            return None
        try:
            from quentin.kernel.policy import ActionRequest
            from quentin.kernel.taxonomy import ACTION_EXPERIMENT_RUN
            from quentin.kernel.audit import AuditEvent, default_audit_logger

            action = ActionRequest.new(
                actor="experiment_orchestrator",
                action_type=ACTION_EXPERIMENT_RUN,
                domain=self.domain,
                environment=self.environment,
                risk_level=self.risk_level,
                estimated_cost_tokens=0,
                estimated_cost_usd=0.0,
                description=f"experiment_run:{target}",
                metadata={"experiment_id": experiment_id, "run_id": run_id, "target": target},
            )
            guard = self.safety_kernel.guard_action(action)
            if not guard.allow:
                raise PermissionError(f"safety_kernel denied experiment_run: {guard.reason}")
            # Apply conservative downgrade if policy requires it.
            try:
                mods = guard.policy_decision.modifications if hasattr(guard, "policy_decision") else {}
                downgrade_env = (mods or {}).get("downgrade_environment")
                if downgrade_env and isinstance(downgrade_env, str) and downgrade_env != self.environment:
                    self.environment = downgrade_env
            except Exception:
                pass
            try:
                default_audit_logger().append(
                    AuditEvent(
                        action_id=action.action_id,
                        event_type="experiment_run",
                        phase="start",
                        actor="experiment_orchestrator",
                        payload={
                            "experiment_id": experiment_id,
                            "run_id": run_id,
                            "target": target,
                            "effective_environment": self.environment,
                        },
                    )
                )
            except Exception:
                pass
            return action.action_id
        except PermissionError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(f"safety_kernel error for experiment_run: {exc}") from exc

    def _audit_experiment_finish(self, *, action_id: Optional[str], ok: bool, payload: Dict[str, Any]) -> None:
        if not action_id:
            return
        try:
            from quentin.kernel.audit import AuditEvent, default_audit_logger

            default_audit_logger().append(
                AuditEvent(
                    action_id=action_id,
                    event_type="experiment_run",
                    phase="success" if ok else "error",
                    actor="experiment_orchestrator",
                    payload=payload,
                )
            )
        except Exception:
            pass

    async def compare_variants(
        self,
        experiment_id: str,
        metric: str,
    ) -> List[Dict[str, Any]]:
        """
        按某个 metric 对 variants 排序。
        """
        rec = await self.get_experiment(experiment_id) or ExperimentRecord(
            experiment_id=experiment_id,
            name="",
            description="",
            config=ExperimentConfig(target_module="", metrics=[]),
            variants=[],
        )

        results = rec.results or {}
        if not results:
            # 尝试从最近 run 获取
            run_ids = await self.kv.get(f"{self.run_index_prefix}{experiment_id}") or []
            if run_ids:
                last_run = await self.get_run(run_ids[-1])
                results = last_run.variant_results if last_run else {}

        rows = [
            {"variant_id": vid, "name": vid, "metric": res.get(metric)}
            for vid, res in results.items()
            if isinstance(res, dict)
        ]
        rows = [r for r in rows if r["metric"] is not None]
        rows.sort(key=lambda x: x["metric"], reverse=True)
        return rows

    async def decide_and_promote_variant(
        self,
        experiment_id: str,
        *,
        promote_policy: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Decide a winner based on the most recent run results and (optionally) apply it.

        promote_policy schema (minimal, stable):
          {
            "metric": "success_rate",
            "min_delta": 0.0,
            "apply": true/false,
            "rules_path": "config/model_router_rules.json"
          }
        """
        pp = dict(promote_policy or {})
        metric = str(pp.get("metric") or "success_rate")
        min_delta = float(pp.get("min_delta") or 0.0)
        do_apply = bool(pp.get("apply", True))
        rules_path = str(pp.get("rules_path") or "config/model_router_rules.json")

        rec = await self.get_experiment(experiment_id)
        if not rec:
            return {"ok": False, "error": "experiment_not_found", "experiment_id": experiment_id}

        runs = await self.list_runs(experiment_id, limit=50)
        last_run = runs[-1] if runs else None
        results = None
        if last_run and isinstance(last_run.variant_results, dict) and last_run.variant_results:
            results = last_run.variant_results
        elif getattr(rec, "results", None):
            results = rec.results
        else:
            results = {}

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
            return {"ok": False, "error": "missing_metric", "metric": metric, "experiment_id": experiment_id}
        if not second_vid or second_val is None:
            second_vid, second_val = best_vid, best_val

        delta = float(best_val) - float(second_val)
        allow_apply = delta >= min_delta
        reason = "ok" if allow_apply else f"delta_below_threshold delta={delta:.6f} min_delta={min_delta:.6f}"

        # Governance: best-effort SafetyKernel gate on "deploy/apply".
        if do_apply and self.safety_kernel is not None:
            try:
                from quentin.kernel.policy import ActionRequest

                action = ActionRequest.new(
                    actor="experiment_orchestrator",
                    action_type="deploy",
                    domain=self.domain,
                    environment=self.environment,
                    risk_level=self.risk_level,
                    estimated_cost_tokens=0,
                    description="Promote experiment variant.",
                    metadata={
                        "experiment_id": experiment_id,
                        "target_module": str(getattr(getattr(rec, "config", None), "target_module", "") or ""),
                        "winner_variant_id": best_vid,
                        "metric": metric,
                        "delta": delta,
                    },
                )
                guard = self.safety_kernel.guard_action(action)
                if not guard.allow:
                    allow_apply = False
                    reason = guard.reason
            except Exception:
                pass

        decision = {
            "experiment_id": experiment_id,
            "metric": metric,
            "winner_variant_id": best_vid,
            "loser_variant_id": second_vid,
            "winner_metric": best_val,
            "loser_metric": second_val,
            "delta": delta,
            "allow_apply": bool(allow_apply),
            "reason": str(reason),
        }

        applied = False
        apply_error = ""
        if do_apply and allow_apply:
            applied, apply_error = self._apply_promotion_best_effort(
                rec=rec,
                winner_variant_id=best_vid,
                rules_path=rules_path,
            )

        self.tracer.span(
            "L3",
            "promotion_decision",
            module="research",
            input={"experiment_id": experiment_id, "metric": metric},
            output={"decision": decision, "applied": applied, "apply_error": apply_error},
        )

        return {"ok": True, "decision": decision, "applied": applied, "apply_error": apply_error}

    def _apply_promotion_best_effort(
        self,
        *,
        rec: ExperimentRecord,
        winner_variant_id: str,
        rules_path: str,
    ) -> tuple[bool, str]:
        """
        Apply promotion to a minimal "online effective config".

        Current v1 supports:
        - model_router: update `config/model_router_rules.json`
        - memory_fabric: update `config/memory_recall_config.json`
        - immune_loop: update `config/immune_loop_config.json`
        """
        try:
            if str(self.environment) == "prod":
                return False, "refused_in_prod"

            target = str(getattr(getattr(rec, "config", None), "target_module", "") or "")
            is_model_router = ("model_router" in target) or ("routing.model_router" in target)
            is_memory_fabric = ("memory_fabric" in target) or ("memory.fabric" in target) or (target == "memory")
            is_immune_loop = ("immune_loop" in target) or (target == "immune_loop") or (target == "immune")
            if not is_model_router and not is_memory_fabric and not is_immune_loop:
                return False, "apply_not_supported_for_target"

            winner = None
            for v in list(getattr(rec, "variants", []) or []):
                if getattr(v, "variant_id", None) == winner_variant_id:
                    winner = v
                    break
            if winner is None:
                return False, "winner_variant_not_found"

            params = getattr(winner, "params", None)
            if not isinstance(params, dict):
                params = {}

            path = Path(rules_path) if is_model_router else Path(rules_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            existing: Dict[str, Any] = {}
            if path.exists():
                try:
                    existing = json.loads(path.read_text(encoding="utf-8") or "{}")
                except Exception:
                    existing = {}

            existing["updated_at"] = datetime.now(UTC).isoformat()
            existing["source"] = {"experiment_id": rec.experiment_id, "variant_id": winner_variant_id}
            if is_model_router:
                existing["rules"] = params.get("rules") or params
            else:
                existing["defaults"] = params.get("defaults") or params

            tmp = path.with_suffix(path.suffix + ".tmp")
            tmp.write_text(json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8")
            tmp.replace(path)
            return True, ""
        except Exception as exc:  # noqa: BLE001
            return False, str(exc)

    async def get_run(self, run_id: str) -> Optional[RunRecord]:
        data = await self.kv.get(f"{self.run_prefix}{run_id}")
        if not data:
            return None
        return RunRecord.from_dict(data)

    async def list_runs(self, experiment_id: str, limit: int = 50) -> List[RunRecord]:
        run_ids = await self.kv.get(f"{self.run_index_prefix}{experiment_id}") or []
        run_ids = list(dict.fromkeys(run_ids))[-limit:]
        res: List[RunRecord] = []
        for rid in run_ids:
            r = await self.get_run(rid)
            if r:
                res.append(r)
        return res
