from __future__ import annotations
from quentin.utils.time import now_iso, now_utc
from typing import Dict, Any, Optional
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
import logging
import subprocess
import os
import shutil

from meta_agent.self_programming.schema import (
    ProgrammingTask,
    ProgrammingResult,
    ReviewDecision,
    DevPlan,
    CodePatchSet,
    TestPlan,
    TestReport,
)
from meta_agent.self_programming.infra.git_ops import GitSafetyLayer
from meta_agent.self_programming.infra.file_patcher import FilePatcher
from meta_agent.self_programming.tools.base import CodeToolRegistry
from meta_agent.self_programming.tools.cli_wrapper import ExternalCLITool
from meta_agent.self_programming.agents.architect import ArchitectAgent
from meta_agent.self_programming.agents.programmer import ProgrammerAgent
from meta_agent.self_programming.agents.tester import TesterAgent
from meta_agent.self_programming.agents.reviewer import ReviewerAgent
from meta_agent.self_programming.metrics_store import MetricsStoreProtocol, RunRecord
from meta_agent.self_programming.evaluator import evaluate_patch_set
from meta_agent.self_programming.governance import GovernanceConfig, EnvironmentPolicy

logger = logging.getLogger(__name__)


class SelfProgrammingEngine:
    """
    一次完整的自编程循环：
    - GitSafetyLayer 建沙盒分支
    - Architect → DevPlan
    - Programmer + CodeTool → CodePatchSet
    - FilePatcher 应用改动
    - Tester 跑测试 → TestReport
    - Reviewer 决定是否接受 → ReviewDecision
    - 成功：commit 并保留分支；失败：回到 base 并删除沙盒
    """

    def __init__(
        self,
        repo_root: str = ".",
        metrics_store: Optional[MetricsStoreProtocol] = None,
        enable_governance: bool = True,
    ):
        self.repo_root = repo_root
        self.git = GitSafetyLayer(repo_root)
        self.patcher = FilePatcher()
        self.metrics_store = metrics_store

        # Load governance config
        self.governance: Optional[GovernanceConfig] = None
        if enable_governance:
            governance_path = Path(repo_root) / "governance.yaml"
            try:
                self.governance = GovernanceConfig.load(governance_path)
                logger.info("Governance enabled with config from %s", governance_path)
            except Exception as e:
                logger.warning("Failed to load governance config: %s, using defaults", e)
                self.governance = GovernanceConfig.default()

        # 工具注册（优先使用外部 CLI：gemini > codex > claude code；最后才回退 local_llm）
        self.tools = CodeToolRegistry()
        cli_candidates = (
            ("gemini_cli", os.getenv("GEMINI_CLI_CMD", "gemini")),
            ("codex_cli", os.getenv("CODEX_CLI_CMD", "codex")),
            ("claude_code_cli", os.getenv("CLAUDE_CODE_CLI_CMD", "claude")),
        )
        for tool_name, cli_cmd in cli_candidates:
            cmd = (cli_cmd or "").strip()
            if not cmd:
                continue
            binary = cmd.split()[0]
            if shutil.which(binary) is None:
                continue
            try:
                self.tools.register(ExternalCLITool(name=tool_name, cli_cmd=cmd, enabled=True))
            except Exception:
                continue

        # 兼容旧单一外部工具开关
        try:
            ext_cli = ExternalCLITool(name="external_cli", cli_cmd=os.getenv("EXTERNAL_CLI_CMD", ""))
            if ext_cli._enabled and ext_cli.cli_cmd:
                self.tools.register(ext_cli)
        except Exception:
            pass

        try:
            from meta_agent.self_programming.tools.local_llm import LocalLLMTool
            self.tools.register(LocalLLMTool())
        except Exception:
            pass

        # 团队
        self.architect = ArchitectAgent()
        self.programmer = ProgrammerAgent(repo_root=repo_root, tools=self.tools)
        self.tester = TesterAgent(repo_root=repo_root)
        self.reviewer = ReviewerAgent()

    def run_task(self, task: ProgrammingTask) -> ProgrammingResult | None:
        """
        外部调用入口：给一个 ProgrammingTask，跑一轮自编程。
        返回 ProgrammingResult（成功/失败都要落日志）。
        如果中途发生 fatal error，会返回 None。
        """
        sandbox_branch = None
        if self.git.enabled:
            sandbox_branch = self.git.create_sandbox(task.task_id)
        try:
            print(f"[{self.__class__.__name__}] Analyzing task with Architect...")
            # 1) Architect
            dev_plan = self.architect.analyze(task)

            # 2) Programmer
            print(f"[{self.__class__.__name__}] Calling programmer to implement dev plan...")
            patch_set = self.programmer.implement(task, dev_plan)
            if not patch_set.files:
                raise RuntimeError("no code modifications generated")

            # 3) Governance checks before applying patches
            if self.governance:
                # Get list of modified files
                modified_files = [mod.file_path for mod in patch_set.files]

                # Check for protected paths
                protected = [f for f in modified_files if self.governance.is_protected(f)]
                if protected:
                    logger.warning("Attempt to modify protected paths: %s", protected)
                    result = self._handle_governance_short_circuit(
                        task=task,
                        violation_type="protected_path",
                        reason=f"Protected paths: {protected}",
                        details={"paths": protected},
                    )
                    return result

                # Check budget (estimate 1000 tokens per file as rough estimate)
                estimated_tokens = len(modified_files) * 1000
                budget_ok, budget_reason = self.governance.check_budget(
                    llm_tokens=estimated_tokens,
                    file_count=len(modified_files),
                )
                if not budget_ok:
                    logger.warning("Budget check failed: %s", budget_reason)
                    result = self._handle_governance_short_circuit(
                        task=task,
                        violation_type="budget_exceeded",
                        reason=f"Budget exceeded: {budget_reason}",
                        details={"budget_reason": budget_reason, "llm_tokens_estimated": estimated_tokens},
                    )
                    return result

            # 4) FilePatcher 应用到沙盒
            patch_reports = self.patcher.apply_modifications(
                patch_set.files, repo_root=self.repo_root
            )
            print(f"[SelfProgrammingEngine] Patch reports from FilePatcher: {patch_reports}")
            # 简单规则：如果有 not_found / ambiguous 太多，可以认为失败
            if any(r.match_kind in ("not_found", "ambiguous") for r in patch_reports):
                # 这里可以进一步打进 Trace，暂时简单处理
                raise RuntimeError("too many patch application issues")

            # 5) Tester
            test_plan = self.tester.build_test_plan(task, dev_plan)
            test_report = self.tester.run_tests(test_plan)

            # 6) Reviewer
            review = self.reviewer.review(task, patch_set, test_report)

            # 7) Governance approval check
            if review.status == "approve" and self.governance:
                modified_files = [mod.file_path for mod in patch_set.files]
                test_failures = len([r for r in test_report.results if r.get("status") == "failed"])

                requires_approval, approval_reason = self.governance.requires_approval(
                    modified_files=modified_files,
                    action_type="code_patch",
                    test_failures=test_failures,
                    domain=getattr(task, "domain", "core"),
                    environment="sandbox",
                )

                if requires_approval:
                    logger.info("Task requires human approval: %s", approval_reason)
                    status = "requires_approval"
                    # Don't commit yet, wait for human approval
                elif self.git.enabled:
                    self.git.commit_work(f"AI self-programming: {task.task_id}")
                    status = "approved"
                else:
                    status = "approved"
            elif review.status == "approve":
                if self.git.enabled:
                    self.git.commit_work(f"AI self-programming: {task.task_id}")
                status = "approved"
            else:
                print(f"[SelfProgrammingEngine] Review rejected. Test raw output:\n{test_report.raw_output}")
                status = "test_fail" if test_report.overall_status != "passed" else "rejected"
                if self.git.enabled and sandbox_branch:
                    self.git.cleanup_sandbox(sandbox_branch)

            result = ProgrammingResult(
                task=task,
                dev_plan=dev_plan,
                patch_set=patch_set,
                test_plan=test_plan,
                test_report=test_report,
                review=review,
                tools_used=[t for t in self.tools.list_tools()],
            )
            quality_metrics: Optional[Dict[str, Any]] = None
            try:
                quality_metrics = evaluate_patch_set(
                    patch_set,
                    repo_root=self.repo_root,
                    test_report=test_report,
                )
            except Exception:
                quality_metrics = None

            self._record_run(
                task,
                status=status,
                test_output=test_report.raw_output,
                result=result,
                quality_metrics=quality_metrics,
            )

            if status != "approved":
                return result

            # 审批成功，保留分支（你可以改成 merge 回 main，再删分支）
            return result

        except Exception as e:
            # fatal error：直接回退到 base 分支并删除沙盒
            print(f"[SelfProgrammingEngine] Fatal error: {e}")
            try:
                if self.git.enabled and sandbox_branch:
                    self.git.cleanup_sandbox(sandbox_branch)
            except Exception:
                pass
            self._record_run(task, status="error", test_output=str(e), result=None)
            raise e

    def _handle_governance_short_circuit(self, task: ProgrammingTask, violation_type: str, reason: str, details: Dict[str, Any]) -> ProgrammingResult:
        """
        Handles governance violations by either raising an error or returning a short-circuited
        ProgrammingResult with a 'request_changes' review decision, based on environment config.
        """
        if not self.governance:
            # If governance is not enabled, all governance short-circuit calls should hard-fail.
            raise RuntimeError(f"Governance not enabled, but short-circuit called for {violation_type}: {reason}")

        env_config = self.governance.environments.get(task.environment, EnvironmentPolicy())
        if not env_config.allow_auto_apply:
            raise RuntimeError(reason) # Hard block

        # If auto-apply is allowed, return a ProgrammingResult with request_changes
        review_decision = ReviewDecision(
            task_id=task.task_id,
            status="request_changes",
            severity="high", # All governance violations are high severity
            issues=[{"type": violation_type, "description": reason, "details": details}],
            summary=f"Governance check triggered '{violation_type}': {reason}",
            follow_up_actions=["Human review required to bypass governance rule."],
        )

        # Create dummy ProgrammingResult components
        dev_plan = DevPlan(task_id=task.task_id, task_summary="Governance short-circuit", impact_analysis={}, work_items=[], test_plan={})
        patch_set = CodePatchSet(task_id=task.task_id, files=[], summary="Governance short-circuit")
        test_plan = TestPlan(task_id=task.task_id, framework="none", tests=[])
        test_report = TestReport(task_id=task.task_id, overall_status="skipped", results=[], raw_output="Governance short-circuit triggered review.")

        return ProgrammingResult(
            task=task,
            dev_plan=dev_plan,
            patch_set=patch_set,
            test_plan=test_plan,
            test_report=test_report,
            review=review_decision,
            tools_used=[], # No tools were really used for this short-circuit
        )

    # -------------------- Metrics helpers -------------------- #
    def _record_run(
        self,
        task: ProgrammingTask,
        *,
        status: str,
        test_output: Optional[str],
        result: Optional[ProgrammingResult],
        quality_metrics: Optional[Dict[str, Any]] = None,
    ) -> None:
        if not self.metrics_store:
            return

        commit_info = self._get_commit_info()
        metrics = self._build_metrics(result, quality_metrics=quality_metrics)
        record: RunRecord = {
            "task_id": task.task_id,
            "status": status,  # type: ignore[assignment]
            "timestamp": now_utc(),
            "commit_hash": commit_info.get("commit_hash"),
            "branch_name": commit_info.get("branch_name"),
            "raw_test_output": (test_output or "")[:4000],
            "metrics": metrics,
            "task_payload": asdict(task),
        }
        try:
            self.metrics_store.log_run(record)
        except Exception:
            # Best-effort logging only; do not break the engine.
            pass

    def _get_commit_info(self) -> Dict[str, Optional[str]]:
        commit_hash: Optional[str] = None
        branch_name: Optional[str] = None
        try:
            out = subprocess.check_output(
                ["git", "rev-parse", "HEAD"],
                cwd=self.repo_root,
            )
            commit_hash = out.decode().strip()
        except Exception:
            commit_hash = None
        try:
            out = subprocess.check_output(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                cwd=self.repo_root,
            )
            branch_name = out.decode().strip()
        except Exception:
            branch_name = None
        return {"commit_hash": commit_hash, "branch_name": branch_name}

    def _build_metrics(
        self,
        result: Optional[ProgrammingResult],
        *,
        quality_metrics: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        if result is None:
            return {}
        tests_total = len(result.test_report.results) if result.test_report else 0
        metrics: Dict[str, Any] = {
            "tests_overall_status": getattr(result.test_report, "overall_status", None),
            "tests_total": tests_total,
            "review_status": getattr(result.review, "status", None),
            "tools_used": result.tools_used,
        }
        if quality_metrics:
            metrics["quality"] = quality_metrics
        return metrics
