from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional
import importlib
import inspect
import logging

from quentin.blueprint.spec import BlueprintSpec, BlueprintCapability, load_default_spec_v3
from quentin.blueprint.gap_tracker import CapabilitiesRegistry, CapabilityStatus
from quentin.blueprint.llm_probes import LLMBasedCapabilityProbe, LLMProbeResult

logger = logging.getLogger(__name__)


@dataclass
class CapabilityProbeResult:
    """
    单条能力的探测结果（来自静态规则 / import 检查 / 将来可能来自 LLM 分析）。

    status_guess:
      - "done" / "partial" / "missing" / "unknown"
    confidence:
      - 0.0 ~ 1.0（简单启发式置信度）
    evidence:
      - 简短文字说明，例如 "found class ExperimentOrchestrator in module quentin.l3.research.experiments"
    """
    capability_id: str
    status_guess: str
    confidence: float
    evidence: str
    source: str  # 哪个 probe 给出的结果（static/import/llm/...）

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class CapabilityScanReport:
    """
    一次扫描的整体报告。
    """
    spec_version: str
    repo_root: str
    probe_results: List[CapabilityProbeResult]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "spec_version": self.spec_version,
            "repo_root": self.repo_root,
            "probe_results": [r.to_dict() for r in self.probe_results],
        }


class CapabilityScanner:
    """
    蓝皮书能力自动扫描器 v1：

      - 读取 BlueprintSpec（蓝皮书能力定义）
      - 使用简单的静态规则检查 repo 是否具备某些关键模块/类
      - 可选：使用 LLM / 多模型会议 语义判断
      - 更新 CapabilitiesRegistry（missing/partial/done）
      - 返回 CapabilityScanReport

    设计目标：
      - 现在先靠静态规则把“我们已经写好的模块”标记为 done
      - 使用 LLM probe 辅助判断语义实现程度
    """

    def __init__(
        self,
        *,
        repo_root: str | Path = ".",
        spec: Optional[BlueprintSpec] = None,
        registry: Optional[CapabilitiesRegistry] = None,
        llm: Optional[Any] = None,
        council: Optional[Any] = None,
    ) -> None:
        self.repo_root = Path(repo_root).resolve()
        self.spec: BlueprintSpec = spec or load_default_spec_v3()
        self.registry: CapabilitiesRegistry = registry or CapabilitiesRegistry(repo_root=self.repo_root)

        # 如果传入了 llm 或 council，则构造 LLM probe
        self._llm_probe: Optional[LLMBasedCapabilityProbe] = None
        if llm is not None or council is not None:
            self._llm_probe = LLMBasedCapabilityProbe(
                repo_root=self.repo_root,
                llm=llm,
                council=council,
            )

    # --------------------------------------------------
    # 对外主入口
    # --------------------------------------------------
    def scan_and_update_registry(self) -> CapabilityScanReport:
        """
        扫描所有能力项：

          - 静态规则（import / 文件检查）
          - 可选：LLM / 多模型会议 语义判断

        然后按能力 id 聚合所有 probe 结果，选出“最佳判断”，更新 CapabilitiesRegistry。

        聚合策略（简化版）：
          - status 优先级：done > partial > missing > unknown
          - 同一 status 下，confidence 高的优先
        """
        static_results = self._run_static_import_probes()
        llm_results: List[CapabilityProbeResult] = []

        if self._llm_probe is not None:
            # 先拿到当前 registry 中“还未 done”的能力 id，
            # 避免 LLM 在已经确认 done 的能力上过度消耗。
            not_done_ids: List[str] = []
            for cap in self.spec.capabilities:
                cs = self.registry.get(cap.id)
                if cs is None or cs.status != "done":
                    not_done_ids.append(cap.id)

            llm_raw_results = self._llm_probe.probe_all(
                self.spec.capabilities,
                only_cap_ids=not_done_ids,
            )

            # 转成 CapabilityProbeResult 统一类型
            for r in llm_raw_results:
                llm_results.append(
                    CapabilityProbeResult(
                        capability_id=r.capability_id,
                        status_guess=r.status_guess,
                        confidence=r.confidence,
                        evidence=f"[llm] {r.evidence}",
                        source="llm-probe",
                    )
                )

        # 合并两个来源的结果
        all_results: List[CapabilityProbeResult] = static_results + llm_results

        # 按能力 id 聚类
        by_cap: Dict[str, List[CapabilityProbeResult]] = {}
        for pr in all_results:
            by_cap.setdefault(pr.capability_id, []).append(pr)

        # 逐能力选出最佳判断并更新 registry
        for cap in self.spec.capabilities:
            cap_id = cap.id
            probes = by_cap.get(cap_id, [])
            if not probes:
                # 没有任何 probe 结果，则不强行覆盖现有状态
                continue

            best = self._select_best_probe(probes)

            current = self.registry.get(cap_id)
            current_status = current.status if current is not None else "unknown"

            new_status = current_status
            # 统一的“覆盖策略”：只要新判断比旧状态“更明确”，就覆盖
            if best.status_guess == "done":
                new_status = "done"
            elif best.status_guess == "partial":
                if current_status not in ("done", "partial"):
                    new_status = "partial"
            elif best.status_guess in ("missing", "unknown"):
                if current_status == "unknown":
                    new_status = best.status_guess

            if new_status != current_status:
                self.registry.set_status(
                    cap_id,
                    new_status,
                    evidence=best.evidence,
                )

        return CapabilityScanReport(
            spec_version=self.spec.version,
            repo_root=str(self.repo_root),
            probe_results=all_results,
        )

    def _select_best_probe(
        self,
        probes: List[CapabilityProbeResult],
    ) -> CapabilityProbeResult:
        """
        从多条 probe 结果中选出一个“最佳判断”：

          - 按 status 优先级排序：done > partial > missing > unknown
          - 同一 status 下，confidence 越高越优先
        """
        status_rank = {
            "done": 3,
            "partial": 2,
            "missing": 1,
            "unknown": 0,
        }

        def _key(p: CapabilityProbeResult) -> tuple[int, float]:
            return (status_rank.get(p.status_guess, 0), p.confidence)

        return max(probes, key=_key)

    # --------------------------------------------------
    # 静态 import / 文件规则
    # --------------------------------------------------
    def _run_static_import_probes(self) -> List[CapabilityProbeResult]:
        results: List[CapabilityProbeResult] = []

        # 为了避免 import 失败导致 crash，逐个 try/except
        def _try_import(module_name: str) -> Optional[Any]:
            try:
                return importlib.import_module(module_name)
            except Exception:
                logger.debug("CapabilityScanner: import failed: %s", module_name)
                return None

        # 1) arch.layers.four-layer-logic
        cap_id = "arch.layers.four-layer-logic"
        mod_runtime = _try_import("quentin.runtime.system")
        mod_research = _try_import("quentin.l3.research.layer")
        if mod_runtime and mod_research:
            results.append(CapabilityProbeResult(
                capability_id=cap_id,
                status_guess="done",
                confidence=0.9,
                evidence="Found quentin.runtime.system and quentin.l3.research.layer modules.",
                source="static-import",
            ))
        else:
            results.append(CapabilityProbeResult(
                capability_id=cap_id,
                status_guess="partial" if mod_runtime or mod_research else "missing",
                confidence=0.6,
                evidence="runtime/research modules partially present." if (mod_runtime or mod_research) else "no runtime/research modules found.",
                source="static-import",
            ))

        # 2) research.experiment-orchestrator
        cap_id = "research.experiment-orchestrator"
        mod_exp = _try_import("quentin.l3.research.experiments")
        if mod_exp and hasattr(mod_exp, "ExperimentOrchestrator"):
            results.append(CapabilityProbeResult(
                capability_id=cap_id,
                status_guess="done",
                confidence=0.95,
                evidence="ExperimentOrchestrator class found in quentin.l3.research.experiments.",
                source="static-import",
            ))
        else:
            results.append(CapabilityProbeResult(
                capability_id=cap_id,
                status_guess="missing",
                confidence=0.7,
                evidence="ExperimentOrchestrator not found or module import failed.",
                source="static-import",
            ))

        # 3) obs.eval-harness
        cap_id = "obs.eval-harness"
        mod_eval = _try_import("quentin.eval.harness")
        if mod_eval and hasattr(mod_eval, "EvalHarness"):
            results.append(CapabilityProbeResult(
                capability_id=cap_id,
                status_guess="done",
                confidence=0.95,
                evidence="EvalHarness class found in quentin.eval.harness.",
                source="static-import",
            ))
        else:
            results.append(CapabilityProbeResult(
                capability_id=cap_id,
                status_guess="missing",
                confidence=0.7,
                evidence="EvalHarness not found or module import failed.",
                source="static-import",
            ))

        # 4) research.budget-controller
        cap_id = "research.budget-controller"
        mod_schemas = _try_import("quentin.l3.research.schemas")
        if mod_schemas and hasattr(mod_schemas, "ResearchBudgetConfig"):
            results.append(CapabilityProbeResult(
                capability_id=cap_id,
                status_guess="done",
                confidence=0.9,
                evidence="ResearchBudgetConfig found in quentin.l3.research.schemas.",
                source="static-import",
            ))
        else:
            results.append(CapabilityProbeResult(
                capability_id=cap_id,
                status_guess="missing",
                confidence=0.6,
                evidence="ResearchBudgetConfig not found.",
                source="static-import",
            ))

        # 5) research.auto-experiment-selection
        cap_id = "research.auto-experiment-selection"
        mod_evolution = _try_import("quentin.l3.research.evolution")
        if mod_evolution and hasattr(mod_evolution, "EvolutionStrategyManager"):
            results.append(CapabilityProbeResult(
                capability_id=cap_id,
                status_guess="done",
                confidence=0.9,
                evidence="EvolutionStrategyManager found in quentin.l3.research.evolution.",
                source="static-import",
            ))
        else:
            results.append(CapabilityProbeResult(
                capability_id=cap_id,
                status_guess="missing",
                confidence=0.6,
                evidence="EvolutionStrategyManager not found.",
                source="static-import",
            ))

        # 6) blueprint.spec.machine-readable
        cap_id = "blueprint.spec.machine-readable"
        mod_spec = _try_import("quentin.blueprint.spec")
        if mod_spec and hasattr(mod_spec, "load_default_spec_v3"):
            results.append(CapabilityProbeResult(
                capability_id=cap_id,
                status_guess="done",
                confidence=0.99,
                evidence="load_default_spec_v3 found in quentin.blueprint.spec.",
                source="static-import",
            ))
        else:
            results.append(CapabilityProbeResult(
                capability_id=cap_id,
                status_guess="missing",
                confidence=0.7,
                evidence="Blueprint spec module not importable.",
                source="static-import",
            ))

        # 7) blueprint.gap-tracking
        cap_id = "blueprint.gap-tracking"
        mod_gap = _try_import("quentin.blueprint.gap_tracker")
        if mod_gap and hasattr(mod_gap, "BlueprintGapTracker"):
            results.append(CapabilityProbeResult(
                capability_id=cap_id,
                status_guess="done",
                confidence=0.95,
                evidence="BlueprintGapTracker found in quentin.blueprint.gap_tracker.",
                source="static-import",
            ))
        else:
            results.append(CapabilityProbeResult(
                capability_id=cap_id,
                status_guess="missing",
                confidence=0.6,
                evidence="BlueprintGapTracker not found.",
                source="static-import",
            ))

        # 8) blueprint.auto-improvement-plans
        cap_id = "blueprint.auto-improvement-plans"
        mod_improver = _try_import("quentin.blueprint.improver")
        if mod_improver and hasattr(mod_improver, "BlueprintImprover"):
            results.append(CapabilityProbeResult(
                capability_id=cap_id,
                status_guess="done",
                confidence=0.95,
                evidence="BlueprintImprover found in quentin.blueprint.improver.",
                source="static-import",
            ))
        else:
            results.append(CapabilityProbeResult(
                capability_id=cap_id,
                status_guess="missing",
                confidence=0.6,
                evidence="BlueprintImprover not found.",
                source="static-import",
            ))

        # 9) loops.cognitive.trace-required
        cap_id = "loops.cognitive.trace-required"
        mod_cognitive_loop = _try_import("quentin.cognitive.loop")
        if mod_cognitive_loop and hasattr(mod_cognitive_loop, "CognitiveLoop"):
            # A more specific check: does CognitiveLoop have a traces_store attribute in its __init__ or definition?
            # Inspecting __init__ for 'traces_store' parameter is a good heuristic.
            if inspect.isclass(mod_cognitive_loop.CognitiveLoop):
                init_signature = inspect.signature(mod_cognitive_loop.CognitiveLoop.__init__)
                if "traces_store" in init_signature.parameters:
                    results.append(CapabilityProbeResult(
                        capability_id=cap_id,
                        status_guess="done",
                        confidence=0.9,
                        evidence="CognitiveLoop class found with traces_store parameter in __init__.",
                        source="static-import",
                    ))
                    # Also set the obs.traces-metrics-logs to done here if it passes the same check.
                    # This implies strong integration.
                    # This might overlap, but it's a strong signal.
                else:
                    results.append(CapabilityProbeResult(
                        capability_id=cap_id,
                        status_guess="partial",
                        confidence=0.7,
                        evidence="CognitiveLoop class found, but no explicit traces_store parameter in __init__.",
                        source="static-import",
                    ))
            else:
                results.append(CapabilityProbeResult(
                    capability_id=cap_id,
                    status_guess="partial",
                    confidence=0.7,
                    evidence="CognitiveLoop module found, but CognitiveLoop is not a class.",
                    source="static-import",
                ))
        else:
            results.append(CapabilityProbeResult(
                capability_id=cap_id,
                status_guess="missing",
                confidence=0.6,
                evidence="CognitiveLoop module or class not found.",
                source="static-import",
            ))

        # 10) obs.traces-metrics-logs
        cap_id = "obs.traces-metrics-logs"
        mod_traces_core = _try_import("quentin.traces.execution_trace")
        if mod_traces_core and hasattr(mod_traces_core, "ExecutionTrace") and hasattr(mod_traces_core, "ExecutionTraceStore"):
            results.append(CapabilityProbeResult(
                capability_id=cap_id,
                status_guess="done",
                confidence=0.9,
                evidence="ExecutionTrace and ExecutionTraceStore classes found in quentin.traces.execution_trace.",
                source="static-import",
            ))
        else:
            results.append(CapabilityProbeResult(
                capability_id=cap_id,
                status_guess="partial" if (mod_traces_core and hasattr(mod_traces_core, "ExecutionTrace")) else "missing",
                confidence=0.6,
                evidence="ExecutionTrace and/or ExecutionTraceStore not found in quentin.traces.execution_trace.",
                source="static-import",
            ))

        # 11) arch.kernel.safety-kernel
        cap_id = "arch.kernel.safety-kernel"
        mod_safety = _try_import("quentin.kernel.safety")
        if mod_safety and hasattr(mod_safety, "SafetyKernel"):
            results.append(CapabilityProbeResult(
                capability_id=cap_id,
                status_guess="done",
                confidence=0.95,
                evidence="SafetyKernel class found in quentin.kernel.safety.",
                source="static-import",
            ))
        else:
            results.append(CapabilityProbeResult(
                capability_id=cap_id,
                status_guess="missing",
                confidence=0.7,
                evidence="SafetyKernel not found or module import failed.",
                source="static-import",
            ))

        # 12) memory.fabric.tiers
        cap_id = "memory.fabric.tiers"
        mod_memory_fabric = _try_import("quentin.memory.fabric")
        if mod_memory_fabric and hasattr(mod_memory_fabric, "MemoryFabric") and hasattr(mod_memory_fabric, "MemoryTier") and hasattr(mod_memory_fabric, "MemoryRecord"):
            results.append(CapabilityProbeResult(
                capability_id=cap_id,
                status_guess="done",
                confidence=0.9,
                evidence="MemoryFabric, MemoryTier, and MemoryRecord classes found in quentin.memory.fabric.",
                source="static-import",
            ))
        else:
            results.append(CapabilityProbeResult(
                capability_id=cap_id,
                status_guess="missing",
                confidence=0.6,
                evidence="MemoryFabric, MemoryTier, and/or MemoryRecord not found in quentin.memory.fabric.",
                source="static-import",
            ))

        # 13) loops.sleep.consolidation
        cap_id = "loops.sleep.consolidation"
        mod_sleep_loop = _try_import("quentin.memory.sleep_loop")
        if mod_sleep_loop and hasattr(mod_sleep_loop, "SleepLoop"):
            results.append(CapabilityProbeResult(
                capability_id=cap_id,
                status_guess="done",
                confidence=0.9,
                evidence="SleepLoop class found in quentin.memory.sleep_loop.",
                source="static-import",
            ))
        else:
            results.append(CapabilityProbeResult(
                capability_id=cap_id,
                status_guess="missing",
                confidence=0.6,
                evidence="SleepLoop not found in quentin.memory.sleep_loop.",
                source="static-import",
            ))

        # 14) loops.immune.anomaly-detector
        cap_id = "loops.immune.anomaly-detector"
        mod_immune_loop = _try_import("quentin.immune.loop")
        if mod_immune_loop and hasattr(mod_immune_loop, "ImmuneLoop"):
            results.append(CapabilityProbeResult(
                capability_id=cap_id,
                status_guess="done",
                confidence=0.9,
                evidence="ImmuneLoop class found in quentin.immune.loop.",
                source="static-import",
            ))
        else:
            results.append(CapabilityProbeResult(
                capability_id=cap_id,
                status_guess="missing",
                confidence=0.6,
                evidence="ImmuneLoop not found in quentin.immune.loop.",
                source="static-import",
            ))

        # 15) selfprog.patch-generation
        cap_id = "selfprog.patch-generation"
        mod_self_prog_engine = _try_import("meta_agent.self_programming.engine_v2")
        if mod_self_prog_engine and hasattr(mod_self_prog_engine, "SelfProgrammingEngineV2"):
            results.append(CapabilityProbeResult(
                capability_id=cap_id,
                status_guess="done",
                confidence=0.9,
                evidence="SelfProgrammingEngineV2 class found in meta_agent.self_programming.engine_v2.",
                source="static-import",
            ))
        else:
            results.append(CapabilityProbeResult(
                capability_id=cap_id,
                status_guess="missing",
                confidence=0.6,
                evidence="SelfProgrammingEngineV2 not found in meta_agent.self_programming.engine_v2.",
                source="static-import",
            ))

        # 16) selfprog.test-harness
        cap_id = "selfprog.test-harness"
        mod_sandbox_test_runner = _try_import("meta_agent.self_programming.test_runner")
        if mod_sandbox_test_runner and hasattr(mod_sandbox_test_runner, "SandboxTestRunner"):
            results.append(CapabilityProbeResult(
                capability_id=cap_id,
                status_guess="done",
                confidence=0.9,
                evidence="SandboxTestRunner class found in meta_agent.self_programming.test_runner.",
                source="static-import",
            ))
        else:
            results.append(CapabilityProbeResult(
                capability_id=cap_id,
                status_guess="missing",
                confidence=0.6,
                evidence="SandboxTestRunner not found in meta_agent.self_programming.test_runner.",
                source="static-import",
            ))

        # 17) loops.skill-evolution.from-traces
        cap_id = "loops.skill-evolution.from-traces"
        mod_skill_evolution = _try_import("quentin.skills.evolution")
        if mod_skill_evolution and hasattr(mod_skill_evolution, "SkillEvolutionLoop"):
            results.append(CapabilityProbeResult(
                capability_id=cap_id,
                status_guess="done",
                confidence=0.9,
                evidence="SkillEvolutionLoop class found in quentin.skills.evolution.",
                source="static-import",
            ))
        else:
            results.append(CapabilityProbeResult(
                capability_id=cap_id,
                status_guess="missing",
                confidence=0.6,
                evidence="SkillEvolutionLoop not found in quentin.skills.evolution.",
                source="static-import",
            ))

        # 18) multiagent.council.roles
        cap_id = "multiagent.council.roles"
        mod_multi_council = _try_import("quentin.llm.multi_council")
        if mod_multi_council and hasattr(mod_multi_council, "MultiAICouncil"):
            results.append(CapabilityProbeResult(
                capability_id=cap_id,
                status_guess="done",
                confidence=0.9,
                evidence="MultiAICouncil class found in quentin.llm.multi_council.",
                source="static-import",
            ))
        else:
            results.append(CapabilityProbeResult(
                capability_id=cap_id,
                status_guess="missing",
                confidence=0.6,
                evidence="MultiAICouncil not found in quentin.llm.multi_council.",
                source="static-import",
            ))

        # 19) routing.model-router.data-driven
        cap_id = "routing.model-router.data-driven"
        mod_model_router = _try_import("quentin.models.router")
        if mod_model_router and hasattr(mod_model_router, "ModelRouter") and hasattr(mod_model_router.ModelRouter, "record_usage"):
            results.append(CapabilityProbeResult(
                capability_id=cap_id,
                status_guess="done",
                confidence=0.9,
                evidence="ModelRouter class with record_usage method found in quentin.models.router.",
                source="static-import",
            ))
        else:
            results.append(CapabilityProbeResult(
                capability_id=cap_id,
                status_guess="missing",
                confidence=0.6,
                evidence="ModelRouter or its record_usage method not found in quentin.models.router.",
                source="static-import",
            ))

        # 20) memory.fabric.consolidation
        cap_id = "memory.fabric.consolidation"
        mod_sleep_loop = _try_import("quentin.memory.sleep_loop")
        if mod_sleep_loop and hasattr(mod_sleep_loop, "SleepLoop") and hasattr(mod_sleep_loop.SleepLoop, "_semantic_consolidate_traces"):
            results.append(CapabilityProbeResult(
                capability_id=cap_id,
                status_guess="done",
                confidence=0.9,
                evidence="SleepLoop class with _semantic_consolidate_traces method found in quentin.memory.sleep_loop.",
                source="static-import",
            ))
        else:
            results.append(CapabilityProbeResult(
                capability_id=cap_id,
                status_guess="missing",
                confidence=0.6,
                evidence="SleepLoop or its _semantic_consolidate_traces method not found in quentin.memory.sleep_loop.",
                source="static-import",
            ))

        # 21) multiagent.council.experimental-roles
        cap_id = "multiagent.council.experimental-roles"
        mod_council_manager = _try_import("quentin.council.manager")
        if mod_council_manager and hasattr(mod_council_manager, "CouncilManager") and hasattr(mod_council_manager, "CouncilMemberConfig") and hasattr(mod_council_manager.CouncilMemberConfig, "role"):
            results.append(CapabilityProbeResult(
                capability_id=cap_id,
                status_guess="done",
                confidence=0.9,
                evidence="CouncilManager and CouncilMemberConfig with 'role' attribute found in quentin.council.manager.",
                source="static-import",
            ))
        else:
            results.append(CapabilityProbeResult(
                capability_id=cap_id,
                status_guess="missing",
                confidence=0.6,
                evidence="CouncilManager, CouncilMemberConfig, or 'role' attribute not found in quentin.council.manager.",
                source="static-import",
            ))

        # 22) selfprog.deployment-policy
        cap_id = "selfprog.deployment-policy"
        mod_policy_and_governance = _try_import("quentin.l3.research.policy")
        if mod_policy_and_governance and hasattr(mod_policy_and_governance, "PolicyAndGovernance") and hasattr(mod_policy_and_governance.PolicyAndGovernance, "approve_experiment"):
            results.append(CapabilityProbeResult(
                capability_id=cap_id,
                status_guess="done",
                confidence=0.9,
                evidence="PolicyAndGovernance class with approve_experiment method found in quentin.l3.research.policy.",
                source="static-import",
            ))
        else:
            results.append(CapabilityProbeResult(
                capability_id=cap_id,
                status_guess="missing",
                confidence=0.6,
                evidence="PolicyAndGovernance or its approve_experiment method not found in quentin.l3.research.policy.",
                source="static-import",
            ))

        # 23) memory.fabric.promotion-decay
        cap_id = "memory.fabric.promotion-decay"
        mod_sleep_loop = _try_import("quentin.memory.sleep_loop")
        if mod_sleep_loop and hasattr(mod_sleep_loop, "SleepLoop") and hasattr(mod_sleep_loop.SleepLoop, "_process_sts") and hasattr(mod_sleep_loop.SleepLoop, "_process_mts"):
            results.append(CapabilityProbeResult(
                capability_id=cap_id,
                status_guess="done",
                confidence=0.9,
                evidence="SleepLoop class with _process_sts and _process_mts methods found in quentin.memory.sleep_loop.",
                source="static-import",
            ))
        else:
            results.append(CapabilityProbeResult(
                capability_id=cap_id,
                status_guess="missing",
                confidence=0.6,
                evidence="SleepLoop or its _process_sts and/or _process_mts methods not found in quentin.memory.sleep_loop.",
                source="static-import",
            ))

        # 24) arch.envs.three-environments
        cap_id = "arch.envs.three-environments"
        mod_settings = _try_import("quentin.config.settings")
        if mod_settings and hasattr(mod_settings, "Settings") and hasattr(mod_settings.Settings, "env"):
            results.append(CapabilityProbeResult(
                capability_id=cap_id,
                status_guess="done",
                confidence=0.9,
                evidence="Settings class with 'env' attribute found in quentin.config.settings.",
                source="static-import",
            ))
        else:
            results.append(CapabilityProbeResult(
                capability_id=cap_id,
                status_guess="missing",
                confidence=0.6,
                evidence="Settings class or its 'env' attribute not found in quentin.config.settings.",
                source="static-import",
            ))

        # 25) memory.fabric.cross-domain
        cap_id = "memory.fabric.cross-domain"
        mod_memory_models = _try_import("quentin.memory.models")
        if mod_memory_models and hasattr(mod_memory_models, "MemoryRecord"):
            # A more specific check for 'domain' attribute in MemoryRecord
            # We assume it has a 'domain' field which can be 'cross'.
            if inspect.isclass(mod_memory_models.MemoryRecord):
                init_signature = inspect.signature(mod_memory_models.MemoryRecord.__init__)
                if "domain" in init_signature.parameters:
                    results.append(CapabilityProbeResult(
                        capability_id=cap_id,
                        status_guess="done",
                        confidence=0.9,
                        evidence="MemoryRecord class found with 'domain' parameter in __init__.",
                        source="static-import",
                    ))
                else:
                    results.append(CapabilityProbeResult(
                        capability_id=cap_id,
                        status_guess="partial",
                        confidence=0.7,
                        evidence="MemoryRecord class found, but no explicit 'domain' parameter in __init__.",
                        source="static-import",
                    ))
            else:
                results.append(CapabilityProbeResult(
                    capability_id=cap_id,
                    status_guess="partial",
                    confidence=0.7,
                    evidence="MemoryRecord module found, but MemoryRecord is not a class.",
                    source="static-import",
                ))
        else:
            results.append(CapabilityProbeResult(
                capability_id=cap_id,
                status_guess="missing",
                confidence=0.6,
                evidence="MemoryRecord class not found in quentin.memory.models.",
                source="static-import",
            ))

        # 26) domain.generic-adapter-interface
        cap_id = "domain.generic-adapter-interface"
        mod_domain_base = _try_import("quentin.domain.base")
        if mod_domain_base and hasattr(mod_domain_base, "DomainAdapter"):
            results.append(CapabilityProbeResult(
                capability_id=cap_id,
                status_guess="done",
                confidence=0.9,
                evidence="DomainAdapter class found in quentin.domain.base.",
                source="static-import",
            ))
        else:
            results.append(CapabilityProbeResult(
                capability_id=cap_id,
                status_guess="missing",
                confidence=0.6,
                evidence="DomainAdapter not found in quentin.domain.base.",
                source="static-import",
            ))

        # 27) domain.cross-skill-reuse
        cap_id = "domain.cross-skill-reuse"
        mod_skill_schema = _try_import("quentin.skills.schema")
        mod_skill_registry = _try_import("quentin.skills.registry")
        
        has_skill_spec_with_domain = False
        if mod_skill_schema and hasattr(mod_skill_schema, "SkillSpec") and inspect.isclass(mod_skill_schema.SkillSpec):
            init_signature = inspect.signature(mod_skill_schema.SkillSpec.__init__)
            if "domain" in init_signature.parameters:
                has_skill_spec_with_domain = True

        has_skill_registry_with_domain_filter = False
        if mod_skill_registry and hasattr(mod_skill_registry, "SkillRegistry") and inspect.isclass(mod_skill_registry.SkillRegistry):
            if hasattr(mod_skill_registry.SkillRegistry, "list_skills"):
                list_skills_signature = inspect.signature(mod_skill_registry.SkillRegistry.list_skills)
                if "domain" in list_skills_signature.parameters:
                    has_skill_registry_with_domain_filter = True

        if has_skill_spec_with_domain and has_skill_registry_with_domain_filter:
            results.append(CapabilityProbeResult(
                capability_id=cap_id,
                status_guess="done",
                confidence=0.9,
                evidence="SkillSpec with 'domain' and SkillRegistry with 'list_skills(domain)' found.",
                source="static-import",
            ))
        else:
            results.append(CapabilityProbeResult(
                capability_id=cap_id,
                status_guess="missing",
                confidence=0.6,
                evidence="SkillSpec 'domain' attribute or SkillRegistry 'list_skills(domain)' method not found.",
                source="static-import",
            ))

        # 28) obs.dashboard-minimum
        cap_id = "obs.dashboard-minimum"
        mod_observability = _try_import("quentin.observability.service")
        if mod_observability and hasattr(mod_observability, "ObservabilityService") and hasattr(mod_observability.ObservabilityService, "get_overview"):
            results.append(CapabilityProbeResult(
                capability_id=cap_id,
                status_guess="done",
                confidence=0.9,
                evidence="ObservabilityService class with get_overview method found in quentin.observability.service.",
                source="static-import",
            ))
        else:
            results.append(CapabilityProbeResult(
                capability_id=cap_id,
                status_guess="missing",
                confidence=0.6,
                evidence="ObservabilityService or its get_overview method not found in quentin.observability.service.",
                source="static-import",
            ))

        return results
