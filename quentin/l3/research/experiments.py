from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional
import json
import logging
import time
import uuid

from quentin.eval.harness import (
    EvalHarness,
    EvalCase,
    EvalCaseResult,
    VariantEvalSummary,
)
from quentin.runtime.system import RuntimeFacade, TaskResult
from quentin.runtime.session_write_lock import acquire_session_write_lock

logger = logging.getLogger(__name__)


@dataclass
class VariantConfig:
    variant_id: str
    name: str
    description: str
    target_component: str
    params: Dict[str, Any]

class ExperimentStore:
    """
    Minimal file-backed experiment store for orchestrator/runners.
    """
    def __init__(self, repo_root: str | Path) -> None:
        self.repo_root = Path(repo_root).resolve()
        self.base_dir = self.repo_root / "data" / "research" / "experiments"
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _config_path(self, experiment_id: str) -> Path:
        return self.base_dir / f"{experiment_id}.json"

    def create_experiment(
        self,
        name: str,
        purpose: str,
        target_component: str,
        created_by: str = "system",
        metadata: Optional[Dict[str, Any]] = None,
        variants: Optional[List[VariantConfig]] = None,
    ) -> ExperimentConfig:
        exp_id = f"exp::{uuid.uuid4().hex}"
        cfg = ExperimentConfig(
            experiment_id=exp_id,
            name=name,
            description=purpose,
            variants=variants or [],
            tasks=[],
            meta={
                "created_by": created_by,
                "target_component": target_component,
                **(metadata or {}),
            },
        )
        self.save_config(cfg)
        return cfg

    def save_config(self, cfg: ExperimentConfig) -> None:
        path = self._config_path(cfg.experiment_id)
        obj = {"config": cfg.to_dict(), "results": []}
        path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")

    def load_config(self, experiment_id: str) -> Optional[ExperimentConfig]:
        path = self._config_path(experiment_id)
        if not path.exists():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        return ExperimentConfig.from_dict(data.get("config") or {})

    def save_result(self, result: ExperimentResult) -> None:
        path = self._config_path(result.experiment_id)
        data: Dict[str, Any] = {"config": {}, "results": []}
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                data = {"config": {}, "results": []}
        data.setdefault("results", [])
        data["results"].append(result.to_dict())
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def load_results(self, experiment_id: str) -> List[ExperimentResult]:
        path = self._config_path(experiment_id)
        if not path.exists():
            return []
        data = json.loads(path.read_text(encoding="utf-8"))
        results_raw = data.get("results") or []
        results: List[ExperimentResult] = []
        for r in results_raw:
            vr_list = r.get("variant_results") or []
            results.append(
                ExperimentResult(
                    experiment_id=experiment_id,
                    status=r.get("status", "unknown"),
                    started_at=r.get("started_at"),
                    finished_at=r.get("finished_at"),
                    variant_results=vr_list,
                    best_variant_id=r.get("best_variant_id"),
                    best_metric_name=r.get("best_metric_name"),
                    notes=r.get("notes", ""),
                )
            )
        return results

@dataclass
class ExperimentTask:
    """
    一个实验里的单个任务定义（近似于 EvalCase 的核心部分）。

    实际跑的时候，会转成 EvalCase。
    """
    task_id: str
    goal: str
    context: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ExperimentConfig:
    """
    实验配置（机器可读）：

    - experiment_id: 唯一 ID
    - name / description: 便于人类识别
    - variants: 变体列表（ID 字符串），每个 ID 对应一个 RuntimeFacade
                 实现上：ExperimentOrchestrator 构造时注入 variant_id -> runtime 的 mapping
    - tasks: 任务列表
    - meta: 额外信息（domain / notes / tags）
    """
    experiment_id: str
    name: str
    description: str
    variants: List[str]
    tasks: List[ExperimentTask]
    meta: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "experiment_id": self.experiment_id,
            "name": self.name,
            "description": self.description,
            "variants": self.variants,
            "tasks": [t.to_dict() for t in self.tasks],
            "meta": self.meta,
        }

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> ExperimentConfig:
        tasks = [
            ExperimentTask(
                task_id=t.get("task_id"),
                goal=t.get("goal"),
                context=t.get("context") or {},
            )
            for t in data.get("tasks", [])
        ]
        return ExperimentConfig(
            experiment_id=data.get("experiment_id"),
            name=data.get("name"),
            description=data.get("description", ""),
            variants=list(data.get("variants") or []),
            tasks=tasks,
            meta=dict(data.get("meta") or {})
        )


@dataclass
class VariantRunReport:
    """
    一个 variant 在某次 run_experiment 中的结果：
      - case_results: 每个 case 的评测结果
      - summary: 聚合指标
    """
    variant_id: str
    case_results: List[EvalCaseResult]
    summary: VariantEvalSummary

    def to_dict(self) -> Dict[str, Any]:
        return {
            "variant_id": self.variant_id,
            "case_results": [c.to_dict() for c in self.case_results],
            "summary": self.summary.to_dict(),
        }

VariantResult = VariantRunReport

@dataclass
class ExperimentRunResult:
    """
    一次完整实验运行的结果。

    - run_id: 本次运行 ID
    - experiment_id: 对应哪个实验
    - started_at / finished_at: 时间戳
    - variant_reports: 每个 variant 的报告
    """
    run_id: str
    experiment_id: str
    started_at: float
    finished_at: float
    variant_reports: Dict[str, VariantRunReport]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "run_id": self.run_id,
            "experiment_id": self.experiment_id,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "variant_reports": {
                vid: report.to_dict() for vid, report in self.variant_reports.items()
            },
        }


ExperimentResult = ExperimentRunResult

@dataclass
class ExperimentRecord:
    """
    完整的实验记录：
      - config: 实验配置
      - runs: 历史运行记录列表
    """
    config: ExperimentConfig
    runs: List[ExperimentRunResult]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "config": self.config.to_dict(),
            "runs": [r.to_dict() for r in self.runs],
        }

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> ExperimentRecord:
        cfg = ExperimentConfig.from_dict(data.get("config") or {})
        runs_data = data.get("runs") or []
        runs: List[ExperimentRunResult] = []
        for r in runs_data:
            vr_dict = r.get("variant_reports") or {}
            variant_reports: Dict[str, VariantRunReport] = {}
            for vid, vrd in vr_dict.items():
                case_results = [
                    EvalCaseResult(
                        case_id=cr.get("case_id"),
                        variant_id=cr.get("variant_id"),
                        success=float(cr.get("success", 0.0)),
                        status=cr.get("status", "unknown"),
                        latency_sec=cr.get("latency_sec"),
                        raw_metrics=cr.get("raw_metrics") or {},
                        notes=cr.get("notes") or "",
                    )
                    for cr in vrd.get("case_results", [])
                ]
                summary_data = vrd.get("summary") or {}
                summary = VariantEvalSummary(
                    experiment_id=summary_data.get("experiment_id", cfg.experiment_id),
                    variant_id=summary_data.get("variant_id", vid),
                    num_cases=int(summary_data.get("num_cases", len(case_results))),
                    success_rate=float(summary_data.get("success_rate", 0.0)),
                    avg_latency_sec=summary_data.get("avg_latency_sec"),
                    extra_metrics=summary_data.get("extra_metrics") or {},
                )
                variant_reports[vid] = VariantRunReport(
                    variant_id=vid,
                    case_results=case_results,
                    summary=summary,
                )
            runs.append(
                ExperimentRunResult(
                    run_id=r.get("run_id"),
                    experiment_id=r.get("experiment_id", cfg.experiment_id),
                    started_at=float(r.get("started_at", 0.0)),
                    finished_at=float(r.get("finished_at", 0.0)),
                    variant_reports=variant_reports,
                )
            )
        return ExperimentRecord(config=cfg, runs=runs)

class ResearchManager:
    def __init__(self, patch_store=None, eval_harness=None, store: Optional[ExperimentStore] = None):
        self.store = store or ExperimentStore(repo_root=".")

    # Minimal APIs used by CLI / ResearchInterface
    def list_experiments(self):
        # list experiment ids from filesystem
        experiments = []
        for path in self.store.base_dir.glob("*.json"):
            experiments.append(path.stem)
        return experiments

    def create_experiment(self, name: str, purpose: str, target_component: str | None = None, created_by: str = "system", metadata: Optional[Dict[str, Any]] = None, variants: Optional[List[VariantConfig]] = None, **kwargs):
        # tolerate extra kwargs like capability
        return self.store.create_experiment(
            name=name,
            purpose=purpose,
            target_component=target_component or "generic",
            created_by=created_by,
            metadata=metadata,
            variants=variants or [],
        )

    def list_runs(self, experiment_id: str):
        return self.store.load_results(experiment_id)

    def compare_variants(self, experiment_id: str, metric_name: str = "score", top_k: int = 5, higher_is_better: bool = True):
        results = self.store.load_results(experiment_id)
        summaries = []
        for res in results:
            for vr in res.variant_results or []:
                # vr may be raw dict (from orchestrator save_result) or VariantRunReport dict
                metrics = vr.get("metrics", {}) if isinstance(vr, dict) else getattr(vr, "metrics", {})
                val = metrics.get(metric_name)
                if val is not None:
                    summaries.append({"variant_id": vr.get("variant_id") if isinstance(vr, dict) else vr.variant_id, "score": val})
        if not summaries:
            return []
        summaries.sort(key=lambda x: x["score"], reverse=higher_is_better)
        return summaries[:top_k]

    def export_results(self, experiment_id: str, dest_path: str):
        results = self.store.load_results(experiment_id)
        cfg = self.store.load_config(experiment_id)
        payload = {
            "config": cfg.to_dict() if cfg else {},
            "results": [r if isinstance(r, dict) else r for r in results],
        }
        Path(dest_path).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    # Compatibility no-ops for legacy callers
    def record_experiment(self, *a, **k):
        return None

    def record_run(self, *a, **k):
        return None

    # Basic placeholder stats provider so EvolutionStrategyManager can call safely
    def get_task_level_stats(self, capability: str, requirement_id: str) -> Dict[str, Any]:
        """
        Return coarse capability/requirement stats from the file-backed experiment store.

        This is intentionally lightweight (v1): it helps L2/L3 reason about whether a
        capability has any experiments/runs recorded without requiring an external DB.
        """
        cap = str(capability or "").strip()
        req = str(requirement_id or "").strip()
        exp_ids = []
        try:
            exp_ids = list(self.list_experiments() or [])
        except Exception:
            exp_ids = []

        matched: list[str] = []
        for exp_id in exp_ids:
            try:
                cfg = self.store.load_config(exp_id)
            except Exception:
                cfg = None
            if cfg is None:
                continue
            meta = getattr(cfg, "meta", {}) or {}
            target_component = str(meta.get("target_component") or "").strip()
            created_by = str(meta.get("created_by") or "").strip()
            # Match either by explicit target_component or by a loose substring in experiment_id.
            if cap and (target_component == cap or cap in target_component or cap in str(exp_id)):
                matched.append(exp_id)
                continue
            # Fallback: a few older configs may encode capability via created_by or description.
            desc = str(getattr(cfg, "description", "") or "")
            if cap and (cap in created_by or cap in desc):
                matched.append(exp_id)

        total_experiments = len(matched)
        total_runs = 0
        last_run_status: Optional[str] = None
        last_run_finished_at: Optional[float] = None
        for exp_id in matched:
            try:
                runs = self.store.load_results(exp_id)
            except Exception:
                runs = []
            total_runs += len(runs or [])
            for r in runs or []:
                try:
                    finished_at = float(getattr(r, "finished_at", 0.0) or 0.0)
                    status = str(getattr(r, "status", "") or "")
                except Exception:
                    continue
                if last_run_finished_at is None or finished_at > float(last_run_finished_at):
                    last_run_finished_at = finished_at
                    last_run_status = status or None

        return {
            "capability": cap,
            "requirement_id": req,
            "total_experiments": int(total_experiments),
            "total_runs": int(total_runs),
            "last_run_status": last_run_status,
            "last_run_finished_at": last_run_finished_at,
            "experiment_ids": matched[:20],
        }


class ExperimentOrchestrator:
    """
    L3 Research Layer 的核心组件之一：实验编排器。

    职责：
      - 管理 ExperimentConfig / ExperimentRecord
      - 调用多个 RuntimeFacade，对同一批任务进行 A/B 测试
      - 使用 EvalHarness 计算指标
      - 提供：
          * create_experiment(config)
          * run_experiment(experiment_id)
          * compare_variants(experiment_id, variant_a, variant_b)
          * export_results(experiment_id)

    设计思路：
      - variants_runtimes: variant_id -> RuntimeFacade
        （即不同版本/配置的智能体 runtime）
      - 持久化：每个 experiment 一个 JSON 文件，位于 data/research/experiments/<id>.json
    """

    def __init__(
        self,
        *,
        repo_root: str | Path,
        variants_runtimes: Dict[str, RuntimeFacade],
        eval_harness: Optional[EvalHarness] = None,
    ) -> None:
        self.repo_root = Path(repo_root).resolve()
        self.variants_runtimes = variants_runtimes
        self.eval_harness = eval_harness or EvalHarness(variants_runtimes=self.variants_runtimes) # Use default harness if none

        self.storage_dir = self.repo_root / "data" / "research" / "experiments"
        self.storage_dir.mkdir(parents=True, exist_ok=True)

        self._experiments: Dict[str, ExperimentRecord] = {}
        self._load_existing_experiments()

    # --------------------------------------------------
    # 公共 API：创建 / 运行 / 比较 / 导出
    # --------------------------------------------------
    def create_experiment(
        self,
        *,
        name: str,
        description: str,
        variants: Optional[List[str]] = None,
        tasks: Optional[List[ExperimentTask]] = None,
        meta: Optional[Dict[str, Any]] = None,
        experiment_id: Optional[str] = None,
    ) -> ExperimentRecord:
        """
        蓝皮书 API：create_experiment(config)

        这里用参数显式列出，内部构造 ExperimentConfig。
        """
        exp_id = experiment_id or f"exp::{uuid.uuid4().hex}"
        variants = variants or list(self.variants_runtimes.keys())
        tasks = tasks or []
        meta = meta or {}

        cfg = ExperimentConfig(
            experiment_id=exp_id,
            name=name,
            description=description,
            variants=variants,
            tasks=tasks,
            meta=meta,
        )

        record = ExperimentRecord(config=cfg, runs=[])
        self._experiments[exp_id] = record
        self._save_experiment(record)
        return record

    def run_experiment(
        self,
        experiment_id: str,
        *,
        max_tasks: Optional[int] = None,
    ) -> ExperimentRunResult:
        """
        蓝皮书 API：run_experiment(experiment_id)

        对指定实验的所有 variants 和 tasks 执行一轮完整评测。
        """
        record = self._get_experiment_or_raise(experiment_id)
        cfg = record.config

        # 1) 构造 EvalCase 列表
        eval_cases: List[EvalCase] = []
        for t in cfg.tasks:
            eval_cases.append(
                EvalCase(
                    case_id=t.task_id,
                    description=t.goal, # Mapping goal to description for EvalCase
                    input_payload=t.context, # Mapping context to input_payload. Note: task has goal and context.
                    # In 119.md, EvalCase has goal, context. 
                    # In 105.md, EvalCase has description, input_payload.
                    # I will use mapping: goal->description, context->input_payload.
                    expected_keywords=[], # Default empty
                )
            )
        if max_tasks is not None:
            eval_cases = eval_cases[:max_tasks]

        start_t = time.time()
        variant_reports: Dict[str, VariantRunReport] = {}

        # 2) 对每个 variant 跑这批 case
        for vid in cfg.variants:
            runtime = self.variants_runtimes.get(vid)
            if runtime is None:
                logger.warning("Experiment %s: variant %s has no runtime, skip", experiment_id, vid)
                continue

            case_results: List[EvalCaseResult] = []

            # Using EvalHarness to run eval
            # But wait, EvalHarness.run_prompt_eval (from 119.md) runs all variants.
            # ExperimentOrchestrator logic here iterates variants manually.
            # I should probably leverage EvalHarness.evaluate_task_result one by one or batch.
            # 105.md implementation iterated variants.
            
            for case in eval_cases:
                # 调用 runtime.run_task
                ctx = {
                    **case.input_payload,
                    "domain": cfg.meta.get("domain", "general"),
                    "experiment_id": experiment_id,
                    "variant_id": vid,
                }
                
                # RuntimeFacade.run_task(description, payload, context)
                task_result: TaskResult = runtime.run_task(description=case.description, payload=ctx, context=ctx)

                # 交给 EvalHarness 打分
                eval_res = self.eval_harness.evaluate_task_result(
                    experiment_id=experiment_id,
                    variant_id=vid,
                    case=case,
                    task_result=task_result,
                    config={"source": "experiment_orchestrator"},
                )
                case_results.append(eval_res)

            # 聚合 variant 指标
            summary = self.eval_harness.aggregate_variant_metrics(
                experiment_id=experiment_id,
                variant_id=vid,
                case_results=case_results,
            )

            variant_reports[vid] = VariantRunReport(
                variant_id=vid,
                case_results=case_results,
                summary=summary,
            )

        finished_t = time.time()
        run_id = f"run::{uuid.uuid4().hex}"

        run_result = ExperimentRunResult(
            run_id=run_id,
            experiment_id=experiment_id,
            started_at=start_t,
            finished_at=finished_t,
            variant_reports=variant_reports,
        )

        record.runs.append(run_result)
        self._save_experiment(record)
        return run_result

    def compare_variants(
        self,
        experiment_id: str,
        variant_a: Optional[str] = None,
        variant_b: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        蓝皮书 API：compare_variants(variant_a, variant_b)

        v1 实现：
          - 使用最近一次 run_experiment 的结果
          - 如果传入 variant_a / variant_b，则只比较这两个
          - 否则返回所有 variants 的 success_rate 排序列表
        """
        record = self._get_experiment_or_raise(experiment_id)
        if not record.runs:
            raise ValueError(f"Experiment {experiment_id} has no runs yet.")

        last_run = record.runs[-1]
        reports = last_run.variant_reports

        def _summary_for(vid: str) -> VariantEvalSummary:
            rep = reports.get(vid)
            if rep is None:
                raise ValueError(f"Variant {vid} not found in last run of {experiment_id}")
            return rep.summary

        if variant_a and variant_b:
            sa = _summary_for(variant_a)
            sb = _summary_for(variant_b)
            return {
                "experiment_id": experiment_id,
                "last_run_id": last_run.run_id,
                "variant_a": sa.to_dict(),
                "variant_b": sb.to_dict(),
                "better": (
                    variant_a if sa.success_rate > sb.success_rate
                    else variant_b if sb.success_rate > sa.success_rate
                    else "tie"
                ),
            }

        # 没有指定具体 variant，就返回排序列表
        summaries = [rep.summary for rep in reports.values()]
        summaries_sorted = sorted(
            summaries,
            key=lambda s: s.success_rate,
            reverse=True,
        )
        return {
            "experiment_id": experiment_id,
            "last_run_id": last_run.run_id,
            "ranked_variants": [s.to_dict() for s in summaries_sorted],
        }

    def export_results(self, experiment_id: str) -> Dict[str, Any]:
        """
        蓝皮书 API：export_results(experiment_id)

        v1 实现：
          - 返回 ExperimentRecord 的完整 dict
          - 同时确保磁盘上已经有最新 JSON
        """
        record = self._get_experiment_or_raise(experiment_id)
        self._save_experiment(record)  # 确保持久化
        return record.to_dict()

    def list_all_experiment_ids(self) -> List[str]:
        """
        返回所有已知实验的 ID 列表。
        """
        return list(self._experiments.keys())

    def get_experiment_record(self, experiment_id: str) -> ExperimentRecord:
        """
        根据 experiment_id 获取 ExperimentRecord，如果不存在则抛出 KeyError。
        """
        return self._get_experiment_or_raise(experiment_id)

    # --------------------------------------------------
    # 内部：加载 / 保存
    # --------------------------------------------------
    def _load_existing_experiments(self) -> None:
        """
        启动时从 data/research/experiments 目录加载所有 experiment JSON。
        """
        for path in self.storage_dir.glob("*.json"):
            try:
                with path.open("r", encoding="utf-8") as f:
                    data = json.load(f)
                record = ExperimentRecord.from_dict(data)
                self._experiments[record.config.experiment_id] = record
            except Exception:
                logger.exception("Failed to load experiment file: %s", path)

    def _save_experiment(self, record: ExperimentRecord) -> None:
        exp_id = record.config.experiment_id
        path = self.storage_dir / f"{exp_id.replace('::', '_')}.json"
        data = record.to_dict()
        tmp_path = path.with_suffix(".json.tmp")
        lock = acquire_session_write_lock(session_file=path)
        try:
            with tmp_path.open("w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            tmp_path.replace(path)
        finally:
            lock["release"]()

    def _get_experiment_or_raise(self, experiment_id: str) -> ExperimentRecord:
        record = self._experiments.get(experiment_id)
        if record is None:
            raise KeyError(f"Experiment not found: {experiment_id}")
        return record

    def register_skill_experiment(self, skill_candidate: Dict[str, Any]) -> str:
        # 之前已经加过的占位方法，如果没有就一起补上
        exp_id = f"skill-exp-{hash(json.dumps(skill_candidate, sort_keys=True)) & 0xFFFFFFFF}"
        record = {
            "experiment_id": exp_id,
            "type": "skill_candidate",
            "skill_candidate": skill_candidate,
        }
        path = self.storage_dir / "skill_candidates.jsonl"
        tmp = path.with_suffix(".tmp")
        lock = acquire_session_write_lock(session_file=path)
        try:
            with tmp.open("a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
            tmp.replace(path)
        finally:
            lock["release"]()
        return exp_id

    def register_patch_experiment(self, patch_proposal: Dict[str, Any]) -> str:
        """
        注册一个“Patch 实验”。

        当前版本：
          - 不立刻执行，只是把 patch 提案写入 JSONL
          - 返回 experiment_id，后续 ResearchLayer / EvalHarness 可以根据这个 id 去跑实验
        """
        exp_id = f"patch-exp-{hash(json.dumps(patch_proposal, sort_keys=True)) & 0xFFFFFFFF}"

        record = {
            "experiment_id": exp_id,
            "type": "patch_proposal",
            "patch_proposal": patch_proposal,
        }

        path = self.storage_dir / "patch_experiments.jsonl"
        tmp = path.with_suffix(".tmp")

        lock = acquire_session_write_lock(session_file=path)
        try:
            with tmp.open("a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
            tmp.replace(path)
        finally:
            lock["release"]()

        return exp_id

    def run_prompt_eval_experiment(
        self,
        *,
        experiment_id: str,
        cases: List[Dict[str, Any]],
        variants: List[str],
    ) -> List[Dict[str, Any]]:
        """
        运行一个简单的“prompt 评测实验”：

          - cases: list[dict]，每个 dict 必须包含：
              - case_id
              - description
              - input_payload
              - expected_keywords
          - variants: 要评测的 runtime 名称列表（例如 ["baseline", "council"]）
        """
        eval_cases = [
            EvalCase(
                case_id=c["case_id"],
                description=c["description"],
                input_payload=c["input_payload"],
                expected_keywords=c.get("expected_keywords", []),
            )
            for c in cases
        ]

        results = self.eval_harness.run_prompt_eval(eval_cases, variants=variants)

        # 写入 data/experiments/prompt_eval_<experiment_id>.jsonl
        path = self.storage_dir / f"prompt_eval_{experiment_id}.jsonl"
        tmp = path.with_suffix(".tmp")
        lock = acquire_session_write_lock(session_file=path)
        try:
            with tmp.open("a", encoding="utf-8") as f:
                for r in results:
                    f.write(json.dumps(r.to_dict(), ensure_ascii=False) + "\n")
            tmp.replace(path)
        finally:
            lock["release"]()

        return [r.to_dict() for r in results]

    def evaluate_patch_with_suite(
        self,
        *,
        repo_root: str | Path,
        trace_recorder: Any, # Using Any to avoid circular import if possible, or I should import TraceRecorder inside
        proposal_id: str,
        test_suite_id: str,
        baseline_variant: str = "baseline",
        candidate_variant: str = "council",
    ) -> Dict[str, Any]:
        # Lazy import to avoid circular dependency with self_programming/eval.py which imports experiments.py
        from quentin.self_programming.eval import PatchEvaluator
        
        evaluator = PatchEvaluator(
            repo_root=repo_root,
            experiment_orchestrator=self,
            trace_recorder=trace_recorder,
        )
        return evaluator.evaluate_patch(
            proposal_id=proposal_id,
            test_suite_id=test_suite_id,
            baseline_variant=baseline_variant,
            candidate_variant=candidate_variant,
        )
