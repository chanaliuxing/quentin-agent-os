from __future__ import annotations

from typing import Any, Dict, Optional, List
from pathlib import Path
from importlib import import_module, reload
import json
import logging
import textwrap
import uuid # For generating temporary file names
from dataclasses import dataclass, asdict

from quentin.skills.manager import SkillManager
from quentin.skills.schema import SkillDefinition # UPDATED from SkillSpec
from quentin.llm.router import ModelRouter
from quentin.llm.client import call_llm
from quentin.self_programming.engine import SelfProgrammingEngine # NEW
from quentin.utils.time import now_iso

logger = logging.getLogger(__name__)


# ---------- 数据结构 ----------

@dataclass
class SkillImplementationRequest:
    """
    请求：为某个 Skill 生成代码实现。

    - skill_id : 要实现的技能 ID
    - dry_run  : 只生成代码并打印，不写入文件、不更新 registry
    """
    skill_id: str
    dry_run: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class SkillImplementationResult:
    """
    结果：记录一次实现尝试的详情，方便 SleepLoop / Research Layer 分析。

    - skill_id       : 技能 ID
    - success        : 是否成功写入 + 导入
    - module         : 实现模块路径（字符串）
    - symbol         : 函数名
    - error          : 错误信息（如果失败）
    - llm_model      : 使用的模型名
    - created_at     : 时间戳
    - raw_llm_output : 原始 LLM 输出（用于后续自我迭代）
    """
    skill_id: str
    success: bool
    module: Optional[str]
    symbol: Optional[str]
    error: Optional[str]
    llm_model: Optional[str]
    created_at: str
    raw_llm_output: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ---------- 引擎主体 ----------

class SkillImplementationEngine:
    """
    SkillImplementationEngine v1

    职责：
    - 针对单个 SkillSpec 生成 Python 函数实现
    - 写到 quentin/tools/auto_skills.py
    - 简单导入测试
    - 成功后调用 SkillManager.mark_implemented()

    注意：
    - 这是 “Blueprint 3.4 技能进化循环” 的一部分，只负责“第一次实现”。
    - 真正的回归测试、A/B 对比、自动上线 → 交给 SelfProgrammingEngine 和 Research Layer。
    """

    def __init__(
        self,
        *,
        repo_root: str | Path = ".",
        skill_manager: Optional[SkillManager] = None,
        model_router: Optional[ModelRouter] = None,
        auto_skills_module: str = "quentin.tools.auto_skills",
        auto_skills_file: str | Path = "quentin/tools/auto_skills.py",
        self_programming_engine: Optional[SelfProgrammingEngine] = None, # NEW
    ) -> None:
        self.repo_root = Path(repo_root).resolve()
        self.skill_manager = skill_manager or SkillManager(repo_root=self.repo_root)
        self.model_router = model_router or ModelRouter()
        self.auto_skills_module = auto_skills_module
        self.auto_skills_file = self.repo_root / auto_skills_file
        try:
            self.self_programming_engine = self_programming_engine or SelfProgrammingEngine(repo_root=self.repo_root) # NEW
        except TypeError:
            # fallback if engine __init__ signature is different
            self.self_programming_engine = self_programming_engine or SelfProgrammingEngine()
        self._ensure_auto_skills_file()

    # ---------- 公共入口 ----------

    def implement_skill(self, req: SkillImplementationRequest) -> SkillImplementationResult:
        """
        核心入口：为指定 skill_id 生成实现。
        """
        sk = self.skill_manager.registry.get(req.skill_id)
        if sk is None:
            msg = f"Skill {req.skill_id} not found"
            logger.error(msg)
            return SkillImplementationResult(
                skill_id=req.skill_id,
                success=False,
                module=None,
                symbol=None,
                error=msg,
                llm_model=None,
                created_at=now_iso(),
                raw_llm_output="",
            )

        # If already implemented and not a dry run, just return success
        if sk.is_implemented and not req.dry_run:
            msg = "Skill already implemented"
            logger.info("SkillImplementationEngine: %s", msg)
            return SkillImplementationResult(
                skill_id=sk.skill_id,
                success=True,
                module=sk.implementation_module,
                symbol=sk.implementation_symbol,
                error=None,
                llm_model=None,
                created_at=now_iso(),
                raw_llm_output="",
            )

        # 1) 准备 prompt，调用 LLM 生成代码
        cfg_model = self.model_router.route(mode="code", task_type=sk.domain or "core")
        system_prompt, user_prompt_text = self._build_prompts(sk)
        raw_llm_output = call_llm(cfg_model, user_prompt=user_prompt_text, system_prompt=system_prompt).strip()

        # 2) 解析 JSON：{"function_name": "...", "code": "def ...", "notes": "..."}
        try:
            snippet = self._extract_json_snippet(raw_llm_output)
            func_name = snippet.get("function_name")
            code_str = snippet.get("code")
            if not func_name or not code_str:
                raise ValueError("Missing function_name or code in LLM output")
        except Exception as e:
            logger.exception("SkillImplementationEngine: failed to parse LLM output for skill %s", sk.skill_id)
            return SkillImplementationResult(
                skill_id=sk.skill_id,
                success=False,
                module=None,
                symbol=None,
                error=f"parse_error: {e}",
                llm_model=getattr(cfg_model, "model", None),
                created_at=now_iso(),
                raw_llm_output=raw_llm_output,
            )

        # 3) Dry run mode: just return the code without evaluation or writing
        if req.dry_run:
            logger.info("SkillImplementationEngine: dry_run=True, not writing to file.")
            return SkillImplementationResult(
                skill_id=sk.skill_id,
                success=True,
                module=self.auto_skills_module,
                symbol=func_name,
                error=None,
                llm_model=getattr(cfg_model, "model", None),
                created_at=now_iso(),
                raw_llm_output=raw_llm_output,
            )

        # --- Experimentation Phase ---
        # Temporarily write the generated code to a unique file for evaluation
        temp_module_name = f"quentin.tools.auto_skills_temp_{uuid.uuid4().hex}"
        temp_file_path = self.repo_root / "quentin" / "tools" / f"auto_skills_temp_{uuid.uuid4().hex}.py"
        try:
            self._write_temp_function_file(temp_file_path, func_name, code_str)
        except Exception as e:
            logger.exception("SkillImplementationEngine: failed to write temporary function file.")
            return SkillImplementationResult(
                skill_id=sk.skill_id,
                success=False,
                module=None,
                symbol=None,
                error=f"temp_file_write_error: {e}",
                llm_model=getattr(cfg_model, "model", None),
                created_at=now_iso(),
                raw_llm_output=raw_llm_output,
            )

        experiment_id = None
        eval_result = None
        try:
            # 4) Create an experiment to evaluate the new skill
            exp_config = self._create_skill_evaluation_experiment(sk, func_name, temp_module_name)
            experiment_id = exp_config.experiment_id

            # For now, let's assume a simple EvalDataset can be constructed or passed in context
            # In a real scenario, this EvalDataset would be specific to the skill and its domain
            # For this MVP, we create a very basic stub dataset for testing if the function runs
            # This is where a more sophisticated eval harness would get/generate tasks
            
            # Construct a dummy EvalDatasetSpec for basic import/execution test
            eval_dataset = self._create_dummy_skill_eval_dataset(sk, func_name, code_str)

            eval_result = self.research_interface.run_experiment(
                experiment_id=experiment_id,
                context={"skill_dataset": eval_dataset},
            )

            # 5) Analyze experiment results
            if eval_result and eval_result.best_variant_id == "candidate":
                logger.info(
                    "SkillImplementationEngine: Experiment %s passed, candidate skill %s/%s performed best.",
                    experiment_id, sk.skill_id, func_name
                )
                # If candidate is best, proceed to permanently save and mark implemented
                self._append_function_to_file(func_name, code_str, sk)
                self.skill_manager.mark_implemented(
                    skill_id=sk.skill_id,
                    module=self.auto_skills_module,
                    symbol=func_name,
                    auto_activate=True,
                )
                return SkillImplementationResult(
                    skill_id=sk.skill_id,
                    success=True,
                    module=self.auto_skills_module,
                    symbol=func_name,
                    error=None,
                    llm_model=getattr(cfg_model, "model", None),
                    created_at=now_iso(),
                    raw_llm_output=raw_llm_output,
                )
            else:
                msg = f"Experiment {experiment_id} failed or baseline performed better for skill {sk.skill_id}."
                logger.warning(msg)
                return SkillImplementationResult(
                    skill_id=sk.skill_id,
                    success=False,
                    module=None,
                    symbol=None,
                    error=msg,
                    llm_model=getattr(cfg_model, "model", None),
                    created_at=now_iso(),
                    raw_llm_output=raw_llm_output,
                )
        except Exception as e:
            logger.exception("SkillImplementationEngine: Error during skill evaluation experiment.")
            return SkillImplementationResult(
                skill_id=sk.skill_id,
                success=False,
                module=None,
                symbol=None,
                error=f"experiment_error: {e}",
                llm_model=getattr(cfg_model, "model", None),
                created_at=now_iso(),
                raw_llm_output=raw_llm_output,
            )
        finally:
            # Clean up temporary file
            try:
                temp_file_path.unlink(missing_ok=True)
            except Exception as e:
                logger.error(f"Failed to delete temporary skill file {temp_file_path}: {e}")

    # ---------- prompts & 解析 ----------
    # ... (unchanged) ...

    # ---------- 文件操作 ----------
    # ... (unchanged _ensure_auto_skills_file, _append_function_to_file) ...



    def _create_skill_evaluation_experiment(
        self,
        sk: SkillSpec,
        func_name: str,
        temp_module_name: str,
    ) -> ExperimentConfig:
        """
        Creates an experiment configuration for evaluating a generated skill.
        """
        variants: List[VariantConfig] = []

        # Baseline: current implemented version of the skill (if any)
        if sk.is_implemented and sk.implementation_module and sk.implementation_symbol:
            variants.append(
                VariantConfig(
                    variant_id="baseline",
                    name="Current Implementation",
                    description=f"Existing implementation of skill {sk.skill_id}",
                    target_component="skill_eval",
                    implementation_hint=f"{sk.implementation_module}:{sk.implementation_symbol}",
                )
            )
        else:
            # If no existing implementation, baseline is a 'no-op' or always-fail variant
            variants.append(
                VariantConfig(
                    variant_id="baseline",
                    name="No Implementation",
                    description=f"Skill {sk.skill_id} is not yet implemented (baseline).",
                    target_component="skill_eval",
                    implementation_hint="quentin.l3.research.runners.skill_eval_runner:_stub_skill_function", # A stub that always fails
                )
            )

        # Candidate: the newly generated code
        variants.append(
            VariantConfig(
                variant_id="candidate",
                name="Generated Code",
                description=f"LLM-generated code for skill {sk.skill_id}",
                target_component="skill_eval",
                implementation_hint=f"{temp_module_name}:{func_name}",
            )
        )

        exp_config = self.research_interface.orchestrator.create_experiment(
            name=f"Skill Eval: {sk.title} ({sk.skill_id[:8]})",
            purpose=f"Evaluate new LLM-generated implementation for skill {sk.skill_id}",
            target_component="skill_eval",
            created_by="SkillImplementationEngine",
            metadata={"skill_id": sk.skill_id, "skill_description": sk.description},
            variants=variants,
        )
        return exp_config
        
    def _create_dummy_skill_eval_dataset(self, sk: SkillSpec, func_name: str, code_str: str) -> EvalDatasetSpec:
        """
        Creates a dummy EvalDatasetSpec for basic testing of the generated skill.
        In a real system, this would come from a dedicated dataset for the skill.
        """
        # Example: a single task that just tries to call the function and expects a successful dict return
        dummy_task = EvalTaskSpec(
            task_id=f"test_skill_{sk.skill_id}",
            description=f"Test basic execution of generated skill '{sk.title}'",
            component="skill_eval",
            input_payload={
                "step_input": {"param1": "value1"}, # Minimal input to avoid exceptions
                "goal_input": {},
                "context_input": {}
            },
            expected_output={"status": "ok"}, # Expect the skill to return {"status": "ok", ...}
            metadata={"skill_id": sk.skill_id}
        )
        
        return EvalDatasetSpec(
            dataset_id=f"skill_eval_dataset_{sk.skill_id[:8]}",
            name=f"Dataset for {sk.title} skill evaluation",
            description="Auto-generated dummy dataset for initial skill eval.",
            component="skill_eval",
            tasks=[dummy_task]
        )

    # ---------- prompts & 解析 ----------

    def _build_prompts(self, sk: SkillSpec) -> tuple[str, str]:
        """
        为代码生成构造 system / user prompt。
        """
        system_prompt = (
            "You are an expert Python engineer in a self-improving AI system.\n"
            "You will implement ONE small, well-defined function as a reusable skill.\n"
            "\n"
            "Required function signature:\n"
            "def {func_name}(step: dict, goal: dict | None = None, context: dict | None = None) -> dict:\n"
            "    \"\"\"Short docstring\"\"\"\n"
            "    ...\n"
            "\n"
            "Returned dict MUST have at least:\n"
            "{\n"
            "  \"status\": \"ok\" | \"error\",\n"
            "  \"result\": <any JSON-serializable value>,\n"
            "  \"meta\": {\"notes\": \"optional extra info\"}\n"
            "}\n"
            "\n"
            "Constraints:\n"
            "- The code MUST be valid Python 3.\n"
            "- It MUST be a single top-level function, with the exact parameters above.\n"
            "- Avoid external dependencies beyond Python stdlib.\n"
            "- Do NOT do any I/O or dangerous operations (no network, no file deletion, no shell exec).\n"
            "\n"
            "Return your answer as a single JSON object ONLY, with this structure:\n"
            "{\n"
            "  \"function_name\": \"snake_case_name\",\n"
            "  \"code\": \"<full python function, including def and docstring>\",\n"
            "  \"notes\": \"short explanation of design choices\"\n"
            "}\n"
            "Do not include any text before or after the JSON.\n"
        )

        user_payload = {
            "skill": {
                "skill_id": sk.skill_id,
                "title": sk.title,
                "description": sk.description,
                "domain": sk.domain,
                "blueprint_capability": sk.blueprint_capability,
                "status": sk.status,
                "metadata": sk.metadata,
            },
            "guidance": {
                "repo_context_hint": "The function will be placed in quentin.tools.auto_skills module.",
                "expected_usage": "It will be called by an executor with explicit parameters later.",
            },
        }
        user_prompt_text = json.dumps(user_payload, ensure_ascii=False, indent=2)
        return system_prompt, user_prompt_text

    def _extract_json_snippet(self, raw: str) -> Dict[str, Any]:
        """
        容错解析：从 LLM 输出中截取首尾大括号，解析 JSON。
        """
        first = raw.find("{")
        last = raw.rfind("}")
        if first != -1 and last != -1 and last > first:
            raw_json = raw[first : last + 1]
        else:
            raw_json = raw
        return json.loads(raw_json)

    # ---------- 文件操作 ----------

    def _ensure_auto_skills_file(self) -> None:
        """
        确保 quentin/tools/auto_skills.py 存在，且有一个简单 header。
        """
        if self.auto_skills_file.exists():
            return

        self.auto_skills_file.parent.mkdir(parents=True, exist_ok=True)
        header = textwrap.dedent(
            """
            # Auto-generated skill implementations for Project Quentin.
            # This file is managed by SkillImplementationEngine.
            # DO NOT edit functions here manually unless you know what you are doing.

            from __future__ import annotations

            # You can import shared utilities here if needed, e.g.:
            # from quentin.utils.logging import get_logger

            """
        )
        self.auto_skills_file.write_text(header, encoding="utf-8")

    def _append_function_to_file(self, func_name: str, code_str: str, sk: SkillSpec) -> None:
        """
        将生成的函数代码 append 到 auto_skills.py 后面，并加上一小段注释。
        """
        stamped_comment = f"# ---- Skill {sk.skill_id} ({sk.title}) generated at {now_iso()} ----\n"
        # 确保代码缩进合理（移除多余前导空格）
        code_body = textwrap.dedent(code_str).strip()
        with self.auto_skills_file.open("a", encoding="utf-8") as f:
            f.write("\n\n")
            f.write(stamped_comment)
            f.write(code_body)
            f.write("\n")
