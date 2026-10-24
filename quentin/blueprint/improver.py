from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Optional
import json
import logging
import re
import uuid
from pathlib import Path

from quentin.blueprint.gap_tracker import BlueprintGapTracker, BlueprintGapReport, CapabilityGap, CapabilitiesRegistry
from quentin.blueprint.spec import BlueprintSpec, BlueprintCapability, load_default_spec_v3
from quentin.l3.research.experiments import ExperimentTask
from quentin.orchestrator.council import MultiModelCouncil
# Keeping previous imports for compatibility if needed, though new logic uses different approach
from quentin.self_programming.engine import SelfProgrammingEngine
from quentin.evolution.skill_loop import SkillEvolutionLoop
from quentin.orchestrator.core import LanguageModel

logger = logging.getLogger(__name__)

_EVIDENCE_PATH_RE = re.compile(r"(?P<path>[A-Za-z0-9_./\\-]+\\.py)")


def resolve_existing_file_path(
    *,
    repo_root: str,
    evidence: Optional[str],
    section: Optional[str],
) -> Optional[str]:
    """
    Resolve a real file path for patch generation without guessing non-existent paths.

    Priority:
    1) Parse paths from `evidence` and keep only those that exist.
    2) Fall back to a conservative, section-based canonical file list (only if exists).
    """
    repo = Path(repo_root).resolve()
    candidates: List[str] = []

    if evidence:
        for m in _EVIDENCE_PATH_RE.finditer(evidence):
            p = m.group("path").replace("\\", "/").lstrip("./")
            if p not in candidates:
                candidates.append(p)

    section_defaults: Dict[str, List[str]] = {
        "memory": ["quentin/memory/fabric.py", "quentin/memory/sleep_loop.py"],
        "loops": ["quentin/runtime/cognitive_loop.py", "quentin/memory/sleep_loop.py"],
        "self-programming": ["meta_agent/self_programming/engine_v2.py"],
        "observability": ["meta_agent/observability/service.py", "quentin/observability/service.py"],
        "research": ["quentin/l3/research/experiment_orchestrator.py", "quentin/l3/research/eval_harness.py"],
        "multi-agent": ["quentin/orchestrator/council.py", "quentin/routing/model_router.py"],
    }
    if section and section in section_defaults:
        for p in section_defaults[section]:
            if p not in candidates:
                candidates.append(p)

    for rel in candidates:
        try:
            if (repo / rel).exists():
                return rel
        except Exception:
            continue
    return None


@dataclass
class GapImprovementPlan:
    """
    针对单个蓝皮书能力 gap 的改进计划。

    - capability_id: 对应 BlueprintCapability.id
    - gap_status: "missing" / "partial"
    - priority: 1=最高 优先级数字越小越重要
    - experiment_name: 建议的实验名称
    - experiment_description: 实验的总体说明
    - tasks: 实验中的任务列表（ExperimentTask 形式）
    """
    capability_id: str
    gap_status: str
    priority: int
    experiment_name: str
    experiment_description: str
    tasks: List[ExperimentTask]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "capability_id": self.capability_id,
            "gap_status": self.gap_status,
            "priority": self.priority,
            "experiment_name": self.experiment_name,
            "experiment_description": self.experiment_description,
            "tasks": [t.to_dict() for t in self.tasks],
        }


class BlueprintImprover:
    """
    蓝皮书自迭代的“策划器”：

      - 可以只用一个 LLM（llm_client）
      - 也可以用 MultiModelCouncil 做多模型“开会”，然后由会议结果产生计划

    用法：
      improver = BlueprintImprover(llm=..., council=council_or_None)
      plans = improver.propose_improvement_plans(gap_report)
      （然后交给 ExperimentOrchestrator.create_experiment(...)）
    """

    def __init__(
        self,
        *,
        llm: Optional[Any] = None,
        council: Optional[MultiModelCouncil] = None,
        default_domain: str = "blueprint-improvement",
        # Compatibility args from previous version in 100.md
        repo_root: Optional[Any] = None,
        tracker: Optional[BlueprintGapTracker] = None,
        engine: Optional[SelfProgrammingEngine] = None,
        skill_evolution: Optional[SkillEvolutionLoop] = None,
    ) -> None:
        if llm is None and council is None:
            raise ValueError("Either llm or council must be provided.")
        self.llm = llm
        self.council = council
        self.default_domain = default_domain
        
        # Store compatibility args if provided, they might be used by methods from 100.md if I keep them?
        # The instructions say "BlueprintImprover... 核心目标: 读取 BlueprintGapReport... 产出: 针对每个 gap 的实验/任务计划"
        # This replaces the logic in 100.md which directly called skill_evolution.
        # However, to avoid breaking run_self_evolution_cycle.py (which calls run_once), I should probably adapt run_once to use this new logic OR keep both.
        # run_self_evolution_cycle.py expects:
        # improver = BlueprintImprover(..., engine=..., skill_evolution=..., llm=...)
        # result = improver.run_once(max_gaps=...)
        # result keys: blueprint_report, promotable_patches...
        
        # So I MUST reimplement run_once to use the new planning logic BUT still bridge to patch generation if I want to maintain the "closed loop" described in 100.md.
        # Or, 107.md logic is "generate experiment plans", while 100.md logic was "generate patches directly".
        # 107.md seems to be a higher level "planning" step.
        # I will keep run_once for compatibility but upgrade it to use the new planning capability if possible, or just keep the old logic side-by-side.
        # Given "BlueprintImprover: 蓝皮书自迭代的‘策划器’", I will try to merge them.
        
        if tracker is not None:
            self.tracker = tracker
        elif repo_root is not None:
            default_spec = load_default_spec_v3()
            default_registry = CapabilitiesRegistry(repo_root=repo_root)
            self.tracker = BlueprintGapTracker(spec=default_spec, registry=default_registry, repo_root=repo_root)
        else:
            self.tracker = None # If neither tracker nor repo_root is provided, tracker cannot be created.
        self.engine = engine
        self.skill_evolution = skill_evolution

    # --------------------------------------------------
    # 核心接口：根据 gap 报告生成改进计划
    # --------------------------------------------------
    def propose_improvement_plans(
        self,
        gap_report: BlueprintGapReport,
        *,
        max_gaps: int = 10,
    ) -> List[GapImprovementPlan]:
        """
        针对 gap_report 中的 missing/partial 能力，生成改进实验计划。

        v1 策略：
          - 优先处理 missing，然后是 partial
          - 最多处理 max_gaps 条能力
          - 每个能力调用一次 LLM / MultiModelCouncil，要求输出 JSON
        """
        candidates: List[CapabilityGap] = []
        candidates.extend(gap_report.missing)
        candidates.extend(gap_report.partial)
        candidates = candidates[:max_gaps]

        plans: List[GapImprovementPlan] = []

        for gap in candidates:
            try:
                plan = self._plan_for_single_gap(gap)
            except Exception:
                logger.exception("BlueprintImprover: failed to plan for cap=%s", gap.capability.id)
                continue
            if plan is not None:
                plans.append(plan)

        return plans

    # --------------------------------------------------
    # Compatibility Method: run_once (from 100.md)
    # --------------------------------------------------
    def run_once(
        self,
        *,
        max_gaps: int = 20,
        test_suites: Optional[List[str]] = None,
        extra_context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Compatibility method for run_self_evolution_cycle.py.
        
        Previously: Scan -> Gaps -> Issues -> Patches -> Tests.
        Now we have: Scan -> Gaps -> Plans -> Experiments.
        
        To keep run_self_evolution_cycle working without rewriting it entirely, 
        I will maintain the "Gaps -> Issues -> Patches" flow here using the *old* logic 
        (directly using skill_evolution), but using the new GapTracker if available.
        
        If self.tracker is the NEW GapTracker (which returns BlueprintGapReport with CapabilityGap objects),
        I need to adapt the output to what _gaps_to_issues expects.
        """
        if not self.tracker:
             raise ValueError("BlueprintImprover initialized without tracker/repo_root, cannot run_once.")
             
        # 1) Scan
        report = self.tracker.scan()
        
        # Report is BlueprintGapReport.
        # In 98.md/100.md, report.gaps was a list of BlueprintGap dataclass (path, issue_type, etc.)
        # In 107.md, report.missing/partial are lists of CapabilityGap (capability, status).
        
        # We need to bridge this.
        # CapabilityGap doesn't necessarily have a file path unless we infer it or it's in the status?
        # The CapabilityStatus has 'evidence' which might be empty.
        # The BlueprintCapability doesn't strictly have a file path in 107.md spec (it has section/id).
        # Wait, 107.md spec does NOT have 'path' in BlueprintCapability. 
        # 98.md ComponentSpec HAD 'path'.
        # This means 107.md is a semantic spec, 98.md was a file-structure spec.
        # They are different levels of abstraction. 
        
        # For run_once to work (generate patches), it needs file paths.
        # I will try to map CapabilityGap back to file paths if possible, or fallback to "module level" issues.
        # Or, I can stick to the logic from 100.md if I had kept the old GapTracker.
        # But I overwrote GapTracker.
        
        # Let's look at how to adapt.
        # I will convert CapabilityGaps to the "issue" format expected by SkillEvolutionLoop.
        # SkillEvolutionLoop needs: target.file_path (if we want LLM to edit it).
        # If we don't have file path, we can't generate a patch easily.
        
        # Quick fix: Assume capability ID maps to a file path or we ask LLM to find/create it.
        # For now, let's just create "general issues" and see if SkillEvolutionLoop can handle them 
        # (it currently checks for file_path, so it might fail to generate patch if missing).
        
        # To support the "old" flow effectively, we might need to re-introduce file-level gap tracking 
        # or just accept that "run_once" will produce plans (new way) instead of patches (old way)?
        # But run_self_evolution_cycle expects patches. 
        
        # I will implement a "best effort" bridge.
        # Historical note: previous versions constructed guessed file paths based on capability IDs.
        
        candidates = []
        candidates.extend(report.missing)
        candidates.extend(report.partial)
        candidates = candidates[:max_gaps]
        
        issues = []
        unresolved_gaps: List[Dict[str, Any]] = []
        for gap in candidates:
            cap_id = gap.capability.id
            file_path = resolve_existing_file_path(
                repo_root=".",
                evidence=getattr(gap.status, "evidence", None),
                section=getattr(gap.capability, "section", None),
            )

            if not file_path:
                unresolved_gaps.append(
                    {
                        "capability_id": cap_id,
                        "section": getattr(gap.capability, "section", None),
                        "gap_status": gap.gap_status,
                        "evidence": getattr(gap.status, "evidence", None),
                        "reason": "no_resolvable_file_path",
                    }
                )
                continue
                
            issues.append({
                "issue_id": f"gap::{cap_id}",
                "source": "blueprint_gap",
                "target": {
                    "target_type": "python_module",
                    "file_path": file_path,
                    "identifier": cap_id
                },
                "reason": f"Capability {cap_id} ({gap.capability.name}) is {gap.gap_status}. Desc: {gap.capability.description}",
                "metrics": {"severity": "medium"}
            })
            
        # Now delegate to skill_evolution
        if not self.skill_evolution or not self.engine:
             logger.warning("BlueprintImprover.run_once: engine/skill_evolution not available, returning empty.")
             return {"blueprint_report": report.to_dict(), "promotable_patches": []}

        patch_candidates = self.skill_evolution.generate_patches_from_issues(issues)
        
        suites = test_suites or ["unit", "static_analysis"]
        patch_reports = self.skill_evolution.evaluate_patches(
            patch_candidates,
            test_suites=suites,
            extra_context=extra_context or {"source": "blueprint_improver"},
        )

        promotable = self._select_promotable_patches(
            patch_reports,
            max_promote=1, # Keep the max_promote argument for future use if needed
        )

        return {
            "blueprint_report": report.to_dict(),
            "issues": issues,
            "unresolved_gaps": unresolved_gaps,
            "patch_candidates": [p.to_dict() for p in patch_candidates],
            "patch_reports": [r.to_dict() for r in patch_reports],
            "promotable_patches": [r.to_dict() for r in promotable],
        }

    def _select_promotable_patches(
        self,
        patch_reports: List[PatchTestReport],
        max_promote: int = 1,
    ) -> List[PatchTestReport]:
        """
        根据补丁的测试报告选择可推广的补丁。
        一个简单的策略：选择通过测试的补丁。
        """
        promotable = [report for report in patch_reports if report.success]
        # Sort by some metric if available, for now just take the first few
        return promotable[:max_promote]


    # --------------------------------------------------
    # 内部：单个能力的计划生成
    # --------------------------------------------------
    def _plan_for_single_gap(self, gap: CapabilityGap) -> Optional[GapImprovementPlan]:
        cap = gap.capability
        gs = gap.gap_status

        prompt = self._build_prompt_for_gap(cap, gs)

        if self.council is not None:
            # 用多模型会议结果作为“最终答复”，final_answer 里要求是 JSON
            deliberation = self.council.deliberate(
                question=prompt,
                context={
                    "capability_id": cap.id,
                    "section": cap.section,
                    "gap_status": gs,
                    "blueprint_version": "v3",
                },
            )
            raw = deliberation.final_answer
        else:
            raw = _call_llm(self.llm, prompt)

        try:
            # Try to extract JSON if wrapped in markdown
            if "```json" in raw:
                raw = raw.split("```json")[1].split("```")[0].strip()
            elif "```" in raw:
                raw = raw.split("```")[1].strip()
                
            data = json.loads(raw)
        except Exception:
            logger.warning(
                "BlueprintImprover: LLM output for cap=%s is not valid JSON, raw=%r",
                cap.id,
                raw[:300],
            )
            return None

        priority = int(data.get("priority", 5))
        exp_name = data.get("experiment_name") or f"improve::{cap.id}"
        exp_desc = data.get("experiment_description") or cap.description

        tasks_json = data.get("tasks") or []
        tasks: List[ExperimentTask] = []

        for i, t in enumerate(tasks_json):
            goal = t.get("goal") or f"Improve capability {cap.id} (task {i})"
            context = t.get("context") or {}
            # 确保带上 domain 信息
            if "domain" not in context:
                context["domain"] = self.default_domain
            task_id = t.get("task_id") or f"{cap.id}::t{i}"
            tasks.append(
                ExperimentTask(
                    task_id=task_id,
                    goal=goal,
                    context=context,
                )
            )

        return GapImprovementPlan(
            capability_id=cap.id,
            gap_status=gs,
            priority=priority,
            experiment_name=exp_name,
            experiment_description=exp_desc,
            tasks=tasks,
        )

    # --------------------------------------------------
    # Prompt 设计
    # --------------------------------------------------
    def _build_prompt_for_gap(self, cap: BlueprintCapability, gap_status: str) -> str:
        """
        把单个 capability gap 转成 LLM 可理解的描述，
        要求输出一个 JSON 改进方案。
        """
        cap_json = json.dumps(cap.to_dict(), ensure_ascii=False, indent=2)
        return (
            "你是一名帮助构建通用自进化智能体的系统架构师。\n"
            "我们有一份蓝皮书（Meta-Agent v3），其中定义了很多能力项。\n"
            "现在有一个能力还没有完全实现，请你为它设计一个“研究实验计划”，" 
            "帮助系统在 sandbox/staging 环境中逐步实现该能力。\n\n"
            "【能力定义（蓝皮书项）】\n"
            f"{cap_json}\n\n"
            f"【当前 gap 状态】{gap_status}\n\n"
            "请你输出一个 JSON 对象，字段必须包含：\n"
            "  - \"priority\": 数字，1=最高优先级，数字越小越重要。\n"
            "  - \"experiment_name\": 此能力的实验名称（简短英文或中英文混合）。\n"
            "  - \"experiment_description\": 实验要验证或实现的内容简介。\n"
            "  - \"tasks\": 一个数组，每个元素是一个任务对象：\n"
            "      * \"goal\": 自然语言描述该任务要做什么（例如：实现某个模块骨架、补充测试等）。\n"
            "      * \"context\": 一个 JSON 对象（可为空），用于提供额外信息（如建议的文件路径、需要使用的循环/模块名称等）。\n\n"
            "要求：\n"
            "  - 不要写任何解释性文字，只输出一个 JSON 对象。\n"
            "  - 任务要尽量具体、可执行，适合交给一个通用智能体 runtime 去跑。\n"
        )


def _call_llm(llm: Any, prompt: str) -> str:
    """
    统一 LLM 调用接口：

      - llm.complete(prompt=...)
      - llm.generate(prompt=...)
      - 直接可调用 llm(prompt)
    """
    from quentin.llm.context_budget import apply_context_budget
    guarded_prompt, guard = apply_context_budget(prompt_text=prompt)
    if guard.should_block:
        raise ValueError(
            f"context budget blocked: reason={guard.reason} total={guard.total_tokens} window={guard.tokens}"
        )
    if hasattr(llm, "complete"):
        return llm.complete(guarded_prompt)
    if hasattr(llm, "generate"):
        try:
             return llm.generate(prompt=guarded_prompt)
        except TypeError:
             return llm.generate(messages=[{"role": "user", "content": guarded_prompt}])
        except Exception:
             pass
    if callable(llm):
        return llm(guarded_prompt)
    raise RuntimeError("LLM client has no complete/generate/callable interface")
