from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional
import logging
import uuid
import textwrap

from quentin.self_programming.schema import (
    PatchCandidate,
    PatchTestPlan,
    PatchTestResult,
    PatchReport,
    PatchTarget,
    PatchExecutionResult,
)
from quentin.orchestrator.core import LanguageModel
from quentin.utils.time import now_iso

logger = logging.getLogger(__name__)


@dataclass
class SkillCandidate:
    """
    从成功 Trace 中抽取出来的“技能候选”。

    v1 先只是结构占位，后面可以真的把长流程提炼成独立函数/模块。
    """
    skill_id: str
    name: str
    description: str
    source_trace_ids: List[str]
    code_suggestion: Optional[str] = None
    meta: Dict[str, Any] = None

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        return d


@dataclass
class SkillEvolutionStats:
    patterns_mined: int
    candidates_generated: int
    experiments_created: int
    candidates_accepted: int
    candidates_rejected: int


class SkillEvolutionLoop:
    """
    技能与代码进化循环（Skill & Code Evolution Loop）v1 实现。

    职责：
    - 从成功 Trace 中挖潜在技能（目前只是占位）
    - 从 issues 列表（包括 ImmuneCase / BlueprintGap 等）生成 PatchCandidate
    - 调用 SelfProgrammingEngine 跑测试，返回 PatchReport
    """

    def __init__(
        self,
        engine: Any,
        *,
        llm: Optional[LanguageModel] = None,
        repo_root: str | Path = ".",
    ) -> None:
        self.engine = engine
        self.llm = llm
        self.repo_root = Path(repo_root).resolve()

    # --------------------------------------------------------------
    # 对 SleepLoop / Runtime 暴露的总入口
    # --------------------------------------------------------------
    def run_once(
        self,
        *,
        successful_traces: List[Dict[str, Any]],
        issues: List[Dict[str, Any]],
        test_suites: Optional[List[str]] = None,
        extra_context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        一次完整的进化轮次。

        输入：
        - successful_traces: SleepLoop 准备好的“成功 Trace 摘要”
        - issues: ImmuneLoop / Blueprint 等准备好的 issue 列表
        - test_suites: 要跑哪些测试（unit/static/…）
        - extra_context: 额外上下文（比如来源：sleep_cycle / research_cycle）

        输出：
        - skill_candidates
        - patch_candidates
        - patch_reports
        - promotable_patches（由 SelfProgrammingEngine.select_patches_to_promote 决定）
        """
        ctx = extra_context or {}

        # 1) 从成功 trace 中挖技能候选（v1 只是结构占位）
        skill_candidates = self.generate_skills_from_traces(successful_traces)

        # 2) 从 issues 生成 PatchCandidate
        patch_candidates = self.generate_patches_from_issues(issues)

        # 3) 跑测试
        suites = test_suites or ["unit", "static_analysis"]
        patch_reports = self.evaluate_patches(
            patch_candidates,
            test_suites=suites,
            extra_context=ctx,
        )

        # 4) 选可推广 patch
        promotable: List[PatchReport] = []
        selector = getattr(self.engine, "select_patches_to_promote", None)
        if callable(selector):
            try:
                promotable = selector(patch_reports, max_promote=1)
            except Exception:
                logger.exception("SkillEvolutionLoop: select_patches_to_promote failed, using fallback")
        if not promotable:
            promotable = patch_reports[:1]

        return {
            "skill_candidates": [s.to_dict() for s in skill_candidates],
            "patch_candidates": [p.to_dict() for p in patch_candidates],
            "patch_reports": [r.to_dict() for r in patch_reports],
            "promotable_patches": [r.to_dict() for r in promotable],
        }

    # --------------------------------------------------------------
    # 1. 从成功 Trace 中挖技能（目前只是 stub）
    # --------------------------------------------------------------
    def generate_skills_from_traces(
        self,
        successful_traces: List[Dict[str, Any]],
    ) -> List[SkillCandidate]:
        """
        v1：只做占位，后面再用 LLM 对 Trace 做 pattern mining。

        现在先简单：每个成功 trace 生成一个很粗糙的 SkillCandidate。
        """
        candidates: List[SkillCandidate] = []
        for t in successful_traces:
            trace_id = t.get("trace_id")
            task_id = t.get("task_id", "unknown_task")
            domain = t.get("domain", "general")

            skill = SkillCandidate(
                skill_id=f"skill_from_trace::{trace_id}",
                name=f"auto_skill_for_{task_id}",
                description=f"Auto-extracted skill placeholder from trace {trace_id} in domain {domain}.",
                source_trace_ids=[trace_id],
                code_suggestion=None,
                meta={"status": "placeholder"},
            )
            candidates.append(skill)

        return candidates

    # --------------------------------------------------------------
    # 2. 从 issues 生成 PatchCandidate —— 重点：接入 LLM
    # --------------------------------------------------------------
    def generate_patches_from_issues(
        self,
        issues: List[Dict[str, Any]],
    ) -> List[PatchCandidate]:
        """
        核心：从 issue 列表生成 PatchCandidate。

        逻辑（v1）：
        - 对每个 issue：
            - 找到 target.file_path
            - 读当前文件内容（不存在则视为新文件）
            - 如果有 llm：
                - 用 llm 生成该文件的完整新版本（不是 diff，而是“重写后的完整文件内容”）
            - 否则：
                - 生成一个 placeholder patch_text（不依赖 diff 应用）
        """
        candidates: List[PatchCandidate] = []
        for issue in issues:
            try:
                cand = self._build_patch_candidate_for_issue(issue)
                if cand is not None:
                    candidates.append(cand)
            except Exception:
                logger.exception("SkillEvolutionLoop: failed to build patch for issue=%r", issue)

        logger.info("SkillEvolutionLoop.generate_patches_from_issues: %d candidates", len(candidates))
        return candidates

    def _build_patch_candidate_for_issue(
        self,
        issue: Dict[str, Any],
    ) -> Optional[PatchCandidate]:
        target = issue.get("target") or {}
        file_path = target.get("file_path")
        if not file_path:
            logger.warning("SkillEvolutionLoop: issue has no file_path: %r", issue)
            return None

        abs_path = self.repo_root / file_path
        try:
            current_code = abs_path.read_text(encoding="utf-8") if abs_path.exists() else ""
        except Exception:
            logger.exception("SkillEvolutionLoop: failed to read %s", abs_path)
            current_code = ""

        reason = issue.get("reason", "")
        issue_id = issue.get("issue_id", f"issue::{uuid.uuid4().hex}")
        severity = (issue.get("metrics") or {}).get("severity", "medium")

        if self.llm is None:
            # 没有 LLM 时，生成一个占位 PatchCandidate，方便后续人工或别的脚本补齐
            patch_text = self._build_stub_patch_text(file_path, current_code, reason)
        else:
            patch_text = self._build_patch_with_llm(
                file_path=file_path,
                current_code=current_code,
                issue=issue,
            )

        patch_id = f"patch::{issue_id}::{uuid.uuid4().hex}"

        target_obj = PatchTarget(
            kind=target.get("target_type", "module"),
            path=file_path,
            symbol=target.get("symbol_name"),
            constraints=target.get("meta", {}),
        )

        candidate = PatchCandidate(
            proposal_id=patch_id,
            created_at=now_iso(),
            created_by="skill_evolution_loop",
            target=target_obj,
            rationale=f"Auto-generated patch for issue: {reason}",
            patch_type="full_file",
            patch_content=patch_text,
            test_plan=PatchTestPlan(),
            meta={"source_issue": issue_id, "severity": severity},
        )
        return candidate

    def _build_stub_patch_text(self, file_path: str, current_code: str, reason: str) -> str:
        """
        Without an LLM, produce a safe placeholder patch (full-file content) without
        relying on diff application or tool-calling.
        """
        banner = textwrap.dedent(
            f"""
            # NOTE: This file is auto-generated as a placeholder by SkillEvolutionLoop.
            # Reason: {reason}
            # File: {file_path}
            #
            # Placeholder: implement according to the Meta-Agent v3 blueprint.
            """
        ).strip("\n")

        if not current_code.strip():
            return banner + "\n\n" + "def _placeholder() -> str:\n    return \"placeholder\"\n"
        else:
            return banner + "\n\n" + current_code

    def _build_patch_with_llm(
        self,
        *,
        file_path: str,
        current_code: str,
        issue: Dict[str, Any],
    ) -> str:
        """
        用 LLM 生成新的文件内容。

        设计选择：
        - 不生成 diff，而是生成“该文件的完整新版本”。
        - SelfProgrammingEngine 在应用 patch 时，可以把 patch_text 直接写回文件
          （或者写到临时目录跑测试）。
        """
        reason = issue.get("reason", "")
        issue_id = issue.get("issue_id", "unknown_issue")

        system_prompt = (
            "You are a senior Python engineer working inside a self-evolving AI agent repository.\n"
            "Your job is to modify ONE file to address a specific issue from a blueprint or immune case.\n"
            "You must output ONLY the full new content of that file, as valid Python code.\n"
            "Do NOT include explanations, comments about what you changed, or diff markers.\n"
            "Just return the final code for the file."
        )

        user_prompt = textwrap.dedent(
            f"""
            Repository context:
              - This repo implements a Meta-Agent v3 blueprint (research-integrated, self-programming system).
              - You are editing the file: {file_path}

            Issue to fix (from blueprint/immune system):
            - Issue ID: {issue_id}
            - Reason: {reason}
            - Target meta: {issue.get("target")}

            Current file content (if empty, the file does not exist yet):
            ---------------- CURRENT FILE START ----------------
            {current_code}
            ---------------- CURRENT FILE END ----------------

            Requirements:
            1. Keep the overall architecture consistent with a research-friendly, modular design.
            2. Use clear, production-quality Python.
            3. If the file is missing, create a minimal but functional skeleton that satisfies the issue.
            4. Do NOT rely on external frameworks beyond standard Python and the existing quentin.* modules.
            5. Output ONLY the full new file content.
            """
        ).strip("\n")

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        try:
            code = self.llm.generate(messages, temperature=0.2)
        except Exception:
            logger.exception("SkillEvolutionLoop: LLM patch generation failed for %s", file_path)
            return self._build_stub_patch_text(file_path, current_code, reason)

        return code

    # --------------------------------------------------------------
    # 3. 调用 SelfProgrammingEngine 跑测试
    # --------------------------------------------------------------
    def evaluate_patches(
        self,
        patch_candidates: List[PatchCandidate],
        *,
        test_suites: List[str],
        extra_context: Optional[Dict[str, Any]] = None,
    ) -> List[PatchReport]:
        """
        对每个 PatchCandidate 运行测试，返回 PatchReport 列表。

        self.engine.run_tests_for_patch 目前可能还是 stub，
        但整体调用链已经打通。
        """
        ctx = extra_context or {}
        reports: List[PatchReport] = []

        for cand in patch_candidates:
            report = self._run_tests_for_candidate(
                cand,
                test_suites=test_suites,
                extra_context=ctx,
            )
            if report:
                reports.append(report)

        return reports

    def _run_tests_for_candidate(
        self,
        candidate: PatchCandidate,
        *,
        test_suites: List[str],
        extra_context: Dict[str, Any],
    ) -> Optional[PatchReport]:
        runner = getattr(self.engine, "run_tests_for_patch", None)
        if callable(runner):
            try:
                return runner(
                    patch=candidate,
                    test_suites=test_suites,
                    extra_context=extra_context,
                )
            except TypeError:
                try:
                    return runner(candidate)
                except Exception:
                    logger.exception("SkillEvolutionLoop: run_tests_for_patch fallback failed")
            except Exception:
                logger.exception("SkillEvolutionLoop: run_tests_for_patch failed")

        # Fallback stub report to keep the loop functional
        exec_result = PatchExecutionResult(
            proposal_id=candidate.proposal_id,
            tests_run=test_suites,
            tests_passed=[],
            tests_failed=[],
            static_issues=[],
            metrics_delta={},
        )
        return PatchReport(
            proposal=candidate,
            execution_result=exec_result,
            recommended_action="needs_review",
            reasoning="run_tests_for_patch unavailable; generated stub report.",
        )
