# meta_agent/self_programming/engine_v2.py
from __future__ import annotations
from quentin.utils.time import now_iso, now_utc
from dataclasses import dataclass, field, asdict
from typing import Any, List, Optional, Iterable
import asyncio
import uuid
import json
import logging
import re
import tempfile
import subprocess
import shutil
from pathlib import Path
import sys
import os
import glob
from contextlib import contextmanager

# Ensure the project root is in sys.path for package imports
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from pydantic import BaseModel, ValidationError

from meta_agent.tools.coder.router import coder_router
from meta_agent.tools.coder.base import CodeGenerationRequest, CodeGenerationResult
from meta_agent.research.tool import ResearchTool # Using the new advanced tool
from quentin.traces.core import JsonlTraceRecorder, new_trace_event, TraceEventType
from meta_agent.config.feature_flags import (
    PROMPT_MIGRATION_M3_SYSTEM_EVENTS,
    PROMPT_MIGRATION_SYSTEM_EVENT_ENQUEUED,
    feature_flags,
)
from meta_agent.patches.models import PatchProposal
from meta_agent.patches.store import PatchStore
from quentin.self_programming.skill_evaluator import PatchEvaluator, SkillPatchEvaluator
from meta_agent.patches.safe_applier import SafePatchApplier
from meta_agent.monitoring.status_snapshot import build_status_snapshot
from quentin.infra.storage.vector_store import ChromaVectorStore, NullVectorStore
from meta_agent.self_programming.test_runner import SandboxTestRunner
from meta_agent.skills.router import SkillRouter # Added import
from meta_agent.skills.registry import SkillRegistry # Added import
from meta_agent.self_programming.infra.git_ops import GitSafetyLayer
from meta_agent.self_programming.test_runner import SandboxTestRunner
from meta_agent.self_programming.infra.context_extractor import build_context_chunks
from quentin.runtime.system_events import SystemEventQueue
from meta_agent.self_programming.backends.base import SelfProgBackendBundle
from quentin.infra.bus import get_system_bus, SystemEvent
from quentin.self_programming.safety_wrapper import SelfProgrammingSafetyWrapper

@dataclass
class GapLike:
    id: str; title: str; description: str; category: str; priority: int
    related_files: List[str] = field(default_factory=list)
    domain: Optional[str] = None
    target_file: Optional[str] = None

logger = logging.getLogger(__name__)

from meta_agent.runtime import council

@dataclass
class CouncilDecision:
    should_apply: bool
    risk_level: str = "low"
    reason: str = ""

    @classmethod
    def from_dict(cls, d: dict) -> 'CouncilDecision':
        return cls(
            should_apply=d.get("should_apply", False),
            risk_level=d.get("risk_level", "high"),
            reason=d.get("reason", "No reason provided."),
        )

    def to_dict(self) -> dict:
        return {
            "should_apply": self.should_apply,
            "risk_level": self.risk_level,
            "reason": self.reason,
        }

class PatchGovernanceCouncil:
    """
    Uses a multi-LLM council to decide whether a patch should be applied.
    """
    def __init__(self, trace_recorder: Optional[JsonlTraceRecorder] = None):
        self.trace_recorder = trace_recorder or JsonlTraceRecorder(repo_root=".")

    async def decide_on_patch(self, p: PatchProposal, report, gap: GapLike, snapshot) -> CouncilDecision:
        """
        Asks the council to review the patch and make a decision.
        """
        self.trace_recorder.record_event(new_trace_event(
            trace_id=f"patch-governance-{p.id}",
            event_type=TraceEventType.SELF_PROGRAMMING,
            payload={"action": "patch_governance_start", "patch_id": p.id, "gap_id": gap.id}
        ))

        context = {
            "gap_title": gap.title,
            "gap_description": gap.description,
            "patch_intent": p.intent,
            "patch_diff": p.get_unified_diff(),
            "evaluation_report": asdict(report),
            "system_status_snapshot": snapshot.to_dict(),
        }

        question = (
            "You are a senior software architect on a self-evolving AI project. "
            "Review the proposed code patch based on the provided context. "
            "Consider the following criteria:\n"
            "1. CORRECTNESS: Does it pass all verification tests?\n"
            "2. REGRESSION RISK: Does it break existing patterns or introduce hidden complexity?\n"
            "3. EVOLUTIONARY ROI: Does this patch provide a reusable skill or fix a recurring gap?\n"
            "4. QUALITY: Is the implementation idiomatic and well-documented?\n\n"
            "Determine if this patch should be applied to the codebase."
        )

        json_schema_hint = """
        {
            "should_apply": boolean, // True if the patch is safe and effective, otherwise False.
            "risk_level": "'low' | 'medium' | 'high'", // Estimated risk of applying this patch.
            "reason": "string" // A brief justification for your decision.
        }
        """

        try:
            result_dict = await council.ask_json(
                role="patch_governance",
                question=question,
                context=context,
                json_schema_hint=json_schema_hint,
            )
            decision = CouncilDecision.from_dict(result_dict)
        except Exception as e:
            self.trace_recorder.record_event(new_trace_event(
                trace_id=f"patch-governance-{p.id}",
                event_type=TraceEventType.ERROR,
                payload={"action": "patch_governance_error", "error": str(e), "patch_id": p.id}
            ))
            # Fail-safe: default to not applying the patch on error.
            decision = CouncilDecision(should_apply=False, risk_level="high", reason=f"Governance council failed with an exception: {e}")

        self.trace_recorder.record_event(new_trace_event(
            trace_id=f"patch-governance-{p.id}",
            event_type=TraceEventType.SELF_PROGRAMMING,
            payload={"action": "patch_governance_decision", "patch_id": p.id, **decision.to_dict()}
        ))
        return decision

@dataclass
class SelfProgrammingConfig:
    default_coder_backend: str = field(default_factory=lambda: os.getenv("CODER_BACKEND", "llm_client"))
    enable_research: bool = field(default_factory=lambda: os.getenv("ENABLE_RESEARCH", "false").lower() == "true")
    max_gaps_per_cycle: int = 3
    max_code_chars: int = 40_000
    allow_auto_apply: bool = True
    proposal_only: bool = field(
        default_factory=lambda: os.getenv("SELFPROG_PROPOSAL_ONLY", "false").strip().lower() in ("1", "true", "yes", "on")
    )
    max_retries: int = 3 # Add retry limit config
    # Deterministic/offline runs: allow a lightweight cycle for evidence/tests.
    fast_deterministic: bool = field(
        default_factory=lambda: os.getenv("SELFPROG_FAST_DETERMINISTIC", "false").strip().lower() in ("1", "true", "yes", "on")
    )
    # Release protocol (shadow/canary) integration (blueprint v3)
    enable_release_protocol: bool = field(
        default_factory=lambda: os.getenv("QUENTIN_PATCH_RELEASE_PROTOCOL", "false").strip().lower() in ("1", "true", "yes", "on")
    )
    enable_canary: bool = field(
        default_factory=lambda: os.getenv("QUENTIN_PATCH_CANARY", "false").strip().lower() in ("1", "true", "yes", "on")
    )
    canary_fraction: float = field(default_factory=lambda: float(os.getenv("QUENTIN_PATCH_CANARY_FRACTION", "0.1") or 0.1))
    release_environment: str = field(default_factory=lambda: os.getenv("QUENTIN_RELEASE_ENV", "sandbox") or "sandbox")
    isolated_workdir: bool = field(
        default_factory=lambda: os.getenv("QUENTIN_SELFPROG_ISOLATED_WORKDIR", "false").strip().lower()
        in ("1", "true", "yes", "on")
    )

class GenerationPayload(BaseModel):
    implementation_code: str
    verification_test_code: str

class SelfProgrammingEngineV2:
    def __init__(
        self,
        config: Optional[SelfProgrammingConfig] = None,
        evaluator: Optional[PatchEvaluator] = None,
        applier: Optional[SafePatchApplier] = None,
        council: Optional[PatchGovernanceCouncil] = None,
        skill_router: Optional[SkillRouter] = None,
        research_tool: Optional[ResearchTool] = None,
        test_runner: Optional[SandboxTestRunner] = None,
        patch_store: Optional[PatchStore] = None,
        trace_recorder: Optional[JsonlTraceRecorder] = None, # New argument
        system_event_queue: Optional[SystemEventQueue] = None,
        backend_bundle: Optional[SelfProgBackendBundle] = None,
        safety_wrapper: Optional[SelfProgrammingSafetyWrapper] = None,
        tool_manager: Optional[Any] = None,
    ):
        self.config = config or SelfProgrammingConfig()
        self.repo_root = Path(".").resolve()
        self._evaluator = evaluator or SkillPatchEvaluator()
        self._applier = applier or SafePatchApplier()
        self._council = council or PatchGovernanceCouncil()
        self.research_tool = research_tool or ResearchTool()
        self.skill_router = skill_router or SkillRouter(SkillRegistry())
        self.trace_recorder = trace_recorder or JsonlTraceRecorder(repo_root=str(self.repo_root))
        self.system_event_queue = system_event_queue or SystemEventQueue(repo_root=str(self.repo_root))
        
        if backend_bundle:
            self.test_runner = backend_bundle.test_runner
            self._applier = backend_bundle.patch_applier
            self.patch_store = backend_bundle.patch_store
            self.git = backend_bundle.repo_adapter
        else:
            self.test_runner = test_runner or SandboxTestRunner()
            self._applier = applier or SafePatchApplier() # Re-assign if not bundle, effectively no-op if logic above is correct but clearer to separate paths
            # Actually, to avoid re-assigning _applier which was set above, let's restructure slightly.
            # But to keep diff minimal, we can overwrite.
            self.patch_store = patch_store or PatchStore(path=str(self.repo_root / "data" / "patches.json"))
            self.git = None if self.config.isolated_workdir else GitSafetyLayer(repo_path=str(self.repo_root))
        self._safety_wrapper = safety_wrapper
        if self._safety_wrapper is None and tool_manager is not None:
            try:
                self._safety_wrapper = SelfProgrammingSafetyWrapper(tool_manager)
            except Exception:
                self._safety_wrapper = None

        try:
            self.vector_store = ChromaVectorStore(db_path="chroma_db_code_chunks")
        except Exception as e:
            # Fallback when chromadb is not installed or misconfigured
            self.vector_store = NullVectorStore()
            self.trace_recorder.record_event(new_trace_event(
                trace_id="self-prog-init",
                event_type=TraceEventType.ERROR,
                payload={"action": "vector_store_fallback", "error": str(e)}
            ))

    def run_for_gaps(self, gaps: Iterable[GapLike], backend: Optional[str] = None):
        if not gaps: return
        # asyncio.run is not re-entrant, handle with care if called from another async context
        asyncio.run(self._run_for_gaps_async(list(gaps)[:self.config.max_gaps_per_cycle], backend=backend))

    async def _run_for_gaps_async(self, gaps: List[GapLike], backend: Optional[str] = None):
        backend = backend or self.config.default_coder_backend
        with self._isolated_workspace():
            self.trace_recorder.record_event(new_trace_event(
                trace_id="self-prog-cycle",
                event_type=TraceEventType.SELF_PROGRAMMING,
                payload={"action": "cycle_start", "num_gaps": len(gaps)}
            ))
            if backend == "deterministic" and bool(getattr(self.config, "fast_deterministic", False)):
                self.trace_recorder.record_event(
                    new_trace_event(
                        trace_id="self-prog-cycle",
                        event_type=TraceEventType.SELF_PROGRAMMING,
                        payload={"action": "cycle_done", "num_gaps": len(gaps), "skipped": "fast_deterministic"},
                    )
                )
                return
            snapshot = build_status_snapshot(window_hours=24)
            tasks = [self._run_for_single_gap(gap, backend, snapshot) for gap in gaps]
            await asyncio.gather(*tasks)
            self.trace_recorder.record_event(new_trace_event(
                trace_id="self-prog-cycle",
                event_type=TraceEventType.SELF_PROGRAMMING,
                payload={"action": "cycle_done", "num_gaps": len(gaps)}
            ))

    def _copy_repo_to(self, dest_root: Path) -> None:
        ignore = shutil.ignore_patterns(
            ".git",
            "__pycache__",
            ".pytest_cache",
            "venv",
            ".venv",
            "node_modules",
            "logs",
            "chroma_db_code_chunks",
        )
        shutil.copytree(self.repo_root, dest_root, dirs_exist_ok=True, ignore=ignore)

    @contextmanager
    def _isolated_workspace(self):
        if not self.config.isolated_workdir:
            yield Path.cwd()
            return
        tmp = tempfile.TemporaryDirectory()
        work_root = Path(tmp.name)
        self._copy_repo_to(work_root)
        old_cwd = Path.cwd()
        old_git = self.git
        try:
            os.chdir(work_root)
            self.git = GitSafetyLayer(repo_path=str(work_root))
            yield work_root
        finally:
            self.git = old_git
            os.chdir(old_cwd)
            tmp.cleanup()

    async def _run_for_single_gap(self, gap: GapLike, backend: str, snapshot):
        sandbox_branch: Optional[str] = None
        if self.git and getattr(self.git, "enabled", False):
            try:
                sandbox_branch = self.git.create_sandbox(f"auto-fix/{gap.id}")
            except Exception as e:
                self.trace_recorder.record_event(new_trace_event(
                    trace_id=f"self-prog-gap-{gap.id}",
                    event_type=TraceEventType.ERROR,
                    payload={"action": "git_sandbox_failed", "gap_id": gap.id, "error": str(e)},
                ))
        self.trace_recorder.record_event(new_trace_event(
            trace_id=f"self-prog-gap-{gap.id}",
            event_type=TraceEventType.SELF_PROGRAMMING,
            payload={"action": "gap_start", "gap_id": gap.id}
        ))
        
        research_notes = self.research_tool.research_gap(gap).merged_summary if self.config.enable_research else ""
        skill_context = await self._build_skill_context_for_gap(gap)
        
        # Determine target file: use explicit target if provided, else guess
        if backend == "deterministic":
            # Safety: keep deterministic/offline runs away from core modules.
            target_file = f"quentin/mutable/deterministic_{gap.id}.py"
        else:
            if getattr(gap, "target_file", None):
                target_file = gap.target_file
            else:
                target_file = await self._guess_target_file_for_gap(gap)
            
        if not target_file:
             # Fallback or handle error
             target_file = f"quentin/mutable/auto_{gap.id}.py"

        # Phase B: root validation for safety
        allowed_roots = ["quentin/mutable/", "meta_agent/tools/"]
        is_safe_root = any(target_file.startswith(root) for root in allowed_roots)
        if not is_safe_root:
            if backend == "deterministic":
                logger.warning(f"Target file {target_file} not in allowed roots for deterministic mode. Forcing to quentin/mutable.")
                target_file = f"quentin/mutable/deterministic_{gap.id}.py"
            else:
                # Even in non-deterministic mode, we might want to enforce this for safety if configured
                # For now, we only enforce for deterministic as per Phase B.
                pass

        feedback = ""
        code_result = None
        
        for attempt in range(self.config.max_retries + 1):
            self.trace_recorder.record_event(new_trace_event(
                trace_id=f"self-prog-gap-{gap.id}",
                event_type=TraceEventType.SELF_PROGRAMMING,
                payload={"action": "attempt_start", "gap_id": gap.id, "attempt": attempt}
            ))
            
            # Add feedback to instructions if this is a retry
            current_instructions_suffix = f"\n\nPrevious Attempt Feedback:\n{feedback}" if feedback else ""
            
            # Generate code (we need to modify _generate_code_for_gap to accept feedback/instructions tweak)
            # For now, we append feedback to research_notes or pass it somehow. 
            # To avoid changing signature too much, let's append to skill_context or handle inside.
            # Actually, let's create a helper to build full prompt.
            
            # Temporarily modifying instructions generation logic inline or via helper
            instructions = self._build_coder_instructions_for_gap(gap, research_notes, skill_context) + current_instructions_suffix
            context_chunks = build_context_chunks(target_file, gap.related_files)
            req = CodeGenerationRequest(
                goal=f"Implement/improve code for gap: {gap.id}",
                context_files=[c.file_path for c in context_chunks],
                instructions=instructions + "\n\n" + self._format_context_chunks(context_chunks),
                request_tests=True
            )
            code_result = coder_router.generate(req, backend_name=backend)
            
            if not code_result.success:
                feedback = f"Code generation failed: {code_result.reasoning}"
                continue

            payload, parse_error = self._extract_generation_payload(code_result.code)
            if not payload:
                feedback = (
                    f"Failed to parse JSON response: {parse_error}. "
                    "Return ONLY a JSON object with keys 'implementation_code' and 'verification_test_code', no Markdown or fences."
                )
                self.trace_recorder.record_event(new_trace_event(
                    trace_id=f"self-prog-gap-{gap.id}",
                    event_type=TraceEventType.ERROR,
                    payload={"action": "parse_fail", "gap_id": gap.id, "error": parse_error}
                ))
                continue
            implementation_code = payload.implementation_code
            verification_test_code = payload.verification_test_code

            static_ok, static_msg = self._run_static_checks(implementation_code)
            if not static_ok:
                feedback = f"Static checks failed: {static_msg}"
                self.trace_recorder.record_event(new_trace_event(
                    trace_id=f"self-prog-gap-{gap.id}",
                    event_type=TraceEventType.ERROR,
                    payload={"action": "static_checks_failed", "gap_id": gap.id, "error": static_msg[:500]},
                ))
                continue

            # Run in sandbox
            # Support both TestRunnerBackend (run_tests) and legacy SandboxTestRunner (run_in_sandbox)
            run_method = getattr(self.test_runner, "run_tests", getattr(self.test_runner, "run_in_sandbox", None))
            if not run_method:
                raise RuntimeError("Test runner does not have run_tests or run_in_sandbox method")
                
            test_result = run_method(
                implementation_code,
                verification_test_code,
                Path(target_file),
                source_root=Path.cwd(),
            )
            
            if test_result["success"]:
                self.trace_recorder.record_event(new_trace_event(
                    trace_id=f"self-prog-gap-{gap.id}",
                    event_type=TraceEventType.SELF_PROGRAMMING,
                    payload={"action": "sandbox_success", "gap_id": gap.id}
                ))
                # Update code_result.code to be just the implementation for the patch
                code_result.code = implementation_code 
                logger.info(f"Sandbox tests passed for gap {gap.id}. Building patch...")
                break # Success!
            else:
                # Extract error for feedback
                stdout = test_result.get("stdout", "")
                stderr = test_result.get("stderr", "")
                feedback = f"Tests failed.\nSTDOUT:\n{stdout}\nSTDERR:\n{stderr}"
                logger.error(f"Sandbox tests failed for gap {gap.id}:\n{feedback}")
                self.trace_recorder.record_event(new_trace_event(
                    trace_id=f"self-prog-gap-{gap.id}",
                    event_type=TraceEventType.SELF_PROGRAMMING,
                    payload={"action": "sandbox_fail", "gap_id": gap.id, "feedback_len": len(feedback), "stdout": stdout, "stderr": stderr}
                ))
        
        if not code_result or not code_result.success or feedback.startswith("Tests failed"):
            logger.warning(f"Gap {gap.id} failed after retries or generation failure.")
            self._enqueue_system_event(
                event_type="self_programming_gap_failed",
                gap=gap,
                payload={
                    "status": "failed",
                    "reason": "max_retries_exceeded_or_generation_failed",
                },
            )
            self.trace_recorder.record_event(new_trace_event(
                trace_id=f"self-prog-gap-{gap.id}",
                event_type=TraceEventType.SELF_PROGRAMMING,
                payload={"action": "gap_failed", "gap_id": gap.id, "reason": "Max retries exceeded or generation failed"}
            ))
            if sandbox_branch and self.git and getattr(self.git, "enabled", False):
                try:
                    self.git.cleanup_sandbox(sandbox_branch)
                except Exception:
                    pass
            return

        # Use the verified implementation code
        proposal = self._build_patch_from_code(gap, code_result.code, target_file)
        if not proposal: 
            logger.error("Failed to build patch proposal from code.")
            return
        
        # Save initial proposal
        self.patch_store.save_patch(proposal)

        report = self._evaluator.evaluate(proposal)
        logger.info(f"Patch evaluated. Asking council...")
        decision = await self._council.decide_on_patch(proposal, report, gap, snapshot)
        
        if not decision.should_apply:
            logger.warning(f"Council rejected patch: {decision.reason}")
            self._enqueue_system_event(
                event_type="self_programming_patch_rejected",
                gap=gap,
                payload={
                    "status": "rejected",
                    "reason": str(getattr(decision, "reason", "") or ""),
                    "patch_id": proposal.id,
                },
            )
            proposal.status = "rejected" # Update status
            self.patch_store.save_patch(proposal) # Persist status change
            self._persist_patch_report_v1(
                patch_id=proposal.id,
                gap_id=gap.id,
                target_files=list(proposal.target_files or []),
                status="rejected",
                decision={"should_apply": False, "reason": getattr(decision, "reason", "")},
                static_checks={"ok": True, "message": ""},
                tests={"success": False, "stdout": "", "stderr": ""},
                safety={"blocked": False, "reason": None, "requires_human_review": True},
            )
            return
        
        logger.info("Council approved. Applying patch...")
        if self.config.proposal_only or not self.config.allow_auto_apply or not feature_flags.get_auto_patch_flag().enabled: 
            logger.info("Auto-apply disabled or proposal-only mode active.")
            self._enqueue_system_event(
                event_type="self_programming_patch_proposed",
                gap=gap,
                payload={
                    "status": "proposed",
                    "reason": "auto_apply_disabled_or_proposal_only",
                    "patch_id": proposal.id,
                },
            )
            if sandbox_branch and self.git and getattr(self.git, "enabled", False):
                try:
                    # Don't merge, just delete the sandbox branch
                    self.git.cleanup_sandbox(sandbox_branch)
                except Exception:
                    pass
            return

        safety_result = None
        if self._should_use_safety_wrapper(proposal):
            # Run patch-level safety checks but route file writes through ToolManager.
            safety_result = self._applier.checker.check(proposal)
            if not safety_result.allow_apply:
                logger.error("Patch safety check blocked before wrapper apply: %s", safety_result.reasons)
            else:
                try:
                    await self._apply_with_safety_wrapper(proposal)
                except Exception as e:
                    safety_result.allow_apply = False
                    safety_result.requires_human_review = True
                    safety_result.reasons = list(safety_result.reasons or []) + [f"safety_wrapper_failed:{e}"]
        else:
            safety_result = self._applier.apply_patch(proposal)
        if safety_result.is_blocked:
            reason = "; ".join(list(getattr(safety_result, "reasons", []) or []))
            logger.error("Patch application blocked: %s", reason)
            self._enqueue_system_event(
                event_type="self_programming_patch_blocked",
                gap=gap,
                payload={
                    "status": "blocked",
                    "reason": reason,
                    "patch_id": proposal.id,
                },
            )
            proposal.status = "blocked" # Update status
            self.patch_store.save_patch(proposal) # Persist status change
            self._persist_patch_report_v1(
                patch_id=proposal.id,
                gap_id=gap.id,
                target_files=list(proposal.target_files or []),
                status="blocked",
                decision={"should_apply": True, "reason": getattr(decision, "reason", "")},
                static_checks={"ok": True, "message": ""},
                tests={"success": True, "stdout": "", "stderr": ""},
                safety={"blocked": True, "reason": reason, "requires_human_review": True},
            )
            if sandbox_branch and self.git and getattr(self.git, "enabled", False):
                try:
                    self.git.cleanup_sandbox(sandbox_branch)
                except Exception:
                    pass
            return

        logger.info(f"Patch applied successfully! ID: {proposal.id}")
        proposal.status = "applied" # Update status
        self.patch_store.save_patch(proposal) # Persist status change
        
        # P5: Signal system via bus for loose coupling
        get_system_bus().publish(SystemEvent(
            type="PATCH_APPLIED",
            source="self_programming_engine",
            payload={"patch_id": proposal.id, "gap_id": gap.id, "target_files": proposal.target_files}
        ))

        # Persist a structured patch report for observability (schema-stable).
        try:
            self._persist_patch_report_v1(
                patch_id=proposal.id,
                gap_id=gap.id,
                target_files=list(proposal.target_files or []),
                status="applied",
                decision={"should_apply": True, "reason": getattr(decision, "reason", "")},
                static_checks={"ok": True, "message": static_msg if "static_msg" in locals() else ""},
                tests=test_result if "test_result" in locals() else {"success": True},
                safety={
                    "blocked": False,
                    "reason": None,
                    "requires_human_review": bool(getattr(safety_result, "requires_human_review", False)),
                    "reasons": list(getattr(safety_result, "reasons", []) or []),
                },
            )
        except Exception:
            pass
        self.trace_recorder.record_event(new_trace_event(
            trace_id=f"self-prog-gap-{gap.id}",
            event_type=TraceEventType.SELF_PROGRAMMING,
            payload={"action": "patch_applied", "gap_id": gap.id, "patch_id": proposal.id}
        ))
        self._enqueue_system_event(
            event_type="self_programming_patch_applied",
            gap=gap,
            payload={
                "status": "applied",
                "patch_id": proposal.id,
                "message": f"Patch {proposal.id} applied for gap {gap.id}.",
            },
        )

        # Blueprint v3: record release protocol lifecycle (shadow/canary) as a schema-stable placeholder.
        try:
            self._record_release_protocol(
                gap=gap,
                proposal=proposal,
                decision=decision,
            )
        except Exception:
            pass

        # Commit/merge and cleanup sandbox
        if sandbox_branch and self.git and getattr(self.git, "enabled", False):
            try:
                self.git.finalize_success(
                    sandbox_branch,
                    commit_message=f"auto-fix {gap.id}",
                    merge=True,
                    delete_branch=True,
                )
            except Exception as e:
                self.trace_recorder.record_event(new_trace_event(
                    trace_id=f"self-prog-gap-{gap.id}",
                    event_type=TraceEventType.ERROR,
                    payload={"action": "git_finalize_failed", "gap_id": gap.id, "error": str(e)},
                ))

    async def _apply_with_safety_wrapper(self, proposal: PatchProposal) -> bool:
        """
        Apply direct-content patches via ToolManager so path/syntax/security middleware run.
        Returns True when wrapper handled writes, False to keep normal applier behavior.
        """
        if self._safety_wrapper is None:
            return False
        new_content = (proposal.metadata or {}).get("new_content")
        target_files = list(proposal.target_files or [])
        if not isinstance(new_content, str) or not target_files:
            return False

        for rel_path in target_files:
            await self._safety_wrapper.safe_write_file(
                path=str(rel_path),
                content=new_content,
                reason=f"selfprog_patch:{proposal.id}",
            )
        return True

    def _should_use_safety_wrapper(self, proposal: PatchProposal) -> bool:
        if self._safety_wrapper is None:
            return False
        new_content = (proposal.metadata or {}).get("new_content")
        return isinstance(new_content, str) and bool(proposal.target_files)

    def _enqueue_system_event(self, *, event_type: str, gap: GapLike, payload: dict) -> None:
        if not feature_flags.is_prompt_migration_enabled(PROMPT_MIGRATION_M3_SYSTEM_EVENTS, default=False):
            return
        session_id = "global"
        try:
            self.system_event_queue.enqueue_event(
                session_id=session_id,
                event_type=event_type,
                payload={
                    "gap_id": str(getattr(gap, "id", "") or ""),
                    **(payload or {}),
                },
                source="self_programming_engine_v2",
            )
            self.trace_recorder.record_event(
                new_trace_event(
                    trace_id=f"self-prog-gap-{gap.id}",
                    event_type=TraceEventType.DECISION,
                    payload={
                        "action": PROMPT_MIGRATION_SYSTEM_EVENT_ENQUEUED,
                        "session_id": session_id,
                        "event_type": event_type,
                        "gap_id": str(getattr(gap, "id", "") or ""),
                    },
                )
            )
        except Exception:
            logger.exception("SelfProgrammingEngineV2: failed to enqueue system event")

    def _record_release_protocol(self, *, gap: GapLike, proposal: PatchProposal, decision: CouncilDecision) -> None:
        if not getattr(self.config, "enable_release_protocol", False):
            return
        try:
            from quentin.l3.research.release_protocol import (
                FileBackedVariantLifecycleStore,
                shadow_request,
                canary_request,
            )
        except Exception:
            return

        repo_root = Path.cwd()
        store = FileBackedVariantLifecycleStore(repo_root=repo_root)
        variant_id = f"patch:{proposal.id}"
        environment = str(getattr(self.config, "release_environment", "sandbox") or "sandbox")

        # Policy gate: only record shadow/canary when allowed, and respect required gates.
        try:
            from quentin.kernel.safety import SafetyKernel
            from quentin.kernel.policy import ActionRequest
        except Exception:
            SafetyKernel = None  # type: ignore[assignment]
            ActionRequest = None  # type: ignore[assignment]

        policy_meta = {
            "patch_id": proposal.id,
            "gap_id": gap.id,
            "variant_id": variant_id,
            "release_stage": "shadow_canary",
        }
        domain = str(getattr(gap, "domain", None) or "core")
        risk = str(getattr(decision, "risk_level", "high") or "high").lower()

        require_canary = False
        require_human_gate = False
        if SafetyKernel is not None and ActionRequest is not None:
            try:
                kernel = SafetyKernel()
                action = ActionRequest.new(
                    actor="selfprog_engine_v2",
                    action_type="deploy",
                    domain=domain,
                    environment=environment,
                    risk_level=risk if risk in ("low", "medium", "high", "critical") else "high",
                    estimated_cost_tokens=0,
                    description="Record patch release protocol (shadow/canary).",
                    metadata=policy_meta,
                )
                guard = kernel.guard_action(action)
                if not guard.allow:
                    self.trace_recorder.record_event(
                        new_trace_event(
                            trace_id=f"self-prog-gap-{gap.id}",
                            event_type=TraceEventType.DECISION,
                            payload={
                                "action": "release_protocol_denied",
                                "variant_id": variant_id,
                                "environment": environment,
                                "reason": guard.reason,
                                "policy": guard.policy_decision.to_dict(),
                            },
                        )
                    )
                    return
                mods = guard.policy_decision.modifications or {}
                require_canary = bool(mods.get("require_canary", False))
                require_human_gate = bool(mods.get("require_human_gate", False))
            except Exception:
                pass

        if require_human_gate:
            # No human-approval mechanism is wired for auto self-programming yet; record a trace and exit.
            self.trace_recorder.record_event(
                new_trace_event(
                    trace_id=f"self-prog-gap-{gap.id}",
                    event_type=TraceEventType.DECISION,
                    payload={
                        "action": "release_protocol_blocked_human_gate",
                        "variant_id": variant_id,
                        "environment": environment,
                        "domain": domain,
                        "risk_level": risk,
                        "require_canary": require_canary,
                    },
                )
            )
            return

        shadow = shadow_request(
            store=store,
            variant_id=variant_id,
            environment=environment,
            request_id=f"shadow::{uuid.uuid4().hex}",
            meta={
                "patch_id": proposal.id,
                "gap_id": gap.id,
                "domain": domain,
                "risk_level": getattr(decision, "risk_level", ""),
                "require_canary": require_canary,
            },
        )

        canary = None
        if getattr(self.config, "enable_canary", False):
            risk = str(getattr(decision, "risk_level", "high") or "high").lower()
            frac = float(getattr(self.config, "canary_fraction", 0.1) or 0.1)
            frac = max(0.0, min(1.0, frac))
            if risk in ("low", "medium") and frac > 0.0:
                canary = canary_request(
                    store=store,
                    variant_id=variant_id,
                    environment=environment,
                    request_id=f"canary::{uuid.uuid4().hex}",
                    fraction=frac,
                    meta={
                        "patch_id": proposal.id,
                        "gap_id": gap.id,
                        "domain": domain,
                        "risk_level": getattr(decision, "risk_level", ""),
                    },
                )
        elif require_canary:
            # Policy demanded canary but runtime config has it disabled.
            self.trace_recorder.record_event(
                new_trace_event(
                    trace_id=f"self-prog-gap-{gap.id}",
                    event_type=TraceEventType.DECISION,
                    payload={
                        "action": "release_protocol_blocked_require_canary",
                        "variant_id": variant_id,
                        "environment": environment,
                        "domain": domain,
                        "risk_level": risk,
                    },
                )
            )

        self.trace_recorder.record_event(
            new_trace_event(
                trace_id=f"self-prog-gap-{gap.id}",
                event_type=TraceEventType.SELF_PROGRAMMING,
                payload={
                    "action": "release_protocol_recorded",
                    "patch_id": proposal.id,
                    "variant_id": variant_id,
                    "environment": environment,
                    "shadow": shadow,
                    "canary": canary,
                },
            )
        )

    def _persist_patch_report_v1(
        self,
        *,
        patch_id: str,
        gap_id: str,
        target_files: list[str],
        status: str,
        decision: Dict[str, Any],
        static_checks: Dict[str, Any],
        tests: Dict[str, Any],
        safety: Dict[str, Any],
        perf_delta: Optional[Dict[str, Any]] = None,
        risk_assessment: Optional[Dict[str, Any]] = None,
        coverage: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Schema-stable patch report required by blueprint v3.

        Writes:
        - `data/patch_reports/{patch_id}.json`
        """
        from pathlib import Path
        import json
        from datetime import datetime

        repo_root = self.repo_root
        out_dir = repo_root / "data" / "patch_reports"
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"{patch_id}.json"

        obj = {
            "patch_id": patch_id,
            "gap_id": gap_id,
            "status": status,
            "target_files": list(target_files or []),
            "tests": {
                "unit": tests,
                "regression": None,
            },
            "static_checks": static_checks,
            "perf_delta": perf_delta,
            "risk_assessment": risk_assessment
            or {
                "safety": safety,
            },
            "coverage": coverage,
            "decision": decision,
            "created_at": now_iso(),
        }
        out_path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")

    async def _build_skill_context_for_gap(self, gap: GapLike) -> str:
        """
        Searches the vector store for skills relevant to the gap description.
        """
        self.trace_recorder.record_event(new_trace_event(
            trace_id=f"self-prog-gap-{gap.id}",
            event_type=TraceEventType.SELF_PROGRAMMING,
            payload={"action": "build_skill_context_start", "gap_id": gap.id}
        ))
        try:
            search_results = await self.vector_store.search(
                query_text=gap.description,
                n_results=5,
            )
            if not search_results:
                return ""

            context_lines = ["# Here are some existing skills that might be relevant:"]
            for result in search_results:
                metadata = result.get('metadata', {})
                if not metadata: continue

                context_lines.append(f"\n# From: {metadata.get('file_path', 'unknown')}")
                context_lines.append(f"# Function/Class: {metadata.get('fully_qualified_name', '')}")
                
                # Add a simplified signature
                content_lines = result.get('content', '').splitlines()
                if content_lines:
                    context_lines.append(f"def {metadata.get('name', '')}(...):")
                
                docstring = metadata.get('docstring')
                if docstring:
                    context_lines.append(f'    """{docstring}"""')
            
            context_str = "\n".join(context_lines)
            self.trace_recorder.record_event(new_trace_event(
                trace_id=f"self-prog-gap-{gap.id}",
                event_type=TraceEventType.SELF_PROGRAMMING,
                payload={"action": "build_skill_context_end", "gap_id": gap.id, "context_found": True, "num_results": len(search_results)}
            ))
            return context_str

        except Exception as e:
            self.trace_recorder.record_event(new_trace_event(
                trace_id=f"self-prog-gap-{gap.id}",
                event_type=TraceEventType.ERROR,
                payload={"action": "build_skill_context_error", "gap_id": gap.id, "error": str(e)}
            ))
            return "" 

    def _generate_code_for_gap(self, gap: GapLike, research_notes: str, skill_context: str, backend: str) -> CodeGenerationResult:
        instructions = self._build_coder_instructions_for_gap(gap, research_notes, skill_context)
        req = CodeGenerationRequest(
            goal=f"Implement/improve code for gap: {gap.id}", 
            context_files=gap.related_files, 
            instructions=instructions,
            request_tests=True  # Explicitly request tests
        )
        return coder_router.generate(req, backend_name=backend)

    def _build_coder_instructions_for_gap(self, gap: GapLike, research_notes: str, skill_context: str) -> str:
        prompt = f"Gap: {gap.title}\n{gap.description}"
        if research_notes: prompt += f"\n\nResearch Report:\n{research_notes}"
        if skill_context: prompt += f"\n\nRelevant Skills:\n{skill_context}"
        prompt += (
            "\n\nPlease generate code to address the gap, using the research and reusing skills. "
            "Respond with ONLY a JSON object (no Markdown fences, no extra text) with exactly two string fields: "
            "'implementation_code' and 'verification_test_code'. "
            "The test code should be a valid pytest function that verifies the implementation. "
            "Do not wrap the JSON in ```json```; return raw JSON."
        )
        return prompt

    def _format_context_chunks(self, chunks) -> str:
        if not chunks:
            return ""
        lines = ["# Context snippets (target file full, others signatures only):"]
        for c in chunks:
            lines.append(f"\n# File: {c.file_path}\n{c.content}")
        return "\n".join(lines)

    def _extract_generation_payload(self, text: str) -> tuple[Optional[GenerationPayload], Optional[str]]:
        """
        Robustly extract and validate the generation payload using Pydantic.
        """
        def try_parse(blob: str) -> tuple[Optional[GenerationPayload], Optional[str]]:
            try:
                return GenerationPayload.model_validate_json(blob), None
            except ValidationError as ve:
                return None, f"validation_error: {ve}"
            except json.JSONDecodeError as je:
                return None, f"json_error: {je}"
            except Exception as e:  # pragma: no cover - defensive
                return None, f"parse_error: {e}"

        candidates: List[str] = []
        text = text.strip()
        candidates.append(text)

        fenced = re.findall(r"```json\\s*(.*?)```", text, flags=re.DOTALL)
        candidates.extend([c.strip() for c in fenced if c.strip()])
        generic_fenced = re.findall(r"```\\s*(.*?)```", text, flags=re.DOTALL)
        candidates.extend([c.strip() for c in generic_fenced if c.strip()])

        decoder = json.JSONDecoder()
        for idx, ch in enumerate(text):
            if ch == "{":
                try:
                    obj, end = decoder.raw_decode(text[idx:])
                    candidates.append(text[idx: idx + end])
                    break
                except Exception:
                    continue

        errors: List[str] = []
        for blob in candidates:
            payload, err = try_parse(blob)
            if payload:
                return payload, None
            if err:
                errors.append(err)
        return None, "; ".join(errors) if errors else "unable to parse JSON payload"

    def _run_static_checks(self, implementation_code: str) -> tuple[bool, str]:
        """
        Run lightweight static checks (flake8 + bandit) if available.
        """
        tmp_dir = Path(tempfile.mkdtemp())
        code_path = tmp_dir / "impl.py"
        code_path.write_text(implementation_code, encoding="utf-8")
        msgs: List[str] = []

        def _maybe_run(cmd: List[str], name: str) -> bool:
            try:
                res = subprocess.run(cmd, cwd=tmp_dir, capture_output=True, text=True)
            except FileNotFoundError:
                return True  # tool not installed, skip
            if res.returncode != 0:
                msgs.append(f"{name} failed: {res.stdout} {res.stderr}")
                return False
            return True

        ok_flake8 = _maybe_run(["flake8", str(code_path)], "flake8")
        ok_bandit = _maybe_run(["bandit", "-q", "-r", str(code_path)], "bandit")
        shutil.rmtree(tmp_dir, ignore_errors=True)
        return ok_flake8 and ok_bandit, "\n".join(msgs)

    # ... (other imports)

# ... (previous code) ...

    def _build_patch_from_code(self, gap: GapLike, new_content: str, target_file: str) -> Optional[PatchProposal]:
        import difflib
        path = Path(target_file)
        
        original_content = ""
        if path.exists():
            try:
                original_content = path.read_text(encoding="utf-8")
            except Exception:
                pass
        
        # Normalize line endings
        orig_lines = original_content.splitlines(keepends=True)
        new_lines = new_content.splitlines(keepends=True)
        
        diff = difflib.unified_diff(
            orig_lines,
            new_lines,
            fromfile=target_file,
            tofile=target_file,
        )
        diff_text = "".join(diff)
        
        # If no diff but file doesn't exist? (New file creation)
        # unified_diff with empty original produces valid diff for new file.
        # But if diff_text is empty and original==new, then no change.
        if not diff_text and original_content == new_content:
            return None
            
        return PatchProposal(
            id=str(uuid.uuid4()),
            target_files=[target_file],
            diff=diff_text,
            intent=f"Fix gap: {gap.title}",
            metadata={"gap_id": gap.id, "author": "engine_v2", "new_content": new_content},
            status="proposed",
        )
    
    async def _guess_target_file_for_gap(self, gap: GapLike) -> str:
        """
        Uses an LLM to guess the most likely file to modify based on the gap description.
        """
        self.trace_recorder.record_event(new_trace_event(
            trace_id=f"self-prog-gap-{gap.id}",
            event_type=TraceEventType.SELF_PROGRAMMING,
            payload={"action": "guess_target_file_start", "gap_id": gap.id}
        ))
        try:
            # Get a list of all files in the repo, with some common ignores
            all_files = glob.glob('**/*', recursive=True)
            files = [f for f in all_files if not os.path.isdir(f) and not f.endswith(('.pyc', '.log')) and '.git/' not in f]
            
            context = {
                "gap_title": gap.title,
                "gap_description": gap.description,
                "file_tree": "\n".join(files[:500]),  # Limit to avoid huge prompts
            }

            question = (
                "Based on the following 'gap' description, which file from the file tree is the most likely target for modification? "
                "Provide only the single most likely file path."
            )

            json_schema_hint = """
            {
                "best_guess_file_path": "path/to/your/best/guess.py"
            }
            """

            result_dict = await council.ask_json(
                role="file_path_guesser",
                question=question,
                context=context,
                json_schema_hint=json_schema_hint,
            )
            
            file_path = result_dict.get("best_guess_file_path", "")
            self.trace_recorder.record_event(new_trace_event(
                trace_id=f"self-prog-gap-{gap.id}",
                event_type=TraceEventType.SELF_PROGRAMMING,
                payload={"action": "guess_target_file_end", "gap_id": gap.id, "guessed_path": file_path}
            ))
            return file_path

        except Exception as e:
            self.trace_recorder.record_event(new_trace_event(
                trace_id=f"self-prog-gap-{gap.id}",
                event_type=TraceEventType.ERROR,
                payload={"action": "guess_target_file_error", "gap_id": gap.id, "error": str(e)}
            ))
            return ""
