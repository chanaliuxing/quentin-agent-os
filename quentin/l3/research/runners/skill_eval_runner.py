# quentin/l3/research/runners/skill_eval_runner.py
from __future__ import annotations

from typing import Any, Dict, Optional, Callable
import logging
import importlib
from types import ModuleType

from quentin.l3.research.orchestrator import ExperimentRunner
from quentin.l3.research.experiments import (
    ExperimentConfig,
    VariantConfig,
    VariantResult,
)
from quentin.eval.spec import EvalDatasetSpec, EvalTaskSpec
from quentin.eval.harness import EvalHarness
from quentin.skills.manager import SkillManager, SkillSpec

logger = logging.getLogger(__name__)


# This represents the function signature of a skill to be evaluated
SkillFunction = Callable[[Dict[str, Any], Optional[Dict[str, Any]], Optional[Dict[str, Any]]], Dict[str, Any]]


class SkillEvalRunner(ExperimentRunner):
    """
    针对 Skill 的评测 Runner。

    用于评测新生成的 Skill 实现是否比基线（或无实现）更好。
    """

    def __init__(
        self,
        *,
        eval_harness: Optional[EvalHarness] = None,
        skill_manager: Optional[SkillManager] = None,
    ) -> None:
        try:
            self.eval_harness = eval_harness or EvalHarness(variants_runtimes={})
        except TypeError:
            self.eval_harness = eval_harness or EvalHarness()
        self.skill_manager = skill_manager or SkillManager() # Assumes default repo_root

    def run_variant(
        self,
        experiment: ExperimentConfig,
        variant: VariantConfig,
        context: Optional[Dict[str, Any]] = None,
    ) -> VariantResult:
        ctx = dict(context or {})

        # The dataset for evaluating skills should be provided in context
        dataset: Optional[EvalDatasetSpec] = ctx.get("skill_dataset") or ctx.get("eval_dataset")
        if dataset is None:
            logger.warning(
                "SkillEvalRunner: no EvalDatasetSpec provided in context "
                "(skill_dataset / eval_dataset missing). Using empty dataset."
            )
            dataset = EvalDatasetSpec(
                dataset_id="empty",
                name="empty",
                description="Empty dataset (no tasks).",
                component="skill_eval",
                tasks=[],
            )

        # The core evaluation function for a single task
        def _eval_fn(task: EvalTaskSpec, variant_cfg: VariantConfig, local_ctx: Dict[str, Any]) -> Dict[str, Any]:
            return self._execute_skill_variant(task, variant_cfg, local_ctx)

        return self.eval_harness.run_dataset(
            experiment=experiment,
            variant=variant,
            dataset=dataset,
            eval_fn=_eval_fn,
            context=ctx,
        )

    def _execute_skill_variant(
        self,
        task: EvalTaskSpec,
        variant: VariantConfig,
        context: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        执行特定 variant 的技能函数。
        """
        skill_id = task.metadata.get("skill_id")
        if not skill_id:
            return {"success": False, "score": 0.0, "notes": "No skill_id in task metadata"}

        sk_spec: Optional[SkillSpec] = self.skill_manager.registry.get(skill_id)
        if not sk_spec:
            return {"success": False, "score": 0.0, "notes": f"Skill {skill_id} not found"}

        # Determine which implementation to use
        impl_module = None
        impl_symbol = None

        if variant.variant_id == "baseline":
            # For baseline, use the currently active/implemented version if any
            if sk_spec.is_active and sk_spec.implementation_module and sk_spec.implementation_symbol:
                impl_module = sk_spec.implementation_module
                impl_symbol = sk_spec.implementation_symbol
            else:
                return {"success": False, "score": 0.0, "notes": "Baseline: Skill not active or implemented"}
        elif variant.variant_id == "candidate":
            # For candidate, use the implementation hint from variant config
            if variant.implementation_hint:
                parts = variant.implementation_hint.split(':')
                if len(parts) == 2:
                    impl_module, impl_symbol = parts
                else:
                    return {"success": False, "score": 0.0, "notes": "Candidate: Invalid implementation_hint format"}
            else:
                # If no hint, it means the generated code wasn't passed, treat as fail
                return {"success": False, "score": 0.0, "notes": "Candidate: No implementation_hint provided"}
        else:
            return {"success": False, "score": 0.0, "notes": f"Unknown variant_id: {variant.variant_id}"}


        if not impl_module or not impl_symbol:
            return {"success": False, "score": 0.0, "notes": "No implementation module/symbol for variant"}

        try:
            # Dynamically load and execute the skill
            module: ModuleType = importlib.import_module(impl_module)
            func: SkillFunction = getattr(module, impl_symbol)

            # Prepare inputs for the skill function from EvalTaskSpec
            skill_input_step = task.input_payload.get("step_input", {})
            skill_input_goal = task.input_payload.get("goal_input", {})
            skill_input_context = task.input_payload.get("context_input", {})

            result_from_skill = func(
                skill_input_step,
                skill_input_goal,
                skill_input_context,
            )

            # Compare result with expected_output from EvalTaskSpec
            # This is a basic comparison; real eval would be more complex
            expected_output = task.expected_output or {}
            
            # Assuming expected_output contains 'status': 'ok' or similar for a success check
            # and potentially a 'result' field to compare
            
            skill_status = result_from_skill.get("status")
            skill_output = result_from_skill.get("result")
            
            success = (skill_status == "ok") # Basic check
            score = 1.0 if success else 0.0
            
            # More advanced scoring could compare skill_output with expected_output

            return {
                "success": success,
                "score": score,
                "raw_skill_output": result_from_skill,
                "notes": f"Skill '{impl_symbol}' executed via variant '{variant.variant_id}'",
                "used_implementation": f"{impl_module}:{impl_symbol}"
            }

        except ModuleNotFoundError:
            logger.error(f"SkillEvalRunner: Module '{impl_module}' not found for skill {skill_id}")
            return {"success": False, "score": 0.0, "notes": f"Module {impl_module} not found"}
        except AttributeError:
            logger.error(f"SkillEvalRunner: Function '{impl_symbol}' not found in module '{impl_module}' for skill {skill_id}")
            return {"success": False, "score": 0.0, "notes": f"Function {impl_symbol} not found"}
        except Exception as e:
            logger.exception(f"SkillEvalRunner: Error executing skill {skill_id} variant {variant.variant_id}")
            return {"success": False, "score": 0.0, "notes": f"Execution error: {e}"}
