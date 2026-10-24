from __future__ import annotations

from dataclasses import dataclass
from typing import List, Dict, Any, Optional
import uuid

from quentin.infra.storage.kv_store import KVStore
from quentin.infra.logging import Tracer
from quentin.eval.harness import EvalHarness
from quentin.experiments.schemas import (
    ExperimentConfig,
    ExperimentRecord,
    ExperimentStatus,
    ExperimentRunResult,
    ExperimentRunStatus,
    VariantConfig,
)
from quentin.utils.time import now_utc


@dataclass
class ExperimentOrchestrator:
    """
    Research & Evolution Layer v1 的核心：

    - create_experiment(config)
    - run_experiment(experiment_id)
    - compare_variants(experiment_id, metric="score")
    - export_results(experiment_id)

    当前只实现 offline、顺序跑所有 variants。
    """
    tracer: Tracer
    kv: KVStore
    eval_harness: EvalHarness

    exp_prefix: str = "exp:record:"
    exp_index_key: str = "exp:index:all"

    # ---------- KV 工具 ----------

    async def _save_record(self, record: ExperimentRecord) -> None:
        key = f"{self.exp_prefix}{record.experiment_id}"
        await self.kv.save(key, record.model_dump())
        await self.kv.append_list(self.exp_index_key, record.experiment_id)

    async def _load_record(self, experiment_id: str) -> Optional[ExperimentRecord]:
        data = await self.kv.get(f"{self.exp_prefix}{experiment_id}")
        if not data:
            return None
        return ExperimentRecord(**data)

    async def list_experiments(self, limit: int = 50) -> List[ExperimentRecord]:
        ids = await self.kv.get(self.exp_index_key) or []
        ids = list(dict.fromkeys(ids))[-limit:]
        res: List[ExperimentRecord] = []
        for eid in ids:
            data = await self.kv.get(f"{self.exp_prefix}{eid}")
            if data:
                res.append(ExperimentRecord(**data))
        return res

    async def get_experiment(self, experiment_id: str) -> Optional[ExperimentRecord]:
        return await self._load_record(experiment_id)

    # ---------- API：创建实验 ----------

    async def create_experiment(self, cfg: ExperimentConfig) -> ExperimentRecord:
        exp_id = cfg.experiment_id or f"exp_{uuid.uuid4().hex}"
        now = now_utc()
        record = ExperimentRecord(
            experiment_id=exp_id,
            name=cfg.name,
            description=cfg.description,
            eval_kind=cfg.eval_kind,
            dataset=cfg.dataset,
            variants=cfg.variants,
            status=ExperimentStatus.draft,
            created_at=now,
            updated_at=now,
            runs=[],
            meta=cfg.meta,
        )
        await self._save_record(record)

        self.tracer.span(
            "L3",
            "experiment_created",
            module="experiment_orchestrator",
            input={"experiment_id": exp_id, "name": cfg.name},
        )
        return record

    # ---------- API：运行实验 ----------

    async def run_experiment(self, experiment_id: str) -> Optional[ExperimentRecord]:
        record = await self._load_record(experiment_id)
        if not record:
            return None

        record.status = ExperimentStatus.running
        record.updated_at = now_utc()
        await self._save_record(record)

        runs: List[ExperimentRunResult] = []

        for variant in record.variants:
            try:
                run = await self.eval_harness.run_variant(record, variant)
            except Exception as e:
                run = ExperimentRunResult(
                    run_id=f"run_{uuid.uuid4().hex}",
                    experiment_id=record.experiment_id,
                    variant_id=variant.variant_id,
                    status=ExperimentRunStatus.failed,
                    error=repr(e),
                    metrics={},
                )
            runs.append(run)

        record.runs.extend(runs)
        record.updated_at = now_utc()

        # 决定整体状态
        if any(r.status == ExperimentRunStatus.failed for r in record.runs):
            record.status = ExperimentStatus.failed
        else:
            record.status = ExperimentStatus.completed

        await self._save_record(record)

        self.tracer.span(
            "L3",
            "experiment_run_completed",
            module="experiment_orchestrator",
            input={"experiment_id": experiment_id},
            output={
                "status": record.status.value,
                "runs": len(record.runs),
            },
        )

        return record

    # ---------- API：比较变体 ----------

    async def compare_variants(
        self,
        experiment_id: str,
        metric: str = "score",
        higher_is_better: bool = True,
    ) -> Optional[Dict[str, Any]]:
        record = await self._load_record(experiment_id)
        if not record or not record.runs:
            return None

        # 聚合每个 variant 的 score（当前以最后一次 run 为准）
        by_variant: Dict[str, ExperimentRunResult] = {}
        for r in record.runs:
            by_variant[r.variant_id] = r

        def get_score(r: ExperimentRunResult) -> float:
            val = r.metrics.get(metric, None)
            if isinstance(val, (int, float)):
                return float(val)
            return 0.0

        best_run: Optional[ExperimentRunResult] = None
        for r in by_variant.values():
            if not best_run:
                best_run = r
                continue
            if higher_is_better:
                if get_score(r) > get_score(best_run):
                    best_run = r
            else:
                if get_score(r) < get_score(best_run):
                    best_run = r

        if not best_run:
            return None

        return {
            "experiment_id": record.experiment_id,
            "metric": metric,
            "higher_is_better": higher_is_better,
            "best_variant_id": best_run.variant_id,
            "best_score": get_score(best_run),
            "best_run": best_run.model_dump(),
        }

    # ---------- API：导出完整结果 ----------

    async def export_results(self, experiment_id: str) -> Optional[Dict[str, Any]]:
        record = await self._load_record(experiment_id)
        if not record:
            return None

        compare = await self.compare_variants(experiment_id)

        return {
            "experiment": record.model_dump(),
            "compare": compare,
        }
