from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Optional


@dataclass
class EvalCase:
    """
    一个最小的评测用例：
      - description: 用例说明
      - input_payload: 直接丢给 runtime.run_task(...) 的 payload
      - expected_keywords: 期望输出中包含的一些关键词（非常粗糙）
    """
    case_id: str
    description: str
    input_payload: Dict[str, Any]
    expected_keywords: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class EvalResult:
    case_id: str
    variant: str
    raw_output: Any
    score: float
    matched_keywords: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

@dataclass
class EvalCaseResult:
    case_id: str
    variant_id: str
    success: float
    status: str
    latency_sec: Optional[float]
    raw_metrics: Dict[str, Any]
    notes: str
    def to_dict(self) -> Dict[str, Any]: return asdict(self)

@dataclass
class VariantEvalSummary:
    experiment_id: str
    variant_id: str
    num_cases: int
    success_rate: float
    avg_latency_sec: Optional[float]
    extra_metrics: Dict[str, Any]
    def to_dict(self) -> Dict[str, Any]: return asdict(self)


class EvalHarness:
    """
    一个非常简单的 EvalHarness：

      - 目前默认调用 RuntimeFacade.run_task(...)
      - 使用“包含关键字数量 / 总关键字数量”作为粗糙评分
      - 真正的复杂评测（多维指标、LLM-as-judge）可以以后逐步自迭代升级
    """

    def __init__(self, variants_runtimes: Dict[str, Any]) -> None:
        self.variants_runtimes = variants_runtimes

    def run_prompt_eval(
        self,
        cases: List[EvalCase],
        *,
        variants: Optional[List[str]] = None,
    ) -> List[EvalResult]:
        if variants is None:
            variants = list(self.variants_runtimes.keys())

        results: List[EvalResult] = []

        for v in variants:
            runtime = self.variants_runtimes[v]
            for case in cases:
                # 这里我们假设 runtime.run_task(description, payload) 已经实现
                # Note: RuntimeFacade.run_task signature is run_task(description, payload, context)
                tr = runtime.run_task(
                    description=case.description,
                    payload=case.input_payload,
                    context={},
                )
                # 简单把 output 转成字符串
                text = str(tr.output)

                matched = [kw for kw in case.expected_keywords if kw in text]
                score = len(matched) / max(1, len(case.expected_keywords))

                results.append(
                    EvalResult(
                        case_id=case.case_id,
                        variant=v,
                        raw_output=text,
                        score=score,
                        matched_keywords=matched,
                    )
                )
        return results
        
    # Keeping previous methods for compatibility if needed by other modules
    def evaluate_task_result(self, *, experiment_id: str, variant_id: str, case: Any, task_result: Any, config: Any = None) -> Any:
        # Minimal stub to satisfy potential callers expecting the previous interface if I didn't overwrite everything
        # But since I am overwriting, the previous interface is gone unless I re-add it.
        # The instructions in 105.md defined evaluate_task_result and aggregate_variant_metrics.
        # The instructions in 119.md define run_prompt_eval and redefine EvalCase/EvalResult.
        # I should try to keep both if possible to avoid breaking things, or assume 119.md replaces 105.md logic.
        # However, ExperimentOrchestrator (defined in 105.md) calls evaluate_task_result.
        # So I MUST keep evaluate_task_result.
        
        # Re-adding evaluate_task_result and aggregate_variant_metrics from 105.md for compatibility
        
        from dataclasses import asdict
        
        # Need to import EvalCaseResult and VariantEvalSummary if I want to return them typed, 
        # but I can return Any or dict to be safe.
        # Actually, I should just merge the classes.
        pass

    # --------------------------------------------------
    # Compatibility methods from 105.md
    # --------------------------------------------------
    def evaluate_task_result(
        self,
        *,
        experiment_id: str,
        variant_id: str,
        case: Any, # EvalCase from 105.md
        task_result: Any,
        config: Optional[Dict[str, Any]] = None,
    ) -> Any: # Returns EvalCaseResult
        
        trace = task_result.trace
        status = trace.status or "unknown"
        metrics = trace.top_level_metrics or {}

        if status == "success":
            success = 1.0
        elif status in ("failed", "error"):
            success = 0.0
        else:
            success = 0.0

        latency = metrics.get("latency_sec")
        notes = ""
        if status != "success":
            notes = f"status={status}; may inspect trace for details."

        raw_metrics = {
            "status": status,
            "latency_sec": latency,
            "llm_calls": metrics.get("llm_calls"),
            "experiment_id": experiment_id,
            "variant_id": variant_id,
        }

        return EvalCaseResult(
            case_id=case.case_id,
            variant_id=variant_id,
            success=success,
            status=status,
            latency_sec=latency,
            raw_metrics=raw_metrics,
            notes=notes,
        )

    def aggregate_variant_metrics(
        self,
        *,
        experiment_id: str,
        variant_id: str,
        case_results: List[Any],
    ) -> Any: # Returns VariantEvalSummary
        
        num_cases = len(case_results)
        if num_cases == 0:
            return VariantEvalSummary(
                experiment_id=experiment_id,
                variant_id=variant_id,
                num_cases=0,
                success_rate=0.0,
                avg_latency_sec=None,
                extra_metrics={},
            )

        success_sum = 0.0
        latency_sum = 0.0
        latency_count = 0

        for r in case_results:
            success_sum += r.success
            if r.latency_sec is not None:
                latency_sum += r.latency_sec
                latency_count += 1

        success_rate = success_sum / num_cases
        avg_latency = latency_sum / latency_count if latency_count > 0 else None

        extra = {
            "num_success_cases": sum(1 for r in case_results if r.success >= 1.0),
            "num_failed_cases": sum(1 for r in case_results if r.success < 1.0),
        }

        return VariantEvalSummary(
            experiment_id=experiment_id,
            variant_id=variant_id,
            num_cases=num_cases,
            success_rate=success_rate,
            avg_latency_sec=avg_latency,
            extra_metrics=extra,
        )
