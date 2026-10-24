from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime, UTC
from pathlib import Path
import hashlib
import json
import os
import tempfile
import time
import uuid
from typing import Any, Callable, Dict, List, Optional, Tuple

from quentin.infra.logging import Tracer
from quentin.infra.storage.kv_store import KVStore
from quentin.kernel.schemas import Experiment, ExperimentVariant
from quentin.memory.fabric import MemoryFabric
from quentin.memory.models import MemoryQuery
from quentin.traces.core import TraceEvent, TraceRecorder
from quentin.runtime.session_write_lock import acquire_session_write_lock


@dataclass
class EvalCase:
    case_id: str
    description: str
    input_payload: Dict[str, Any]
    expected_keywords: List[str] = field(default_factory=list)
    pass_threshold: float = 0.6
    meta: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class EvalCaseResult:
    case_id: str
    variant_id: str
    success: float
    status: str
    latency_ms: float
    cost_tokens: float
    raw_output: Any
    raw_metrics: Dict[str, Any] = field(default_factory=dict)
    notes: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class EvalSuiteResult:
    run_id: str
    experiment_id: str
    variant_id: str
    started_at: str
    finished_at: str
    case_results: List[EvalCaseResult]
    metrics: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["case_results"] = [c.to_dict() for c in self.case_results]
        return data


@dataclass
class EvalHarness:
    """
    实验评测骨架：
    - 允许注册不同 target_type 的 evaluator
    - 支持单次评测（run_eval）和评测套件（run_suite）
    - 将结果写入 TraceRecorder 和 JSONL 持久化，供 MetricsAggregator / 研究层使用
    """

    kv: KVStore
    tracer: Tracer
    results_path: Path = Path("data/research/eval_results.jsonl")
    trace_recorder: Optional[TraceRecorder] = None
    repo_root: Path | str = Path(".")

    def __post_init__(self) -> None:
        self._evaluators: Dict[str, Callable[[EvalCase, ExperimentVariant], Dict[str, Any]]] = {}
        self.results_path = Path(self.results_path)
        self.repo_root = Path(self.repo_root).resolve()
        self.results_path.parent.mkdir(parents=True, exist_ok=True)
        # Built-in evaluators for common target types.
        self.register_evaluator("planner", self._planner_evaluator_v1)
        self.register_evaluator("skill", self._skill_evaluator_v1)
        self.register_evaluator("model_router", self._model_router_evaluator_v1)
        self.register_evaluator("memory_fabric", self._memory_fabric_evaluator_v1)
        self.register_evaluator("immune_loop", self._immune_loop_evaluator_v1)

    # ------------------------------------------------------------------ 注册 evaluator
    def register_evaluator(
        self,
        target_type: str,
        fn: Callable[[EvalCase, ExperimentVariant], Dict[str, Any]],
    ) -> None:
        self._evaluators[target_type] = fn

    # ------------------------------------------------------------------ 核心入口
    async def run_eval_for_experiment(
        self,
        experiment: Experiment,
        variant: ExperimentVariant,
        cases: Optional[List[EvalCase]] = None,
    ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        """
        兼容旧接口：执行一次完整 eval suite，返回 (metrics, raw)
        """
        # 如果没有显式传入 cases，则尝试从 experiment.meta["eval_cases"] 读取
        if cases is None:
            raw_cases = experiment.meta.get("eval_cases", []) if hasattr(experiment, "meta") else []
            cases = [
                EvalCase(
                    case_id=c.get("case_id", f"case_{idx}"),
                    description=c.get("description", c.get("goal", "")),
                    input_payload=c.get("input_payload", c.get("context", {})),
                    expected_keywords=c.get("expected_keywords", []),
                    pass_threshold=float(c.get("pass_threshold", 0.6)),
                    meta=c.get("meta", {}),
                )
                for idx, c in enumerate(raw_cases)
            ]

        suite = await self.run_suite(
            experiment_id=experiment.experiment_id,
            variant=variant,
            cases=cases or [],
            target_type=experiment.target_type,
        )
        return suite.metrics, suite.to_dict()

    async def run_dataset(
        self,
        *,
        experiment_id: str,
        variant: ExperimentVariant,
        cases: List[EvalCase],
        target_type: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Compatibility helper for dataset-style runners.

        Returns aggregated metrics dict (same keys as `run_suite().metrics`).
        """
        suite = await self.run_suite(
            experiment_id=experiment_id,
            variant=variant,
            cases=cases,
            target_type=target_type,
        )
        return suite.metrics

    async def run_suite(
        self,
        *,
        experiment_id: str,
        variant: ExperimentVariant,
        cases: List[EvalCase],
        target_type: Optional[str] = None,
    ) -> EvalSuiteResult:
        """
        执行一组评测用例，聚合指标并持久化。
        """
        run_id = f"eval::{uuid.uuid4().hex}"
        started_at = datetime.now(UTC)
        case_results: List[EvalCaseResult] = []

        for case in cases:
            case_results.append(self._run_case(case=case, variant=variant, target_type=target_type))

        finished_at = datetime.now(UTC)
        metrics = self._aggregate(case_results)

        suite = EvalSuiteResult(
            run_id=run_id,
            experiment_id=experiment_id,
            variant_id=variant.variant_id,
            started_at=started_at.isoformat(),
            finished_at=finished_at.isoformat(),
            case_results=case_results,
            metrics=metrics,
        )

        await self._persist_suite_result(suite)
        self._record_trace_events(suite)

        self.tracer.span(
            "L3",
            "eval_run_completed",
            module="eval_harness",
            input={
                "experiment_id": experiment_id,
                "variant_id": variant.variant_id,
                "target_type": target_type or variant.target_type,
                "num_cases": len(cases),
            },
            output=metrics,
        )
        return suite

    # ------------------------------------------------------------------ 内部：单 case 执行/聚合/存储
    def _run_case(
        self,
        *,
        case: EvalCase,
        variant: ExperimentVariant,
        target_type: Optional[str],
    ) -> EvalCaseResult:
        evaluator = self._evaluators.get(target_type or variant.target_type, self._default_evaluator)

        start_t = time.perf_counter()
        payload = evaluator(case, variant) or {}
        latency_ms = (time.perf_counter() - start_t) * 1000.0

        # evaluator 可以直接返回 EvalCaseResult 以覆盖默认逻辑
        if isinstance(payload, EvalCaseResult):
            if payload.latency_ms <= 0:
                payload.latency_ms = latency_ms
            return payload

        raw_output = payload.get("output") if isinstance(payload, dict) else payload
        text = json.dumps(raw_output, ensure_ascii=False) if isinstance(raw_output, (dict, list)) else str(raw_output)

        matched = [kw for kw in case.expected_keywords if kw.lower() in text.lower()]
        success_score = len(matched) / max(1, len(case.expected_keywords)) if case.expected_keywords else 1.0
        status = "success" if success_score >= case.pass_threshold else "error"

        cost_tokens = float(payload.get("cost_tokens", 0.0)) if isinstance(payload, dict) else 0.0
        latency_ms = float(payload.get("latency_ms", latency_ms)) if isinstance(payload, dict) else latency_ms

        return EvalCaseResult(
            case_id=case.case_id,
            variant_id=variant.variant_id,
            success=success_score,
            status=status,
            latency_ms=latency_ms,
            cost_tokens=cost_tokens,
            raw_output=raw_output,
            raw_metrics={
                "matched_keywords": matched,
                "expected_keywords": case.expected_keywords,
            },
            notes=payload.get("notes", "") if isinstance(payload, dict) else "",
        )

    def _aggregate(self, results: List[EvalCaseResult]) -> Dict[str, Any]:
        if not results:
            return {
                "success_rate": 0.0,
                "avg_latency_ms": 0.0,
                "avg_cost_tokens": 0.0,
                "num_cases": 0,
            }

        total_success = sum(r.success for r in results)
        total_latency = sum(r.latency_ms for r in results)
        total_cost = sum(r.cost_tokens for r in results)
        n = len(results)

        return {
            "success_rate": total_success / n,
            "avg_latency_ms": total_latency / n,
            "avg_cost_tokens": total_cost / n,
            "num_cases": n,
        }

    # ------------------------------------------------------------------ Built-in evaluator(s)
    @staticmethod
    def _variant_params(variant: ExperimentVariant) -> Dict[str, Any]:
        """
        Compatibility helper: different schemas exist in this repo.

        Prefer:
        - variant.params (older / research schema)
        - variant.config (kernel.schemas VariantSpec/ExperimentVariant style)
        """
        params = getattr(variant, "params", None)
        if isinstance(params, dict):
            return params
        config = getattr(variant, "config", None)
        if isinstance(config, dict):
            return config
        return {}

    @staticmethod
    def _toy_embed(text: str, *, dim: int = 16) -> List[float]:
        """
        Small deterministic embedding for offline evaluators.

        This is intentionally NOT semantically meaningful; it exists only so vector-only/hybrid
        code paths can be exercised without external embedding providers.
        """
        h = hashlib.sha1((text or "").encode("utf-8")).digest()
        raw = list(h[:dim])
        return [((b / 255.0) * 2.0) - 1.0 for b in raw]

    def _planner_evaluator_v1(self, case: EvalCase, variant: ExperimentVariant) -> Dict[str, Any]:
        """
        Minimal planner evaluator for offline A/B:
        - Produces a plan JSON (goal → milestones → steps)
        - Uses expected_keywords as a cheap proxy for "plan relevance"

        Variant params:
          - strategy: "baseline" | "hierarchical"
        """
        started = time.perf_counter()
        vparams = self._variant_params(variant)
        strategy = str(vparams.get("strategy") or "baseline").lower()

        goal = case.description
        if strategy == "hierarchical":
            steps = [
                {"step_id": "s1", "description": f"Analyze goal: {goal}", "depends_on": [], "rollback_point": None, "estimated_cost_tokens": 0},
                {"step_id": "s2", "description": f"Execute goal: {goal}", "depends_on": ["s1"], "rollback_point": "revert_changes_if_any", "estimated_cost_tokens": 0},
            ]
        else:
            steps = [
                {"step_id": "s1", "description": f"Execute goal: {goal}", "depends_on": [], "rollback_point": None, "estimated_cost_tokens": 0},
            ]

        plan = {
            "goal": goal,
            "milestones": [{"milestone_id": "m1", "title": "Execute", "steps": steps}],
            "steps": [{"step_id": s["step_id"], "description": s["description"]} for s in steps],  # back-compat
            "success_criteria": case.meta.get("success_criteria", []),
            "hard_constraints": case.meta.get("hard_constraints", []),
        }

        # Cheap "cost" proxy: tokens ≈ chars/4.
        cost_tokens = float(max(1, int(len(json.dumps(plan, ensure_ascii=False)) / 4)))
        latency_ms = (time.perf_counter() - started) * 1000.0
        return {
            "output": plan,
            "cost_tokens": cost_tokens,
            "latency_ms": latency_ms,
            "notes": f"planner_eval_v1 strategy={strategy}",
        }

    def _memory_fabric_evaluator_v1(self, case: EvalCase, variant: ExperimentVariant) -> Dict[str, Any]:
        """
        Offline memory evaluator:
        - Populate a temporary SQLite memory DB with a small corpus
        - Run recall with parameters from variant.params/config
        - Output top-k contents so expected_keywords checks can score success

        Expected case.input_payload:
          {
            "corpus": ["text1", "text2", ...],
            "query": "..."
          }
        """
        params = self._variant_params(variant)
        mode = str(params.get("mode") or "hybrid")
        alpha = float(params.get("alpha") or 0.5)
        top_k = int(params.get("top_k") or 5)
        k_text = int(params.get("k_text") or top_k)
        k_vec = int(params.get("k_vec") or top_k)

        payload = case.input_payload or {}
        corpus = payload.get("corpus") or []
        if not isinstance(corpus, list):
            corpus = [str(corpus)]
        query_text = str(payload.get("query") or case.description or "")

        with tempfile.TemporaryDirectory(prefix="quentin_eval_mem_") as d:
            db_path = Path(d) / "memory.db"
            fabric = MemoryFabric(db_path=db_path, use_postgres=False, trace_recorder=None)

            for t in corpus[:200]:
                text = str(t)
                fabric.remember_atomic(
                    content=text,
                    source="eval_harness",
                    vector=self._toy_embed(text),
                    metadata={"eval_case_id": case.case_id},
                )

            q = MemoryQuery(
                text=query_text if mode != "vector_only" else None,
                vector=self._toy_embed(query_text) if mode in ("vector_only", "hybrid") else None,
                top_k=top_k,
                mode=mode,
                alpha=alpha,
                k_text=k_text,
                k_vec=k_vec,
                debug=False,
            )
            recs = fabric.recall(q)
            top_contents = [r.content for r in recs[:top_k]]

        return {
            "output": {
                "mode": mode,
                "alpha": alpha,
                "top_k": top_k,
                "top_contents": top_contents,
            },
            "notes": "memory_fabric_eval_v1",
        }

    def _skill_evaluator_v1(self, case: EvalCase, variant: ExperimentVariant) -> Dict[str, Any]:
        """
        Minimal skill evaluator:
        - Loads a python module from a file path (variant.params.module_path)
        - Calls a function (variant.params.callable, default: run_skill)
        - Returns JSON-friendly output

        This enables A/B comparisons between old/new skill implementations using EvalHarness.
        """
        params = self._variant_params(variant)
        module_path = params.get("module_path") or params.get("path")
        fn_name = str(params.get("callable") or "run_skill")
        if not module_path:
            return {"output": {"error": "missing_module_path"}, "cost_tokens": 0.0}

        try:
            import importlib.util

            spec = importlib.util.spec_from_file_location("quentin_skill_variant", str(module_path))
            if spec is None or spec.loader is None:
                return {"output": {"error": "cannot_load_module", "module_path": str(module_path)}, "cost_tokens": 0.0}
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)  # type: ignore[union-attr]
            fn = getattr(mod, fn_name, None)
            if fn is None or not callable(fn):
                return {
                    "output": {"error": "missing_callable", "callable": fn_name, "module_path": str(module_path)},
                    "cost_tokens": 0.0,
                }
            out = fn(case.input_payload or {})
            return {"output": out, "cost_tokens": 0.0}
        except Exception as e:  # noqa: BLE001
            return {"output": {"error": str(e), "module_path": str(module_path)}, "cost_tokens": 0.0}

    def _model_router_evaluator_v1(self, case: EvalCase, variant: ExperimentVariant) -> Dict[str, Any]:
        """
        Minimal model_router evaluator:
        - Treats `variant.params.model` as the "chosen model" (schema-stable, no external calls).
        - Returns a JSON-friendly output that the default keyword matcher can score.

        This is intentionally lightweight so L3->L2->L1 feedback loops can run locally.
        """
        started = time.perf_counter()
        params = self._variant_params(variant)
        chosen = params.get("model") or params.get("chosen_model") or "unknown"
        latency_ms = (time.perf_counter() - started) * 1000.0
        return {
            "output": {"chosen_model": str(chosen)},
            "cost_tokens": 0.0,
            "latency_ms": latency_ms,
            "notes": "model_router_eval_v1",
        }

    def _immune_loop_evaluator_v1(self, case: EvalCase, variant: ExperimentVariant) -> EvalCaseResult:
        """
        Offline immune loop evaluator:
        - Builds a temporary ExecutionTraceStore with synthetic traces
        - Runs ImmuneLoop with variant threshold knobs
        - Scores whether flagged components match expectations

        Expected case.input_payload:
          {
            "traces": [
              {"component_id": "planner", "success": true, "latency_ms": 10.0},
              ...
            ],
            "expect": {
              "flagged_components": ["planner"],
              "unflagged_components": ["executor"]
            }
          }
        """
        started = time.perf_counter()
        params = self._variant_params(variant)
        window_minutes = int(params.get("window_minutes") or 60)
        min_samples = int(params.get("min_samples") or 10)
        error_rate_threshold = float(params.get("error_rate_threshold") or 0.3)
        latency_ms_threshold = params.get("latency_ms_threshold")
        latency_ms_threshold_val = float(latency_ms_threshold) if latency_ms_threshold is not None else None

        payload = case.input_payload or {}
        traces = payload.get("traces") or []
        if not isinstance(traces, list):
            traces = []
        expect = payload.get("expect") or {}
        if not isinstance(expect, dict):
            expect = {}
        expected_flagged = [str(x) for x in (expect.get("flagged_components") or []) if x is not None]
        expected_unflagged = [str(x) for x in (expect.get("unflagged_components") or []) if x is not None]

        with tempfile.TemporaryDirectory(prefix="quentin_eval_immune_") as d:
            from datetime import datetime, UTC
            from quentin.traces.execution_trace import ExecutionTrace, ExecutionTraceStore
            from quentin.l3.research.experiments import ExperimentStore, ResearchManager
            from quentin.loops.immune_loop import ImmuneLoop, ImmuneConfig

            store = ExecutionTraceStore(repo_root=d)
            now = datetime.now(UTC).isoformat()

            for idx, t in enumerate(traces):
                if not isinstance(t, dict):
                    continue
                comp = str(t.get("component_id") or "unknown")
                success = bool(t.get("success", True))
                latency = t.get("latency_ms")
                metrics: Dict[str, float] = {}
                if latency is not None:
                    try:
                        metrics["latency_ms"] = float(latency)
                    except Exception:
                        pass
                store.append(
                    ExecutionTrace(
                        trace_id=f"trace_{idx}",
                        task_id=f"task_{idx}",
                        component_id=comp,
                        blueprint_capability_id=None,
                        success=success,
                        start_time=now,
                        end_time=now,
                        metrics=metrics,
                        tags={},
                    )
                )

            rm = ResearchManager(store=ExperimentStore(repo_root=d))
            loop = ImmuneLoop(
                repo_root=d,
                config=ImmuneConfig(
                    window_minutes=window_minutes,
                    min_samples=min_samples,
                    error_rate_threshold=error_rate_threshold,
                    latency_ms_threshold=latency_ms_threshold_val,
                    enable_self_fix=False,
                    max_self_fix_per_run=0,
                    component_to_module={},
                ),
                traces_store=store,
                research_manager=rm,
                immune_cases_path="data/immune_cases.jsonl",
            )
            immune_cases = loop.run_once()

        flagged = sorted({c.component_id for c in (immune_cases or []) if getattr(c, "component_id", None)})
        ok = True
        missing = [c for c in expected_flagged if c not in flagged]
        unexpected = [c for c in flagged if c in set(expected_unflagged)]
        if missing or unexpected:
            ok = False

        latency_ms = (time.perf_counter() - started) * 1000.0
        return EvalCaseResult(
            case_id=case.case_id,
            variant_id=variant.variant_id,
            success=1.0 if ok else 0.0,
            status="success" if ok else "error",
            latency_ms=latency_ms,
            cost_tokens=0.0,
            raw_output={
                "flagged_components": flagged,
                "expected_flagged": expected_flagged,
                "expected_unflagged": expected_unflagged,
                "missing": missing,
                "unexpected": unexpected,
                "params": {
                    "window_minutes": window_minutes,
                    "min_samples": min_samples,
                    "error_rate_threshold": error_rate_threshold,
                    "latency_ms_threshold": latency_ms_threshold_val,
                },
            },
            raw_metrics={"flagged_components": flagged, "missing": missing, "unexpected": unexpected},
            notes="immune_loop_eval_v1",
        )

    async def _persist_suite_result(self, suite: EvalSuiteResult) -> None:
        data = suite.to_dict()
        await self.kv.save(f"eval:run:{suite.run_id}", data)
        await self.kv.append_list("eval:index:runs", suite.run_id)

        lock = acquire_session_write_lock(session_file=self.results_path)
        try:
            with self.results_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(data, ensure_ascii=False) + "\n")
        finally:
            lock["release"]()

        # Optional persistence for "brain learning": store eval outcomes in MemoryFabric (default OFF).
        if (os.getenv("QUENTIN_EVAL_RESULTS_TO_MEMORY", "0") or "").strip().lower() in ("1", "true", "yes", "on"):
            try:
                fabric = MemoryFabric(repo_root=self.repo_root, trace_recorder=None)
                summary = {
                    "run_id": suite.run_id,
                    "experiment_id": suite.experiment_id,
                    "variant_id": suite.variant_id,
                    "metrics": suite.metrics,
                    "started_at": suite.started_at,
                    "finished_at": suite.finished_at,
                    "num_cases": len(suite.case_results or []),
                }
                fabric.remember_atomic(
                    content=f"eval_suite_result {json.dumps(summary, ensure_ascii=False)}",
                    source="eval_harness",
                    domain="core",
                    importance=0.3,
                    metadata={"suite": data, "summary": summary},
                    kind="semantic",
                )
            except Exception:
                pass

        # Optional event bridge into SystemEventQueue so cognitive loop / autofixer can react.
        try:
            events_on = (os.getenv("QUENTIN_EVAL_RESULTS_TO_EVENTS", "0") or "").strip().lower() in ("1", "true", "yes", "on")
            global_events_on = (os.getenv("QUENTIN_OUTCOME_EVENTS", "0") or "").strip().lower() in ("1", "true", "yes", "on")
            if events_on or global_events_on:
                from quentin.runtime.system_events import SystemEventQueue

                queue = SystemEventQueue(repo_root=self.repo_root)
                queue.enqueue_event(
                    session_id=str(os.getenv("QUENTIN_SESSION_ID", "brain") or "brain"),
                    event_type="evaluation_suite_completed",
                    payload={
                        "run_id": suite.run_id,
                        "experiment_id": suite.experiment_id,
                        "variant_id": suite.variant_id,
                        "metrics": dict(suite.metrics or {}),
                        "num_cases": len(suite.case_results or []),
                    },
                    source="eval_harness",
                )
        except Exception:
            pass

    def _record_trace_events(self, suite: EvalSuiteResult) -> None:
        if not self.trace_recorder:
            return

        for res in suite.case_results:
            payload = {
                "experiment_id": suite.experiment_id,
                "variant_id": suite.variant_id,
                "case_id": res.case_id,
                "status": res.status,
                "latency_ms": res.latency_ms,
                "cost_tokens": res.cost_tokens,
                "success_score": res.success,
            }
            event = TraceEvent(
                event_id=str(uuid.uuid4()),
                trace_id=suite.run_id,
                event_type="task_result",
                timestamp=datetime.now(UTC).isoformat(),
                payload=payload,
            )
            self.trace_recorder.record_event(event)

    # ------------------------------------------------------------------ 默认 evaluator
    def _default_evaluator(self, case: EvalCase, variant: ExperimentVariant) -> Dict[str, Any]:
        """
        最简单的 evaluator：
        - 假设 input_payload 里已经包含模型输出字符串（字段 output/text）
        - 只做关键字匹配，不调用外部服务
        """
        raw_output = (
            case.input_payload.get("output")
            or case.input_payload.get("text")
            or case.input_payload.get("candidate_output")
            or ""
        )
        return {
            "output": raw_output,
            "cost_tokens": float(case.input_payload.get("cost_tokens", 0.0)),
            "latency_ms": float(case.input_payload.get("latency_ms", 0.0)),
            "notes": f"default_eval:{variant.variant_id}",
        }
