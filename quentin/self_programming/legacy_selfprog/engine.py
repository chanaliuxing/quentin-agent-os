from __future__ import annotations

from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Any, Dict, Optional
import difflib
import json
import logging
import subprocess
import textwrap
import uuid

from quentin.kernel.safety import SafetyKernel, GuardResult
from quentin.kernel.policy import ActionRequest
from quentin.llm.router import ModelRouter
from quentin.llm.types import LLMConfig
from quentin.llm.multi_council import MultiAICouncil, CouncilDecision
from quentin.l3.research.experiments import ResearchManager
from quentin.traces.execution_trace import ExecutionTrace
from quentin.llm.client import call_llm
from quentin.utils.time import now_iso

logger = logging.getLogger(__name__)


@dataclass
class PatchTaskSpec:
    target_path: str
    reason: str
    domain: str = "core"
    environment: str = "sandbox"
    risk_level: str = "high"
    context_snippet: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class PatchTestResult:
    passed: bool
    command: str
    stdout: str
    stderr: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class PatchGateResult:
    approved: bool
    council_summary: str
    council_raw_answer: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class PatchResult:
    task_id: str
    target_path: str
    success: bool
    applied: bool
    guard: GuardResult
    test_result: Optional[PatchTestResult]
    gate_result: Optional[PatchGateResult]
    new_code_preview: str
    error: Optional[str] = None
    created_at: str = field(default_factory=lambda: now_iso())

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class PatchGateCouncil:
    def __init__(self, council: Optional[MultiAICouncil] = None, router: Optional[ModelRouter] = None) -> None:
        if council is None:
            router = router or ModelRouter()
            cfg = router.route(mode="critic", task_type="code_patch")
            members = [
                LLMConfig(provider=cfg.provider, model=cfg.model, role="Speed-Agent"),
                LLMConfig(provider=cfg.provider, model=cfg.model, role="Safety-Agent"),
                LLMConfig(provider=cfg.provider, model=cfg.model, role="Cost-Agent"),
                LLMConfig(provider=cfg.provider, model=cfg.model, role="Domain-Expert-Agent"),
            ]
            council = MultiAICouncil(members=members)
        self.council = council

    def review(
        self,
        *,
        target_path: str,
        reason: str,
        diff_text: str,
        test_result: Optional[PatchTestResult],
    ) -> PatchGateResult:
        context_parts = [
            f"TARGET PATH: {target_path}",
            "",
            f"REASON:\n{reason}",
            "",
            "UNIFIED DIFF (old -> new):",
            diff_text,
        ]
        if test_result is not None:
            context_parts.append("")
            context_parts.append("TEST RESULT:")
            context_parts.append(f"command: {test_result.command}")
            context_parts.append(f"passed : {test_result.passed}")
            context_parts.append("stdout :")
            context_parts.append(test_result.stdout[:2000])
            context_parts.append("stderr :")
            context_parts.append(test_result.stderr[:2000])

        context = "\n".join(context_parts)
        question = (
            "You are a PATCH REVIEW COUNCIL for a self-evolving AI system.\n"
            "Given the patch diff and test results, you must decide whether to approve it.\n\n"
            "Return ONLY one JSON object:\n"
            "{ \"approved\": true/false, \"summary\": \"short explanation\" }\n"
        )

        decision: CouncilDecision = self.council.deliberate(question=question, context=context, mode="patch_gate")
        ans = decision.final_answer or "{}"
        try:
            s = ans.strip()
            first = s.find("{")
            last = s.rfind("}")
            if first != -1 and last != -1 and last > first:
                s = s[first : last + 1]
            data = json.loads(s)
            approved = bool(data.get("approved", False))
            summary = str(data.get("summary", "") or "")
        except Exception:
            logger.exception("PatchGateCouncil.review: failed to parse council JSON: %r", ans)
            approved = False
            summary = "Failed to parse council answer; default to not approved."

        return PatchGateResult(approved=approved, council_summary=summary, council_raw_answer=ans)


class SelfProgrammingEngine:
    def __init__(
        self,
        *,
        repo_root: str | Path = ".",
        safety_kernel: Optional[SafetyKernel] = None,
        model_router: Optional[ModelRouter] = None,
        patch_gate: Optional[PatchGateCouncil] = None,
        research_manager: Optional[ResearchManager] = None,
    ) -> None:
        self.repo_root = Path(repo_root).resolve()
        self.safety_kernel = safety_kernel or SafetyKernel()
        self.model_router = model_router or ModelRouter()
        self.patch_gate = patch_gate or PatchGateCouncil(router=self.model_router)
        self.research_manager = research_manager or ResearchManager()

    def propose_and_apply_patch(self, task: PatchTaskSpec) -> PatchResult:
        task_id = str(uuid.uuid4())
        target_file = (self.repo_root / task.target_path).resolve()

        estimated_tokens = self._estimate_tokens_for_task(task, target_file)
        action = ActionRequest.new(
            actor="selfprog_engine",
            action_type="code_patch",
            domain=task.domain,
            environment=task.environment,
            risk_level=task.risk_level,
            estimated_cost_tokens=estimated_tokens,
            estimated_cost_usd=0.0,
            description=task.reason,
            metadata={"target_path": task.target_path, "task_id": task_id},
        )
        guard = self.safety_kernel.guard_action(action)
        if not guard.allow:
            return PatchResult(
                task_id=task_id,
                target_path=task.target_path,
                success=False,
                applied=False,
                guard=guard,
                test_result=None,
                gate_result=None,
                new_code_preview="",
                error=f"Denied by SafetyKernel: {guard.reason}",
            )

        try:
            old_code = target_file.read_text(encoding="utf-8")
        except FileNotFoundError:
            return PatchResult(
                task_id=task_id,
                target_path=task.target_path,
                success=False,
                applied=False,
                guard=guard,
                test_result=None,
                gate_result=None,
                new_code_preview="",
                error=f"target file not found: {task.target_path}",
            )

        cfg = self.model_router.route(mode="coder", task_type="self_programming_patch")
        sys = "You are a senior Python engineer. Output ONLY the full new file content."
        user = self._build_prompt(old_code=old_code, task=task)
        try:
            new_code = call_llm(
                cfg.model,
                user_prompt=user,
                system_prompt=sys,
                provider=cfg.provider,
                model_name=cfg.model,
                action_metadata={"topic": "legacy_selfprog_patch", "target_path": task.target_path},
            )
        except Exception as e:  # noqa: BLE001
            return PatchResult(
                task_id=task_id,
                target_path=task.target_path,
                success=False,
                applied=False,
                guard=guard,
                test_result=None,
                gate_result=None,
                new_code_preview="",
                error=f"llm_call_failed: {e}",
            )

        diff_text = "".join(
            difflib.unified_diff(
                old_code.splitlines(keepends=True),
                str(new_code).splitlines(keepends=True),
                fromfile=f"a/{task.target_path}",
                tofile=f"b/{task.target_path}",
            )
        )

        test_result = self._run_tests()
        gate = self.patch_gate.review(target_path=task.target_path, reason=task.reason, diff_text=diff_text, test_result=test_result)
        if not gate.approved:
            return PatchResult(
                task_id=task_id,
                target_path=task.target_path,
                success=False,
                applied=False,
                guard=guard,
                test_result=test_result,
                gate_result=gate,
                new_code_preview=str(new_code)[:200],
                error=f"patch_gate_rejected: {gate.council_summary}",
            )

        try:
            target_file.parent.mkdir(parents=True, exist_ok=True)
            target_file.write_text(str(new_code), encoding="utf-8")
        except Exception as e:  # noqa: BLE001
            return PatchResult(
                task_id=task_id,
                target_path=task.target_path,
                success=False,
                applied=False,
                guard=guard,
                test_result=test_result,
                gate_result=gate,
                new_code_preview=str(new_code)[:200],
                error=f"write_failed: {e}",
            )

        try:
            self.research_manager.record_run(
                experiment_id="legacy_selfprog",
                variant_id="baseline",
                metrics={"applied": 1},
                context={"target_path": task.target_path},
            )
        except Exception:
            pass

        try:
            ExecutionTrace(
                trace_id=f"legacy_selfprog::{task_id}",
                task_id=task_id,
                component_id="selfprog",
                blueprint_capability_id="self_programming",
                target_module=task.target_path,
                target_symbol=task.metadata.get("target_symbol") if isinstance(task.metadata, dict) else None,
                success=True,
                error_type=None,
                error_message=None,
                start_time="",
                end_time="",
                metrics={"applied": 1},
                tags={"mode": "legacy_selfprog"},
            )
        except Exception:
            pass

        return PatchResult(
            task_id=task_id,
            target_path=task.target_path,
            success=True,
            applied=True,
            guard=guard,
            test_result=test_result,
            gate_result=gate,
            new_code_preview=str(new_code)[:200],
            error=None,
        )

    def _estimate_tokens_for_task(self, task: PatchTaskSpec, target_file: Path) -> int:
        try:
            text = target_file.read_text(encoding="utf-8")
        except Exception:
            text = ""
        return max(1, int(len(text) / 4) + int(len(task.reason or "") / 4) + 2048)

    def _build_prompt(self, *, old_code: str, task: PatchTaskSpec) -> str:
        return textwrap.dedent(
            f"""
            You are editing file: {task.target_path}
            Reason: {task.reason}
            Domain: {task.domain}
            Environment: {task.environment}
            Risk: {task.risk_level}

            Context snippet (optional):
            {task.context_snippet}

            Current file content:
            {old_code}
            """
        ).strip()

    def _run_tests(self, command: str = "pytest -q") -> Optional[PatchTestResult]:
        try:
            proc = subprocess.run(command, cwd=str(self.repo_root), shell=True, capture_output=True, text=True)
            return PatchTestResult(
                passed=proc.returncode == 0,
                command=command,
                stdout=(proc.stdout or "")[:4000],
                stderr=(proc.stderr or "")[:4000],
            )
        except Exception:
            return None
