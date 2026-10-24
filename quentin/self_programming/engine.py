# quentin/self_programming/engine.py
from __future__ import annotations
import re
import uuid
import logging
from typing import Optional, List
from pathlib import Path

from meta_agent.tools.coder.router import coder_router
from meta_agent.tools.coder.base import CodeGenerationRequest
from meta_agent.tools.research.research_tool import ResearchTool
from meta_agent.patches.models import PatchProposal
from meta_agent.patches.safe_applier import SafePatchApplier
from quentin.traces.core import JsonlTraceRecorder
from quentin.self_programming.patches import (
    CodePatch,
    PatchStatus,
    PatchType,
    PatchTestReport,
    PatchTestCaseResult,
)
from quentin.self_programming.testing import ShellCommandPatchTestRunner
from quentin.self_programming.infra.git_ops import GitSafetyLayer

logger = logging.getLogger(__name__)

# Placeholder for the Gap object until it's formally integrated
class BlueprintGap:
    def __init__(self, id: str, title: str, description: str, related_files: List[str]):
        self.id = id
        self.title = title
        self.description = description
        self.related_files = related_files


class SelfProgrammingEngine:
    def __init__(self, *args, **kwargs):
        try:
            self.research_tool = ResearchTool()
        except RuntimeError as e:
            logger.warning(f"SelfProgrammingEngine: ResearchTool initialization failed: {e}. Some features may be degraded.")
            self.research_tool = None
        self.repo_root = Path(kwargs.get("repo_root", ".")).resolve()
        self.trace = JsonlTraceRecorder(repo_root=str(self.repo_root))
        self.git = GitSafetyLayer(repo_path=str(self.repo_root))
        
        # Placeholder stores for compatibility
        from quentin.self_programming.patches import FileBackedPatchStore

        self.patch_store = kwargs.get("patch_store") or FileBackedPatchStore()
        self.skill_store = kwargs.get("skill_store")
        self.test_runner = kwargs.get("test_runner") or ShellCommandPatchTestRunner(repo_root=".")

    async def run_cycle_for_gap(self, gap: BlueprintGap, backend: str = "codex_cli") -> Optional[PatchProposal]:
        """
        Full self-healing cycle for a gap:
        1. Researches the concept behind the gap.
        2. Create Git sandbox branch.
        3. Uses an external CoderTool to generate a patch based on research.
        4. Apply patch to sandbox.
        5. Run automated tests (pytest).
        6. Merge to base branch if successful, otherwise rollback.
        """
        self.trace.record_event(
            event_type="self_prog_gap_start",
            payload={"gap_id": gap.id, "backend": backend},
        )

        # 1. Research
        research_summary = "ResearchTool is disabled; continuing with existing context."
        if self.research_tool:
            query = f"{gap.title} {gap.description} in meta-agent / self-improving agents / code evolution best practices"
            research_summary = await self.research_tool.search_and_summarize(query=query, max_pages=3)

        # 2. Git Sandbox
        sandbox_branch = None
        if self.git.enabled:
            try:
                sandbox_branch = self.git.create_sandbox(gap.id)
                logger.info(f"SelfProgrammingEngine: Created sandbox branch {sandbox_branch}")
            except Exception as e:
                logger.error(f"SelfProgrammingEngine: Failed to create git sandbox: {e}")
                # Continue without git if failed, but we prefer safety
        
        try:
            # 3. Code Generation
            req = CodeGenerationRequest(
                goal=f"Fix blueprint gap: {gap.id} - {gap.title}",
                context_files=gap.related_files,
                instructions=f"""
The blueprint gap description is:
{gap.description}

Relevant files in the current codebase:
{gap.related_files}

An external research summary on this topic is:
{research_summary}

Please generate the improved code implementation based on this information.
Requirements:
- Adhere to the existing architecture and interfaces.
- Include tests or usage examples where possible.
- The code must be clean and readable.
""",
                preferred_language="python",
            )

            result = coder_router.generate(req, backend_name=backend)

            # P3-Audit: Security Audit Logging for self-programming
            try:
                from quentin.security.audit_schema import AuditEvent as SecurityAuditEvent
                from quentin.kernel.audit import default_audit_logger
                
                sec_event = SecurityAuditEvent(
                    event_id=f"selfprog-{uuid.uuid4().hex}",
                    actor="self_programming_engine",
                    action="run_cycle_for_gap",
                    resource=gap.id,
                    decision="allow" if result.success else "block",
                    reason=str(result.reasoning or ""),
                    session_id="brain",
                    metadata={"gap_title": gap.title, "backend": backend}
                )
                default_audit_logger().append(sec_event)
            except Exception:
                pass

            if not result.success:
                if sandbox_branch:
                    self.git.cleanup_sandbox(sandbox_branch)
                return None

            # 4. Convert to Patch and Apply
            # In this simple implementation, we assume the coder returns full file content 
            # or a diff that we can apply. For v1, we write to the target file.
            proposal = self._build_patch_from_code(gap, result.code)

            # Apply the patch via the non-bypass safety path.
            applier = SafePatchApplier(repo_root=self.repo_root)
            safety_result = applier.apply_patch(proposal)
            if not safety_result.allow_apply:
                logger.warning(f"SelfProgrammingEngine: Patch blocked by safety: {safety_result.reasons}")
                if sandbox_branch:
                    self.git.cleanup_sandbox(sandbox_branch)
                return None

            # 5. Run Tests
            # We create a temporary Patch object for the test runner
            target_file = proposal.target_files[0]
            new_content = proposal.metadata.get("new_content", "")
            code_patch = CodePatch(
                patch_id=proposal.id,
                target_file=target_file,
                content=new_content,
                status=PatchStatus.PROPOSED
            )
            self.patch_store.upsert(code_patch)
            
            report = self.run_tests_for_patch(code_patch.patch_id)
            
            # 6. Finalize
            if report.success:
                logger.info(f"SelfProgrammingEngine: Tests passed for gap {gap.id}. Merging...")
                if sandbox_branch:
                    self.git.finalize_success(
                        sandbox_branch, 
                        commit_message=f"Self-healing: Fixed gap {gap.id} - {gap.title}",
                        merge=True
                    )
                return proposal
            else:
                logger.warning(f"SelfProgrammingEngine: Tests failed for gap {gap.id}. Rolling back.")
                try:
                    applier.rollback(proposal)
                except Exception:
                    pass
                if sandbox_branch:
                    self.git.cleanup_sandbox(sandbox_branch)
                return None

        except Exception as e:
            logger.error(f"SelfProgrammingEngine: Unexpected error in cycle: {e}")
            if sandbox_branch:
                try:
                    self.git.cleanup_sandbox(sandbox_branch)
                except Exception:
                    pass
            return None

    def _build_patch_from_code(self, gap: BlueprintGap, code: str) -> PatchProposal:
        """
        Convert generated code into a PatchProposal.
        """
        # Improved policy: if related_files is provided, try to find the best match
        target_file = None
        if gap.related_files:
            target_file = gap.related_files[0]
        
        if not target_file:
            safe_id = re.sub(r"[^a-zA-Z0-9._-]+", "_", str(gap.id)).strip("_") or uuid.uuid4().hex[:8]
            target_file = f"mutable/generated/{safe_id}.py"

        content = str(code or "")
        if content and not content.endswith("\n"):
            content += "\n"
        lines = content.splitlines(keepends=True)
        num_lines = max(1, len(lines))
        diff = "--- /dev/null\n" + f"+++ b/{target_file}\n" + f"@@ -0,0 +1,{num_lines} @@\n"
        diff += "".join(f"+{l}" for l in lines) if lines else "+\n"

        return PatchProposal(
            id=f"patch-{uuid.uuid4().hex}",
            target_files=[target_file],
            diff=diff,
            intent=f"Implement gap {gap.id}: {gap.title}",
            metadata={
                "gap_id": gap.id,
                "gap_title": gap.title,
                "related_files": list(gap.related_files or []),
                "new_content": content,
                "origin": "self-programming-v2-sandboxed",
            },
        )

    # -------- Minimal patch test pipeline -------- #
    def run_tests_for_patch(self, patch_id: str, command: str = "pytest -q") -> PatchTestReport:
        """
        Load CodePatch by id, run shell tests, and update store eval_summary/status.
        """
        patch = self.patch_store.get(patch_id)
        if patch is None:
            raise ValueError(f"Patch not found: {patch_id}")

        runner = ShellCommandPatchTestRunner(command=command, repo_root=str(self.repo_root))
        report = runner.run_for_patch(patch)

        patch.eval_summary = {
            "tests": [c.to_dict() for c in report.cases],
            "success": report.success,
            "runtime_sec": report.runtime_sec,
        }
        patch.status = PatchStatus.EVALUATED if report.success else PatchStatus.PROPOSED
        self.patch_store.upsert(patch)

        self.trace.record_event(
            event_type="self_prog_patch_test",
            payload={
                "patch_id": patch.patch_id,
                "success": report.success,
                "command": command,
                "cases": [c.to_dict() for c in report.cases],
            },
        )
        return report
