from __future__ import annotations

from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Any, Dict, List, Optional
import importlib
import json
import logging
import os
import re
import time

from quentin.traces.core import TraceEventType, new_trace_event
from quentin.skills.manager import SkillManager, SkillSpec
from quentin.models.router import ModelRouter
from quentin.llm.client import call_llm, call_llm_with_tools
from quentin.llm.tool_call_protocols import (
    bootstrap_protocols,
    get_tool_call_protocol_registry,
    is_protocol_registry_enabled,
    ProtocolDecision,
)
from quentin.cognitive.context_snapshots import (
    bootstrap_snapshots,
    get_context_snapshot_registry,
    is_context_snapshots_enabled,
)
from quentin.cognitive.prompt_layers import build_layered_system_prompt
from quentin.tools.summary_map import format_tool_summary_block, build_tool_summary_map
from quentin.utils.time import now_utc_iso
from quentin.infra.concurrency.abort_signal import abort_registry
from quentin.infra.text.markdown_parser import MarkdownCodeDetector
from quentin.execution.virtual_canvas import VirtualCanvas
from quentin.execution.idempotency import IdempotencyGate
from quentin.execution.contract import StepContractGuard
from quentin.agents.pi_embedded_helpers.errors import classify_error_taxonomy
from quentin.agents.pi_embedded_helpers.json_truncation import truncate_json_text
from quentin.agents.pi_embedded_helpers.xml import enforce_closed_tag_blocks

logger = logging.getLogger(__name__)


from quentin.infra.tools.display import resolve_tool_display, format_tool_summary

@dataclass
class StepExecutionRecord:
    """A small, JSON-friendly step execution record."""

    step_id: str
    description: str
    skill_id: Optional[str]
    executor_mode: str  # "skill" | "llm" | "noop"
    success: bool
    result: Any = None
    error: Optional[str] = None
    started_at: str = field(default_factory=now_utc_iso)
    finished_at: str = field(default_factory=now_utc_iso)
    direct_response_sent: bool = False
    summary: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class Executor:
    """
    Skill-first executor with LLM fallback and direct tool calling.
    """

    def __init__(
        self,
        *,
        repo_root: str | Path = ".",
        model_router: Optional[ModelRouter] = None,
        skill_manager: Optional[SkillManager] = None,
        tool_manager: Optional[Any] = None,
    ) -> None:
        self.repo_root = Path(repo_root).resolve()
        self.model_router = model_router or ModelRouter()
        self.skill_manager = skill_manager or SkillManager(repo_root=self.repo_root)
        self.tool_manager = tool_manager
        self._native_tool_calling_disabled_reason: Optional[str] = None
        self._native_tool_calling_disable_logged: bool = False
        self.virtual_canvas = VirtualCanvas()
        self.idempotency_gate = IdempotencyGate(repo_root=repo_root)
        self.step_contract_guard = StepContractGuard()
        self._tool_knowledge_prompt_enabled = str(
            os.getenv("QUENTIN_EXECUTOR_TOOL_KNOWLEDGE_PROMPT", "1")
        ).strip().lower() in ("1", "true", "yes", "on")
        try:
            self._tool_knowledge_prompt_top_k = max(
                1, int(os.getenv("QUENTIN_EXECUTOR_TOOL_KNOWLEDGE_TOP_K", "8") or 8)
            )
        except Exception:
            self._tool_knowledge_prompt_top_k = 8
        try:
            self._tool_knowledge_prompt_examples_per_tool = max(
                1, int(os.getenv("QUENTIN_EXECUTOR_TOOL_KNOWLEDGE_EXAMPLES_PER_TOOL", "1") or 1)
            )
        except Exception:
            self._tool_knowledge_prompt_examples_per_tool = 1
        self._tool_knowledge_block_cache: Optional[str] = None
        self._tool_knowledge_block_cache_at: float = 0.0
        self._tool_knowledge_block_cache_ttl_s: float = 5.0
        
        # P2-D Cache feature flags
        self._is_protocol_registry_enabled = is_protocol_registry_enabled()
        self._is_context_snapshots_enabled = is_context_snapshots_enabled()

        if self._is_protocol_registry_enabled:
            bootstrap_protocols()
        
        if self._is_context_snapshots_enabled:
            bootstrap_snapshots()

    async def run_step(self, step: Dict[str, Any], context: Dict[str, Any], goal: Any = None) -> Any:
        return await self._execute_step(step=step, context=context, goal=goal)

    @staticmethod
    def _emit_alignment_trace_event(
        *,
        context: Dict[str, Any],
        step_id: str,
        iteration: int,
        event: Dict[str, Any],
    ) -> None:
        rec = context.get("trace_recorder")
        trace_id = str(context.get("trace_id") or "").strip()
        if rec is None or not trace_id:
            return
        if not isinstance(event, dict):
            return
        try:
            payload = {
                "signal": "plan_tool_alignment",
                "step_id": str(step_id or ""),
                "iteration": int(iteration or 0),
                "event_type": str(event.get("type") or ""),
                "reason": str(event.get("reason") or ""),
                "expected_tool": str(event.get("expected_tool") or ""),
                "actual_tool": str(event.get("actual_tool") or ""),
                "rewritten_tool": str(event.get("rewritten_tool") or ""),
                "blocked": bool(event.get("blocked")),
            }
            rec.record_event(
                new_trace_event(
                    trace_id=trace_id,
                    event_type=TraceEventType.EXECUTION,
                    payload=payload,
                )
            )
        except Exception:
            logger.debug("Executor: failed to emit plan_tool_alignment trace event", exc_info=True)

    async def execute_plan(
        self,
        *,
        goal: Any,
        plan: Any,
        context: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Execute a PlannerResult-like `plan`.
        """
        self.step_contract_guard.reset()
        records: List[StepExecutionRecord] = []
        overall_success = True
        direct_response_sent = False

        steps = []
        if isinstance(plan, dict):
            steps = plan.get("steps", [])
        elif hasattr(plan, "steps"):
            steps = plan.steps
        elif isinstance(plan, list):
            steps = plan

        resume_from_step_index = int(context.get("resume_from_step_index") or 0)
        if resume_from_step_index < 0:
            resume_from_step_index = 0

        for idx, step in enumerate(steps):
            if idx < resume_from_step_index:
                continue
            if hasattr(step, "to_dict"):
                step_dict = step.to_dict()
            elif isinstance(step, dict):
                step_dict = step
            else:
                step_dict = {"description": str(step)}

            rec = await self._execute_step(step=step_dict, goal=goal, context=context)
            records.append(rec)
            if rec.direct_response_sent:
                direct_response_sent = True
            if not rec.success:
                overall_success = False

        return {
            "success": overall_success,
            "direct_response_sent": direct_response_sent,
            "steps": [r.to_dict() for r in records],
            "meta": {"resume_from_step_index": resume_from_step_index, "executed_steps": len(records)},
        }

    async def _execute_step(
        self,
        *,
        step: Dict[str, Any],
        goal: Any,
        context: Dict[str, Any],
    ) -> StepExecutionRecord:
        desc = step.get("description") or ""
        step_id = step.get("step_id") or "step"
        skill_id = step.get("skill_id")
        step_tool_intent = step.get("tool_intent") if isinstance(step.get("tool_intent"), dict) else {}
        expected_tool = str(step_tool_intent.get("expected_tool") or "").strip().lower()
        fallback_families = [
            str(x).strip().lower()
            for x in (step_tool_intent.get("allowed_fallback_families") or [])
            if str(x).strip()
        ]
        fingerprint = step.get("fingerprint")
        target_file = step.get("target_file") or step.get("args", {}).get("path") or step.get("args", {}).get("file")

        # P4-A: Idempotency check
        if fingerprint and self.idempotency_gate.check(fingerprint, target_file):
            logger.info("Executor: step %s skipped due to idempotent_hit", step_id)
            return StepExecutionRecord(
                step_id=step_id,
                description=desc,
                skill_id=skill_id,
                executor_mode="noop",
                success=True,
                result={"status": "skipped", "idempotent_hit": True}
            )

        # P4-A: Step Contract check
        # We need a PlanStep-like object for the guard
        from quentin.planning.hierarchical_planner import PlanStep
        mock_step = PlanStep(
            step_id=step_id,
            description=desc,
            kind="skill" if skill_id else "llm_call",
            name=skill_id or "fallback_llm",
            args=step.get("args") or {},
        )
        if not self.step_contract_guard.verify_step(mock_step):
             raise RuntimeError(f"Step {step_id} violated step contract: mutation without prior observation.")

        from quentin.infra.concurrency.cancellation import CancellationToken
        cancel_token = context.get("cancel_token")
        if isinstance(cancel_token, CancellationToken):
            cancel_token.raise_if_cancelled()

        rec = StepExecutionRecord(
            step_id=step_id,
            description=desc,
            skill_id=skill_id,
            executor_mode="noop",
            success=False,
        )
        rec.started_at = now_utc_iso()

        step_context = dict(context or {})
        step_context["current_step_description"] = str(desc or "")
        step_context["current_step_id"] = str(step_id or "")
        step_context["current_step_tool_intent"] = {
            "expected_tool": expected_tool,
            "allowed_fallback_families": fallback_families,
        }

        # P5: Surgery Twenty - Pre-action Physical Snapshot
        modifying_tools = {"fs.write_file", "fs.search_replace", "edit", "write", "patch"}
        tool_name_in_step = step.get("name", "")
        pre_hash = None
        if tool_name_in_step in modifying_tools and target_file:
            pre_hash = self.idempotency_gate.get_file_hash(self.repo_root / target_file)

        # P5: Surgery Sixty-six - Global FS Side-effect Guard (OpenClaw Parity)
        from quentin.utils.env_scanner import EnvironmentScanner
        scanner = EnvironmentScanner(self.repo_root)
        pre_step_fingerprint = scanner.get_workspace_fingerprint()

        if skill_id:
            logger.info("Executor: step %s suggests skill_id=%s", step_id, skill_id)
            ok = self._try_execute_skill(step=step, goal=goal, context=step_context, record=rec)
            if ok:
                rec.executor_mode = "skill"
                # (Post-check logic after skill execution)
            else:
                logger.warning("Executor: skill %s failed, fallback to LLM for step %s", skill_id, step_id)

        if not getattr(rec, "executor_mode", None) == "skill":
            await self._fallback_llm_execute(step=step, goal=goal, context=step_context, record=rec)
        
        # P5: Surgery Sixty-six - Side-effect Assertion
        post_step_fingerprint = scanner.get_workspace_fingerprint()
        if pre_step_fingerprint != post_step_fingerprint:
            logger.info("Executor: Physical environment drifted. Verifying intent...")
            
        # P5: Surgery Ninety-nine - Physical Contract Verification (OpenClaw Parity)
        expected_state = step.get("expected_state")
        if expected_state:
            from quentin.cognitive.contract_engine import ContractEngine
            ok, errors = ContractEngine.verify_contract(expected_state, self.repo_root)
            if not ok:
                logger.error(f"Executor: PHYSICAL CONTRACT VIOLATION: {errors}")
                rec.success = False
                rec.error = f"contract_violation: {'; '.join(errors)}"
                if isinstance(rec.result, dict):
                    rec.result["status"] = "error"
                    rec.result["error"] = "Physical state does not match expectations."
                    rec.result["hint"] = f"After this step, I expected: {errors}. Please fix your previous action."
                return rec

        # P5: Surgery Twenty - Post-action Physical Assertion
        if pre_hash is not None and target_file and rec.success:
            post_hash = self.idempotency_gate.get_file_hash(self.repo_root / target_file)
            # Check if it was explicitly skipped by the tool itself
            is_skipped = False
            if isinstance(rec.result, dict):
                is_skipped = rec.result.get("skipped") or "unchanged" in str(rec.result.get("result", "")).lower()
            
            if pre_hash == post_hash and not is_skipped:
                logger.error(f"Executor: Physical Assertion Failed for {target_file}. Content did not change.")
                rec.success = False
                rec.error = "physical_assertion_failed: no_content_change"
                # Inject a sharp correction hint for the next turn
                if isinstance(rec.result, dict):
                    rec.result["status"] = "error"
                    rec.result["error"] = "Physical state did not change."
                    rec.result["hint"] = f"You claimed to modify '{target_file}', but the file content remains identical. Check if your 'oldText' matches the file EXACTLY, or use 'ls' to check if the file exists."

        # P5: Surgery Fifty-nine - Turn-level Budget Guard (OpenClaw Parity)
        from quentin.infra.llm.budget_guard import BudgetGuard
        guard = BudgetGuard()
        
        raw_result_str = str(rec.result.get("result", "")) if isinstance(rec.result, dict) else str(rec.result)
        
        is_allowed, reason = guard.check_result_payload(raw_result_str)
        if not is_allowed:
            logger.warning(f"Executor: {reason}. FORCING EXTREME TRUNCATION.")
            # If rejected by budget, we force SmartTruncator to be very aggressive (e.g. 2000 chars)
            from quentin.infra.text.smart_truncator import SmartTruncator
            rec.actions_summary = SmartTruncator.truncate(raw_result_str, max_chars=2000)
            if isinstance(rec.result, dict):
                rec.result["status"] = "error"
                rec.result["error"] = "turn_budget_exceeded"
                rec.result["hint"] = f"The output was too large ({len(raw_result_str)} chars). {reason} Use 'grep' or 'tail' to read smaller parts."
                rec.result["result"] = rec.actions_summary
            rec.success = False
            rec.finished_at = now_utc_iso()
            return rec

        # P5: Surgery Thirty-seven - Structure-aware Truncation
        # (Existing truncation continues if within budget)
        from quentin.infra.text.smart_truncator import SmartTruncator
        
        # 1. Prepare raw string for record
        raw_result_str = str(rec.result.get("result", "")) if isinstance(rec.result, dict) else str(rec.result)
        
        # 2. Perform intelligent truncation
        max_tool_chars = int(os.getenv("QUENTIN_MAX_TOOL_OUTPUT_CHARS", "12000"))
        rec.actions_summary = SmartTruncator.truncate(raw_result_str, max_chars=max_tool_chars)
        
        # 3. Reflect back into the result object if it's a dictionary
        if isinstance(rec.result, dict) and len(raw_result_str) > max_tool_chars:
            rec.result["result"] = rec.actions_summary
            rec.result["truncated"] = True
            rec.result["original_length"] = len(raw_result_str)

        rec.finished_at = now_utc_iso()
        
        # P4-A: Mark success for idempotency
        if rec.success and fingerprint:
            self.idempotency_gate.mark_success(fingerprint, target_file)
            
        return rec

    def _try_execute_skill(
        self,
        *,
        step: Dict[str, Any],
        goal: Any,
        context: Dict[str, Any],
        record: StepExecutionRecord,
    ) -> bool:
        skill_id = record.skill_id
        if not skill_id:
            return False

        # 1) Executable skill plugins (drop-in, directory-based).
        try:
            fn, plugin = self.skill_manager.load_exec_skill_callable(skill_id)
        except Exception:
            fn, plugin = None, None
        if fn is not None:
            goal_dict: Dict[str, Any] = self._goal_to_dict(goal)
            try:
                result = fn(step, goal_dict, context or {})
            except Exception as e:  # noqa: BLE001
                logger.exception("Executor._try_execute_skill: exec-skill plugin %s raised exception", skill_id)
                record.error = f"exec_skill_runtime_error: {e}"
                return False
            record.result = result
            if isinstance(result, dict):
                status = result.get("status", "ok")
                if status == "ok":
                    record.success = True
                    return True
                record.error = f"exec_skill_status={status}"
                return False
            record.success = True
            return True

        # 2) Registry-backed python skills (legacy path).
        try:
            sk: Optional[SkillSpec] = self.skill_manager.registry.get(skill_id)  # type: ignore[attr-defined]
        except Exception:
            record.error = "skill_registry_error"
            return False

        if sk is None:
            record.error = "skill_not_found"
            return False
        if not (sk.is_active or sk.is_implemented):
            record.error = f"skill_not_ready(status={sk.status}, implemented={sk.is_implemented})"
            return False
        if not sk.implementation_module or not sk.implementation_symbol:
            record.error = "skill_not_implemented"
            return False

        try:
            module = importlib.import_module(sk.implementation_module)
            func = getattr(module, sk.implementation_symbol)
        except Exception as e:  # noqa: BLE001
            logger.exception("Executor._try_execute_skill: import/attr error for %s", skill_id)
            record.error = f"import_error: {e}"
            return False

        goal_dict: Dict[str, Any] = self._goal_to_dict(goal)

        try:
            result = func(step, goal_dict, context or {})
        except Exception as e:  # noqa: BLE001
            logger.exception("Executor._try_execute_skill: skill %s raised exception", skill_id)
            record.error = f"runtime_error: {e}"
            return False

        if isinstance(result, dict):
            status = result.get("status", "ok")
            record.result = result
            if status == "ok":
                record.success = True
                return True
            record.error = f"skill_status={status}"
            return False

        record.result = result
        record.success = True
        return True

    async def _execute_via_protocols(
        self,
        *,
        cfg: Any,
        system_prompt: str,
        user_prompt: str,
        tools: List[Dict[str, Any]],
        context: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        registry = get_tool_call_protocol_registry()
        provider = getattr(cfg, "provider", None) or ""
        model_name = getattr(cfg, "name", None) or getattr(cfg, "model", None) or ""

        candidates = [
            p for p in registry.list_protocols()
            if p.supports(provider=provider, model_name=model_name, config=cfg)
        ]
        if not candidates:
            return None

        tried: List[str] = []
        last_error_payload: Optional[Dict[str, Any]] = None

        for protocol in candidates:
            tried.append(protocol.id)
            decision: ProtocolDecision = await protocol.next_action(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                tools=tools,
                config=cfg,
                context=context,
            )

            # On protocol error, continue trying lower-priority protocols.
            if decision.kind == "error":
                last_error_payload = {
                    "status": "error",
                    "error": decision.error or "protocol_error",
                    "result": decision.content,
                    "meta": {**decision.meta, "protocol": protocol.id, "protocol_chain": list(tried)},
                }
                continue

            if decision.kind == "tool_call":
                return {
                    "status": "ok",
                    "call_tool": decision.tool_calls[0] if decision.tool_calls else None,
                    "tool_calls": decision.tool_calls,
                    "result": decision.content,
                    "meta": {**decision.meta, "protocol": protocol.id, "protocol_chain": list(tried)},
                }

            # Final answer
            return {
                "status": "ok",
                "result": decision.content,
                "meta": {**decision.meta, "protocol": protocol.id, "protocol_chain": list(tried)},
            }

        return last_error_payload

    @staticmethod
    def _robust_json_parse(text: str) -> Dict[str, Any]:
        """
        Forcefully extract and parse JSON from messy LLM output.
        Handles markdown blocks and minor syntax errors.
        """
        s = text.strip()
        # Clean markdown markers
        if s.startswith("```"):
            s = re.sub(r"^```(json)?", "", s, flags=re.IGNORECASE)
            s = re.sub(r"```$", "", s).strip()

        # 1. Try simple parse
        try:
            return json.loads(s)
        except:
            pass
            
        # 2. Extract first { to last }
        start = s.find("{")
        end = s.rfind("}")
        if start != -1 and end != -1:
            s = s[start : end + 1]
            
        # 3. Handle unescaped backslashes in content (common in Python code strings)
        # This is a dangerous but necessary heuristic for small models
        try:
            return json.loads(s)
        except json.JSONDecodeError as je:
            # If it's a backslash error, try double-escaping them
            if "Invalid \\escape" in str(je):
                # Double escape only backslashes that aren't already part of a valid sequence
                # (Simplified: double all backslashes and fix later)
                s_fixed = s.replace("\\", "\\\\")
                # But fix the double-double quote problem if the model correctly escaped it
                s_fixed = s_fixed.replace('\\\\"', '\\"') 
                try:
                    return json.loads(s_fixed)
                except: pass

        # 4. Final attempt: Remove trailing commas
        s = re.sub(r",\s*([\]\}])", r"\1", s)
        try:
            return json.loads(s)
        except Exception as e:
            logger.warning(f"Robust parse failed: {e}. Raw text: {text[:200]}...")
            return {"status": "error", "error": "parse_failure", "raw": text}

    @staticmethod
    def _safe_json_dump(obj: Any, **kwargs) -> str:
        """
        Safe JSON dump that handles non-serializable objects.
        """
        def _preview_text(s: str, *, head: int = 800, tail: int = 300) -> str:
            if not isinstance(s, str):
                return str(s)
            if len(s) <= head + tail + 40:
                return s
            return f"{s[:head]}\n...[{len(s)} chars]...\n{s[-tail:]}"

        def _compact_tool_call_result_dict(d: Dict[str, Any]) -> Dict[str, Any]:
            out: Dict[str, Any] = {
                "tool_name": d.get("tool_name"),
                "success": bool(d.get("success")),
            }
            if d.get("error"):
                out["error"] = d.get("error")

            output = d.get("output") if isinstance(d.get("output"), dict) else {}
            if output:
                compact_out: Dict[str, Any] = {}
                for k in ("status", "error", "hint", "result", "cached", "cache_stale"):
                    if k in output:
                        v = output.get(k)
                        compact_out[k] = _preview_text(v) if isinstance(v, str) else v
                na = output.get("next_actions")
                if isinstance(na, list):
                    compact_out["next_actions"] = [str(x)[:200] for x in na[:4]]
                if "content" in output and "content_preview" not in compact_out:
                    compact_out["content_preview"] = _preview_text(str(output.get("content") or ""))
                if "_untrusted_wrapped_text" in output:
                    compact_out["_untrusted_wrapped_text_preview"] = _preview_text(
                        str(output.get("_untrusted_wrapped_text") or "")
                    )
                if compact_out:
                    out["output"] = compact_out

            meta = d.get("meta") if isinstance(d.get("meta"), dict) else {}
            if meta:
                keep: Dict[str, Any] = {}
                for k in ("action_id", "untrusted_output_wrapped", "plugin_id", "plugin_dir", "manifest_path"):
                    if k in meta:
                        keep[k] = meta.get(k)
                if keep:
                    out["meta"] = keep
            return out

        def _default(o):  # type: ignore[no-untyped-def]
            if hasattr(o, "to_dict"):
                return o.to_dict()
            try:
                from pydantic import BaseModel  # type: ignore

                if isinstance(o, BaseModel):
                    d = o.model_dump() if hasattr(o, "model_dump") else o.dict()  # type: ignore[attr-defined]
                    if o.__class__.__name__ == "ToolCallResult" and isinstance(d, dict):
                        return _compact_tool_call_result_dict(d)
                    return d
            except Exception:
                pass
            if hasattr(o, "__dict__"):
                return f"<{o.__class__.__name__}>"
            from datetime import datetime

            if isinstance(o, datetime):
                return o.isoformat()
            return str(o)

        kwargs.setdefault("ensure_ascii", False)
        kwargs.setdefault("default", _default)
        dumped = json.dumps(obj, **kwargs)
        return truncate_json_text(dumped, max_chars=12000)

    @staticmethod
    def _strip_thinking_tags(text: str) -> str:
        """
        P5: Microscope Port of OpenClaw's code-aware stripper.
        Ensures that <think> tags appearing inside code blocks are preserved.
        """
        if not text:
            return text
        text = enforce_closed_tag_blocks(text, tags=("final", "think"))
            
        detector = MarkdownCodeDetector()
        detector.build_index(text)

        # 1. Handle <final> protocol (Outside code blocks ONLY)
        final_pattern = re.compile(r"<final\b[^>]*>([\s\S]*?)</final>", re.IGNORECASE)
        for m in reversed(list(final_pattern.finditer(text))):
            if not detector.is_inside_code(m.start()):
                # Found a valid <final> block outside code.
                return m.group(1).strip()

        # 2. Sequential Stripping (Non-destructive)
        # We process tags one by one and check their position
        tag_pattern = re.compile(r"<(/?(?:think(?:ing)?|thought|antthinking|final))\b[^>]*>", re.IGNORECASE)
        
        result = []
        last_idx = 0
        in_thinking_block = False
        think_block_start = -1

        for m in tag_pattern.finditer(text):
            idx = m.start()
            if detector.is_inside_code(idx):
                # This tag is part of code, keep it as text
                continue
            
            # Tag is outside code, process it
            tag_name = m.group(1).lower()
            
            if not in_thinking_block:
                if not tag_name.startswith("/"): # Opening tag
                    # Append everything before the tag
                    result.append(text[last_idx:idx])
                    in_thinking_block = True
                    think_block_start = idx
                else:
                    # Stray closing tag, ignore
                    result.append(text[last_idx:idx])
            else:
                if tag_name.startswith("/"): # Closing tag
                    # End of thinking block, just update last_idx to skip the content
                    in_thinking_block = False
                    think_block_start = -1
                else:
                    # Nested opening tag? Treat as content of current thinking block (ignore)
                    pass
            
            last_idx = m.end()

        if not in_thinking_block:
            result.append(text[last_idx:])
        
        return "".join(result).strip()

    @staticmethod
    def _extract_directives(text: str) -> Dict[str, str]:
        """
        P5: Ported from OpenClaw's reply-directives.ts.
        Extracts [[key:value]] directives from model output.
        """
        if not text:
            return {}
        from quentin.runtime.stream_protocol import extract_reply_directives

        parsed, _cleaned = extract_reply_directives(text)
        return dict(parsed.raw or {})

    async def _fallback_llm_execute(
        self,
        *,
        step: Dict[str, Any],
        goal: Any,
        context: Dict[str, Any],
        record: StepExecutionRecord,
    ) -> None:
        record.executor_mode = "llm"

        domain = getattr(goal, "domain", None) or "core"
        cfg = self.model_router.route(mode="executor", task_type=domain)

        def sanitize(obj):
            if isinstance(obj, dict):
                return {k: sanitize(v) for k, v in obj.items()}
            if isinstance(obj, list):
                return [sanitize(i) for i in obj]
            if isinstance(obj, (str, int, float, bool, type(None))):
                return obj
            try:
                from pydantic import BaseModel  # type: ignore

                if isinstance(obj, BaseModel):
                    d = obj.model_dump() if hasattr(obj, "model_dump") else obj.dict()  # type: ignore[attr-defined]
                    return sanitize(d)
            except Exception:
                pass
            if hasattr(obj, "to_dict"):
                try: return sanitize(obj.to_dict())
                except: pass
            if hasattr(obj, "__dict__"):
                return f"<{obj.__class__.__name__}>"
            return str(obj)

        safe_context = sanitize(context)
        # Explicitly remove cancel_token as it's handled separately
        if isinstance(safe_context, dict):
            safe_context.pop("cancel_token", None)
        payload_base = {"step": step, "goal": self._goal_to_dict(goal), "context": safe_context}
        desc = str(step.get("description") or "")
        step_tool_intent = step.get("tool_intent") if isinstance(step.get("tool_intent"), dict) else {}
        expected_tool = str(step_tool_intent.get("expected_tool") or "").strip().lower()
        fallback_families = [
            str(x).strip().lower()
            for x in (step_tool_intent.get("allowed_fallback_families") or [])
            if str(x).strip()
        ]
        narration_mode = self._resolve_narration_mode(step=step, context=context)
        tool_summary_block = self._build_tool_summary_block()
        tool_knowledge_block = self._build_tool_knowledge_block()
        canvas_description = self.virtual_canvas.render_text_description()

        base_system_prompt = (
            "You are the HARDCORE EXECUTION AGENT in a self-improving system.\n"
            "THINKING PROTOCOL (CRITICAL):\n"
            "1. Before any tool call or final response, you MUST output an internal monologue inside <think> tags.\n"
            "2. In your <think> block, analyze: a) Current state vs goal, b) Potential risks, c) Expected tool outcome.\n"
            "3. After </think>, output your JSON payload. Your JSON response should be wrapped in <final> tags if possible.\n"
            "\n"
            "CRITICAL RULES:\n"
            "1. ONLY PERFORM ACTIONS by calling real tools. DO NOT simulate or narrate actions.\n"
            "2. DO NOT say 'I have saved the file' unless you just received a successful response from 'fs.write_file'.\n"
            "3. If a file is missing, use 'ls' or 'shell.run_command' to find it. DO NOT guess paths.\n"
            "4. NEVER output raw text/prose. Use tool calls for actions; when the goal is achieved, set call_tool to null and finish.\n"
            "5. If you cannot proceed, set status to 'error' and explain exactly which tool output is blocking you.\n"
            "6. Never use interactive editors like nano/vim; use fs.read_file + fs.search_replace/fs.write_file.\n"
            "7. Never use guessed download/install URLs; verify official sources or use a package manager.\n"
            "\n"
            f"{canvas_description}\n\n"
            "Your output MUST be a strict JSON object:\n"
            "{\n"
            '  "status": "ok" | "error",\n'
            '  "result": "technical summary of LAST tool output",\n'
            '  "call_tool": {"tool_name": "...", "args": {...}} | null\n'
            "}\n"
            f"\n{tool_summary_block}\n"
            + (f"\n{tool_knowledge_block}\n" if tool_knowledge_block else "")
        )
        hint_lines: List[str] = []
        hint_lines.append(f"NARRATION MODE: {narration_mode}")
        if narration_mode == "minimal":
            hint_lines.append("Default behavior: do not narrate routine, low-risk tool calls.")
        try:
            from quentin.kernel.path_guard import PathGuard

            allowed = PathGuard(self.repo_root).allowed_roots
            if allowed:
                hint_lines.append(
                    "WRITE POLICY: You may only write under allowed roots: "
                    + ", ".join([f"{p}/" for p in allowed])
                )
        except Exception:
            pass
        forbidden_actions = context.get("forbidden_actions")
        if isinstance(forbidden_actions, list) and forbidden_actions:
            hint_lines.append(
                "FORBIDDEN ACTIONS (from recent guard feedback): "
                + ", ".join([str(x) for x in forbidden_actions[:8]])
                + ". Never call these unless explicitly required by user."
            )
        if bool(context.get("progressive_pressure")):
            pressure_note = str(
                context.get("progressive_pressure_note")
                or "You have performed multiple tool calls. Provide a brief progress update before continuing."
            ).strip()
            if pressure_note:
                hint_lines.append("PROGRESS PRESSURE:\n" + pressure_note)
        self_awareness_note = str(context.get("self_awareness_note") or "").strip()
        if self_awareness_note:
            hint_lines.append("SELF AWARENESS:\n" + self_awareness_note)
        strict_reasons = context.get("strict_reasons")
        if isinstance(strict_reasons, list) and strict_reasons:
            vals = [str(x).strip() for x in strict_reasons if str(x).strip()]
            if vals:
                hint_lines.append(
                    "INTELLIGENCE STRICT REASONS:\n"
                    + ", ".join(vals[:8])
                    + "\nPrioritize discovery, avoid repeated blocked actions, and use low-risk incremental steps."
                )
        if expected_tool:
            hint_lines.append(
                "STEP TOOL INTENT:\n"
                + f"- expected_tool={expected_tool}\n"
                + (
                    "- allowed_fallback_families=" + ",".join(fallback_families)
                    if fallback_families
                    else "- allowed_fallback_families=<none>"
                )
            )
        
        # P1-E: Context Snapshots
        snapshot_text = ""
        if self._is_context_snapshots_enabled:
            registry = get_context_snapshot_registry()
            # Include tool summaries for ToolInventorySnapshotProvider
            snap_ctx = {**context, "tool_summaries": self._build_tool_summaries()}
            blocks = registry.collect_all(repo_root=self.repo_root, context=snap_ctx)
            if blocks:
                snapshot_lines = ["\nRUNTIME SNAPSHOT:"]
                for b in blocks:
                    snapshot_lines.append(f"--- {b.title} ---\n{b.content}")
                snapshot_text = "\n".join(snapshot_lines)

        system_prompt = build_layered_system_prompt(
            base_system=base_system_prompt + snapshot_text,
            soul=str(context.get("soul_prompt") or ""),
            skill=str(context.get("skill_prompt") or ""),
            project_context=str(context.get("project_context_prompt") or ""),
            hints=hint_lines,
        )

        try:
            from quentin.infra.concurrency.cancellation import CancellationToken
            from quentin.config.dynamic_manager import get_dynamic_config
            
            cancel_token = context.get("cancel_token")
            dynamic_cfg = get_dynamic_config(repo_root=self.repo_root)
            
            max_step_iterations = int(dynamic_cfg.get("max_step_iterations", context.get("max_step_iterations", 6)))
            no_progress_threshold = int(dynamic_cfg.get("no_progress_threshold", context.get("no_progress_threshold", 2)))
            
            if no_progress_threshold < 1:
                no_progress_threshold = 1
            feedback: List[Dict[str, Any]] = []
            step_deltas: List[Dict[str, Any]] = []
            no_progress_streak = 0
            repeated_tool_signature = ""
            repeated_tool_count = 0
            native_enabled = self._native_tool_calling_enabled(cfg=cfg, context=context)
            if self._native_tool_calling_disabled_reason:
                native_enabled = False

            for iteration in range(1, max_step_iterations + 1):
                if isinstance(cancel_token, CancellationToken):
                    cancel_token.raise_if_cancelled()

                # Fast lane: compile obvious filesystem/shell steps deterministically (no LLM needed).
                # This is a major reliability win for small local models that sometimes refuse tool-calls.
                if iteration == 1:
                    fast_tool = self._infer_fast_tool_call_from_description(desc)
                    if fast_tool:
                        fast_tool, align_event = self._align_tool_call_with_step_intent(
                            desc=desc,
                            tool_call=fast_tool,
                            iteration=iteration,
                            expected_tool=expected_tool,
                            allowed_fallback_families=fallback_families,
                        )
                        if isinstance(align_event, dict):
                            blocked = bool(align_event.get("blocked"))
                            self._emit_alignment_trace_event(
                                context=context,
                                step_id=str(record.step_id or ""),
                                iteration=int(iteration or 0),
                                event=align_event,
                            )
                            feedback.append(
                                {
                                    "iteration": iteration,
                                    **align_event,
                                    "tool_call": fast_tool,
                                }
                            )
                            if blocked:
                                fast_tool = None
                        if fast_tool:
                            tool_res = await self._execute_tool_call(tool_call=fast_tool, context=context)
                            record.result = {
                                "status": "ok" if (hasattr(tool_res, "success") and bool(tool_res.success)) else "error",
                                "result": "fast_path_tool_call",
                                "tool_calls": [fast_tool],
                                "tool_result": tool_res,
                                "meta": {"fast_path": True, "tool_call_mode": "compiled"},
                            }
                            record.success = bool(getattr(tool_res, "success", False))
                            return

                payload = {**payload_base, "feedback": feedback[-6:], "iteration": iteration}
                user_prompt = self._safe_json_dump(payload, indent=2)
                parsed: Optional[Dict[str, Any]] = None

                # P1-D: Protocol-based execution (new path)
                if self._is_protocol_registry_enabled:
                    print(f"\n[Executor] Iteration {iteration}: Selecting protocols...", flush=True)
                    relevant_tools = await self._get_relevant_tool_specs(desc)
                    
                    # Populate context for protocols
                    proto_ctx = {
                        **context,
                        "iteration": iteration,
                        "current_step_id": record.step_id,
                        "domain": domain,
                    }
                    print(f"[Executor] Calling protocols with {len(relevant_tools)} tools...", flush=True)
                    # P5: CONTEXT GUARD (The "Brain Safety Valve")
                    from quentin.infra.llm.context_guard import ContextGuard
                    guard = ContextGuard()
                    
                    # Construct messages to check size
                    check_msgs = [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}]
                    status = guard.check(check_msgs)
                    
                    if status["action"] == "compact":
                        # Naive compaction
                        print("[ContextGuard]: Compacting prompt due to high usage...", flush=True)
                        user_prompt = user_prompt[:1000] + "\n...[Compacted]...\n" + user_prompt[-3000:]
                    elif status["action"] == "fail":
                        # Hard fail
                        raise RuntimeError(f"Context Overflow: Estimated {status['usage']} tokens exceeds limit.")

                    parsed = await self._execute_via_protocols(
                        cfg=cfg,
                        system_prompt=system_prompt,
                        user_prompt=user_prompt,
                        tools=relevant_tools,
                        context=proto_ctx,
                    )
                    print(f"[Executor] Protocols returned. Success: {bool(parsed)}", flush=True)
                    
                    if parsed:
                        # P5: CONSOLE LOG
                        print(f"\n[Brain Payload]: {json.dumps(parsed, indent=2, ensure_ascii=False)}", flush=True)
                        
                        # P5: PERSISTENT LOG (data/executor_debug.jsonl)
                        try:
                            from quentin.utils.time import now_utc_iso
                            debug_path = self.repo_root / "data" / "executor_debug.jsonl"
                            debug_path.parent.mkdir(parents=True, exist_ok=True)
                            with open(debug_path, "a", encoding="utf-8") as df:
                                entry = {
                                    "ts": now_utc_iso(),
                                    "step": record.step_id,
                                    "iter": iteration,
                                    "payload": parsed
                                }
                                df.write(json.dumps(entry, ensure_ascii=False) + "\n")
                        except Exception: pass
                    
                    if parsed and parsed.get("tool_calls"):
                        # P5: Visibility
                        print(f"\n[Brain]: Executing {len(parsed['tool_calls'])} tools...", flush=True)
                        tool_calls = parsed["tool_calls"]
                        executed_tool = False
                        for tool_call in tool_calls[:2]:
                            tool_call, align_event = self._align_tool_call_with_step_intent(
                                desc=desc,
                                tool_call=tool_call,
                                iteration=iteration,
                                expected_tool=expected_tool,
                                allowed_fallback_families=fallback_families,
                            )
                            if isinstance(align_event, dict):
                                blocked = bool(align_event.get("blocked"))
                                self._emit_alignment_trace_event(
                                    context=context,
                                    step_id=str(record.step_id or ""),
                                    iteration=int(iteration or 0),
                                    event=align_event,
                                )
                                feedback.append(
                                    {
                                        "iteration": iteration,
                                        **align_event,
                                        "tool_call": tool_call,
                                    }
                                )
                                if blocked:
                                    continue
                            if self._should_enforce_coding_tool(desc=desc, tool_call=tool_call, iteration=iteration):
                                feedback.append(
                                    {
                                        "iteration": iteration,
                                        "type": "strategy_guard",
                                        "reason": "plan_execution_misalignment",
                                        "hint": self._build_coding_tool_guard_hint(),
                                        "blocked_tool_call": tool_call,
                                    }
                                )
                                continue
                            signature = self._safe_json_dump(tool_call, sort_keys=True)
                            if signature == repeated_tool_signature:
                                repeated_tool_count += 1
                            else:
                                repeated_tool_signature = signature
                                repeated_tool_count = 1

                            repeat_limit = self._repeat_limit_for_tool_call(tool_call)
                            if repeated_tool_count >= repeat_limit:
                                hint = self._build_dead_loop_hint()
                                diagnostics = self._dead_loop_diagnostic_probes()
                                parsed = {
                                    "status": "error",
                                    "error": "repeated_tool_call_loop",
                                    "call_tool": tool_call,
                                    "hint": hint,
                                    "meta": {
                                        "iteration": iteration,
                                        "protocol": parsed.get("meta", {}).get("protocol"),
                                        "repeat_limit": repeat_limit,
                                        "diagnostic_probes": diagnostics,
                                    },
                                }
                                # P5: Inject pain into cognitive loop
                                feedback.append({
                                    "iteration": iteration, 
                                    "type": "emergency_hint", 
                                    "hint": hint,
                                    "tool_call": tool_call,
                                    "diagnostic_probes": diagnostics,
                                })
                                executed_tool = False
                                break
                                
                            tool_res = await self._execute_tool_call(tool_call=tool_call, context=context)

                            # P5: OpenClaw Parity - Inline Feedback / Reactive Planning
                            # If a tool fails, we don't just report it; we guide the model to pivot.
                            if hasattr(tool_res, "success") and not tool_res.success:
                                err_msg = str(getattr(tool_res, "error", "unknown error")).lower()
                                reactive_hint = ""
                                if "not found" in err_msg or "no such file" in err_msg:
                                    reactive_hint = "CRITICAL: Target not found. Do NOT retry the same path. Use 'ls' or 'find' to discover the correct location before proceeding."
                                elif "permission" in err_msg or "denied" in err_msg:
                                    reactive_hint = "CRITICAL: Permission denied. Try an alternative directory (e.g. 'mutable/') or check 'ls -l' for ownership."
                                else:
                                    tax = classify_error_taxonomy(err_msg)
                                    reactive_hint = f"{tax.hint} [error_kind={tax.kind} reflection_weight={tax.reflection_weight}]"
                                
                                if reactive_hint:
                                    feedback.append({
                                        "iteration": iteration,
                                        "type": "reactive_guidance",
                                        "hint": reactive_hint,
                                        "error": err_msg
                                    })

                            # P5: OpenClaw Parity - Tool Display Summary
                            disp = resolve_tool_display(tool_call.get("tool_name", "tool"), tool_call.get("args"))
                            record.summary = format_tool_summary(disp)

                            # P5: OpenClaw Parity - Messaging Tool Suppression
                            if hasattr(tool_res, "meta") and tool_res.meta.get("direct_response_sent"):
                                record.direct_response_sent = True

                            # P5: Differentiate Logic Loop from System Error (based on actual tool result)
                            is_transient = False
                            if hasattr(tool_res, "error") and tool_res.error:
                                err_s = str(tool_res.error).lower()
                                if any(k in err_s for k in ("timeout", "connection", "rate limit", "429", "500")):
                                    is_transient = True
                            if is_transient:
                                logger.debug(
                                    "Executor: transient error detected; easing repeated-call counter for %s",
                                    tool_call.get("tool_name"),
                                )
                                repeated_tool_count = max(0, repeated_tool_count - 1)

                            feedback.append({"iteration": iteration, "tool_call": tool_call, "tool_result": tool_res})
                            parsed["tool_result"] = tool_res
                            executed_tool = True
                            if self._should_end_step_after_tool_call(desc=desc, tool_call=tool_call, tool_res=tool_res):
                                record.result = parsed
                                record.success = True
                                return
                        
                        if executed_tool:
                            continue

                # Legacy path (preserved for back-compat or if protocols fail/disabled)
                if parsed is None:
                    if native_enabled and self.tool_manager is not None:
                        try:
                            native_out = call_llm_with_tools(
                                cfg,
                                system_prompt=system_prompt,
                                user_prompt=user_prompt,
                                tools=self._build_native_tool_specs(),
                                actor="executor_native_tools",
                                domain=str(getattr(goal, "domain", "core") or "core"),
                                environment=str(getattr(goal, "environment", "sandbox") or "sandbox"),
                                risk_level="medium",
                                action_metadata={"component": "executor", "step_id": record.step_id, "iteration": iteration},
                                provider=getattr(cfg, "provider", None),
                                model_name=getattr(cfg, "name", None) or getattr(cfg, "model", None),
                                cancel_token=cancel_token if isinstance(cancel_token, CancellationToken) else None,
                            )
                            parsed = self._normalize_native_reply(native_out)
                            tool_calls = parsed.get("tool_calls") if isinstance(parsed.get("tool_calls"), list) else []
                            executed_tool = False
                            for raw_call in tool_calls[:2]:
                                tool_call = self._normalize_native_tool_call(raw_call)
                                if not tool_call:
                                    continue
                                tool_call, align_event = self._align_tool_call_with_step_intent(
                                    desc=desc,
                                    tool_call=tool_call,
                                    iteration=iteration,
                                    expected_tool=expected_tool,
                                    allowed_fallback_families=fallback_families,
                                )
                                if isinstance(align_event, dict):
                                    blocked = bool(align_event.get("blocked"))
                                    self._emit_alignment_trace_event(
                                        context=context,
                                        step_id=str(record.step_id or ""),
                                        iteration=int(iteration or 0),
                                        event=align_event,
                                    )
                                    feedback.append(
                                        {
                                            "iteration": iteration,
                                            **align_event,
                                            "tool_call": tool_call,
                                        }
                                    )
                                    if blocked:
                                        continue
                                if self._should_enforce_coding_tool(desc=desc, tool_call=tool_call, iteration=iteration):
                                    feedback.append(
                                        {
                                            "iteration": iteration,
                                            "type": "strategy_guard",
                                            "reason": "plan_execution_misalignment",
                                            "hint": self._build_coding_tool_guard_hint(),
                                            "blocked_tool_call": tool_call,
                                        }
                                    )
                                    continue
                                signature = self._safe_json_dump(tool_call, sort_keys=True)
                                if signature == repeated_tool_signature:
                                    repeated_tool_count += 1
                                else:
                                    repeated_tool_signature = signature
                                    repeated_tool_count = 1
                                repeat_limit = self._repeat_limit_for_tool_call(tool_call)
                                if repeated_tool_count >= repeat_limit:
                                    hint = self._build_dead_loop_hint()
                                    diagnostics = self._dead_loop_diagnostic_probes()
                                    parsed = {
                                        "status": "error",
                                        "error": "repeated_tool_call_loop",
                                        "call_tool": tool_call,
                                        "hint": hint,
                                        "meta": {
                                            "iteration": iteration,
                                            "tool_call_mode": "native",
                                            "repeat_limit": repeat_limit,
                                            "diagnostic_probes": diagnostics,
                                        },
                                    }
                                    feedback.append({
                                        "iteration": iteration,
                                        "type": "emergency_hint",
                                        "hint": hint,
                                        "tool_call": tool_call,
                                        "diagnostic_probes": diagnostics,
                                    })
                                    executed_tool = False
                                    break
                                tool_res = await self._execute_tool_call(tool_call=tool_call, context=context)
                                
                                # P5: OpenClaw Parity - Tool Display Summary
                                disp = resolve_tool_display(tool_call.get("tool_name", "tool"), tool_call.get("args"))
                                record.summary = format_tool_summary(disp)

                                # P5: OpenClaw Parity - Messaging Tool Suppression
                                if hasattr(tool_res, "meta") and tool_res.meta.get("direct_response_sent"):
                                    record.direct_response_sent = True

                                feedback.append({"iteration": iteration, "tool_call": tool_call, "tool_result": tool_res})
                                parsed["tool_result"] = tool_res
                                executed_tool = True
                            if executed_tool:
                                continue
                        except Exception as native_err:  # noqa: BLE001
                            err_s = str(native_err)
                            if ("400" in err_s and "/api/chat" in err_s) or ("Bad Request" in err_s and "/api/chat" in err_s):
                                self._native_tool_calling_disabled_reason = err_s
                                if not self._native_tool_calling_disable_logged:
                                    logger.warning(
                                        "Executor: disabling native tool-calling for this run (Ollama /api/chat rejected request): %s",
                                        err_s,
                                    )
                                    self._native_tool_calling_disable_logged = True
                            else:
                                logger.warning(
                                    "Executor: native tool-calling failed at step=%s iteration=%s, fallback to JSON mode: %s",
                                    record.step_id,
                                    iteration,
                                    native_err,
                                )
                            parsed = None
                            native_enabled = False

                if parsed is None:
                    out_raw = call_llm(
                        cfg,
                        user_prompt=user_prompt,
                        system_prompt=system_prompt,
                        actor="executor",
                        domain=str(getattr(goal, "domain", "core") or "core"),
                        environment=str(getattr(goal, "environment", "sandbox") or "sandbox"),
                        risk_level="medium",
                        action_metadata={"component": "executor", "step_id": record.step_id, "iteration": iteration},
                        provider=getattr(cfg, "provider", None),
                        model_name=getattr(cfg, "name", None) or getattr(cfg, "model", None),
                        cancel_token=cancel_token if isinstance(cancel_token, CancellationToken) else None,
                    )
                    out_clean = self._strip_thinking_tags(str(out_raw or ""))
                    if not str(out_clean or "").strip():
                        raise RuntimeError("executor_empty_model_output: no visible JSON content after stripping thinking tags")
                    from quentin.llm.ollama_client import OllamaLLMClient
                    parsed = OllamaLLMClient.extract_json(out_clean)
                    
                    # Log format_salvaged if needed
                    if out_clean.strip() != json.dumps(parsed):
                        if isinstance(parsed, dict):
                            parsed.setdefault("meta", {})
                            if isinstance(parsed["meta"], dict):
                                parsed["meta"]["format_salvaged"] = True

                    tool_call = parsed.get("call_tool") if isinstance(parsed, dict) else None
                    if tool_call and self.tool_manager:
                        normalized_call = self._normalize_json_tool_call(tool_call)
                        if normalized_call:
                            normalized_call, align_event = self._align_tool_call_with_step_intent(
                                desc=desc,
                                tool_call=normalized_call,
                                iteration=iteration,
                                expected_tool=expected_tool,
                                allowed_fallback_families=fallback_families,
                            )
                            if isinstance(align_event, dict):
                                blocked = bool(align_event.get("blocked"))
                                self._emit_alignment_trace_event(
                                    context=context,
                                    step_id=str(record.step_id or ""),
                                    iteration=int(iteration or 0),
                                    event=align_event,
                                )
                                feedback.append(
                                    {
                                        "iteration": iteration,
                                        **align_event,
                                        "tool_call": normalized_call,
                                    }
                                )
                                if blocked:
                                    continue
                            if self._should_enforce_coding_tool(desc=desc, tool_call=normalized_call, iteration=iteration):
                                feedback.append(
                                    {
                                        "iteration": iteration,
                                        "type": "strategy_guard",
                                        "reason": "plan_execution_misalignment",
                                        "hint": self._build_coding_tool_guard_hint(),
                                        "blocked_tool_call": normalized_call,
                                    }
                                )
                                continue
                            signature = self._safe_json_dump(normalized_call, sort_keys=True)
                            if signature == repeated_tool_signature:
                                repeated_tool_count += 1
                            else:
                                repeated_tool_signature = signature
                                repeated_tool_count = 1
                            repeat_limit = self._repeat_limit_for_tool_call(normalized_call)
                            if repeated_tool_count >= repeat_limit:
                                hint = self._build_dead_loop_hint()
                                diagnostics = self._dead_loop_diagnostic_probes()
                                parsed = {
                                    "status": "error",
                                    "error": "repeated_tool_call_loop",
                                    "call_tool": normalized_call,
                                    "hint": hint,
                                    "meta": {
                                        "iteration": iteration,
                                        "tool_call_mode": "json_fallback",
                                        "repeat_limit": repeat_limit,
                                        "diagnostic_probes": diagnostics,
                                    },
                                }
                                feedback.append({
                                    "iteration": iteration,
                                    "type": "emergency_hint",
                                    "hint": hint,
                                    "tool_call": normalized_call,
                                    "diagnostic_probes": diagnostics,
                                })
                            else:
                                tool_res = await self._execute_tool_call(tool_call=normalized_call, context=context)
                                
                                # P5: OpenClaw Parity - Tool Display Summary
                                disp = resolve_tool_display(normalized_call.get("tool_name", "tool"), normalized_call.get("args"))
                                record.summary = format_tool_summary(disp)

                                # P5: OpenClaw Parity - Messaging Tool Suppression
                                if hasattr(tool_res, "meta") and tool_res.meta.get("direct_response_sent"):
                                    record.direct_response_sent = True

                                parsed["tool_result"] = tool_res
                                feedback.append(
                                    {"iteration": iteration, "tool_call": normalized_call, "tool_result": tool_res}
                                )
                                # Legacy JSON mode must terminate the step after a successful one-shot tool call.
                                # Otherwise, the loop will repeat the same call until the repeated_tool_call_loop
                                # guard trips (especially for fs.write_file / shell.run_command), masking true success.
                                if self._should_end_step_after_tool_call(desc=desc, tool_call=normalized_call, tool_res=tool_res):
                                    record.result = parsed
                                    record.success = bool(getattr(tool_res, "success", False))
                                    return
                                continue

                if isinstance(parsed, dict):
                    # P5: Reactive Planning - Parse [[directives]] from result text
                    res_text = str(parsed.get("result") or "")
                    if res_text:
                        directives = self._extract_directives(res_text)
                        if directives:
                            logger.info("Executor: Reactive Planning directives found: %s", directives)
                            
                            # P5: Surgery Two - Mid-execution Abort
                            if "abort" in directives or "stop" in directives:
                                session_id = str(context.get("session_id") or "default")
                                logger.warning(f"Executor: Reactive abort triggered for session {session_id}")
                                abort_registry.get_signal(session_id).abort(reason=directives.get("abort") or directives.get("stop"))
                                parsed["status"] = "error"
                                parsed["error"] = "reactive_abort"
                                record.result = parsed
                                record.success = False
                                return

                            # P5: Surgery Ten - Physical Rollback
                            if "rollback" in directives:
                                logger.warning("Executor: Physical rollback triggered via directive.")
                                from quentin.infra.tools.state_manager import PhysicalStateManager
                                sm = PhysicalStateManager(str(self.repo_root))
                                # Use current step_id as fallback snapshot_id
                                if sm.rollback(str(record.step_id)):
                                    feedback.append({
                                        "iteration": iteration,
                                        "type": "rollback_executed",
                                        "hint": "SUCCESS: Workspace rolled back to previous stable state. Re-evaluate your approach."
                                    })
                                    # Continue execution turn with rollback feedback
                                    continue

                            if "narration" in directives:
                                narration_mode = directives["narration"]
                            if "think" in directives or "thinking" in directives:
                                val = directives.get("think") or directives.get("thinking")
                                context["think_level"] = val
                            
                            # Clean up the result text by removing directives
                            cleaned_res = re.sub(r"\[\[.*?\]\]", "", res_text).strip()
                            parsed["result"] = cleaned_res

                    parsed.setdefault("meta", {})
                    if isinstance(parsed["meta"], dict):
                        parsed["meta"]["narration_mode"] = narration_mode
                        parsed["meta"]["iterations"] = iteration
                        parsed["meta"]["tool_feedback_turns"] = len(feedback)
                if isinstance(parsed, dict):
                    step_delta = {
                        "iteration": iteration,
                        "status": str(parsed.get("status") or ""),
                        "has_tool_result": "tool_result" in parsed,
                        "result_preview": str(parsed.get("result") or "")[:120],
                    }
                    step_deltas.append(step_delta)

                # Enforce "tools or nothing": for action-like steps, a plain-text "final" is not progress.
                if (
                    isinstance(parsed, dict)
                    and self._step_requires_tool_call(desc)
                    and (not parsed.get("tool_calls"))
                    and (not parsed.get("call_tool"))
                    and ("tool_result" not in parsed)
                    and (not any(isinstance(x, dict) and ("tool_result" in x) for x in feedback))
                    and iteration < max_step_iterations
                ):
                    feedback.append(
                        {
                            "iteration": iteration,
                            "type": "protocol_violation",
                            "reason": "expected_tool_call",
                            "hint": "You MUST call a real tool now. Do not explain. Return ONLY a tool call payload.",
                            "model_output_preview": str(parsed.get("result") or "")[:240],
                        }
                    )
                    continue

                visible_progress = self._has_visible_progress(parsed)
                if visible_progress:
                    no_progress_streak = 0
                else:
                    no_progress_streak += 1

                is_error_reply = bool(isinstance(parsed, dict) and str(parsed.get("status") or "").lower() == "error")

                if (
                    (not visible_progress)
                    and (not is_error_reply)
                    and no_progress_streak < no_progress_threshold
                    and iteration < max_step_iterations
                ):
                    feedback.append(
                        {
                            "iteration": iteration,
                            "type": "no_progress_retry",
                            "no_progress_streak": no_progress_streak,
                            "step_delta": step_deltas[-1] if step_deltas else {},
                        }
                    )
                    continue

                if no_progress_streak >= no_progress_threshold and not visible_progress:
                    parsed = {
                        "status": "error",
                        "error": "no_progress_threshold_reached",
                        "meta": {
                            "narration_mode": narration_mode,
                            "iterations": iteration,
                            "tool_feedback_turns": len(feedback),
                            "no_progress_streak": no_progress_streak,
                        },
                        "feedback_tail": feedback[-3:],
                        "step_deltas": step_deltas[-6:],
                    }

                if isinstance(parsed, dict):
                    parsed.setdefault("meta", {})
                    if isinstance(parsed["meta"], dict):
                        parsed["meta"]["step_delta_count"] = len(step_deltas)
                    parsed["step_deltas"] = step_deltas[-6:]
                record.result = parsed
                record.success = bool(isinstance(parsed, dict) and parsed.get("status") == "ok")
                return

            record.result = {
                "status": "error",
                "error": "max_step_iterations_reached",
                "meta": {
                    "narration_mode": narration_mode,
                    "iterations": max_step_iterations,
                    "tool_feedback_turns": len(feedback),
                    "no_progress_streak": no_progress_streak,
                },
                "feedback_tail": feedback[-3:],
                "step_deltas": step_deltas[-6:],
            }
            record.success = False
                
        except Exception as e:
            record.error = str(e)
            record.success = False

    @staticmethod
    def _native_tool_calling_enabled(*, cfg: Any, context: Dict[str, Any]) -> bool:
        forced = context.get("native_tool_calling")
        if isinstance(forced, bool):
            return forced
        env = str(context.get("environment") or "sandbox").lower()
        if env != "sandbox":
            return False
        if str(getattr(cfg, "provider", "") or "").lower() != "ollama":
            return False
        return str(os.environ.get("QUENTIN_EXECUTOR_NATIVE_TOOL_CALLING", "1")).lower() in {
            "1",
            "true",
            "yes",
            "on",
        }

    @staticmethod
    def _step_requires_tool_call(desc: str) -> bool:
        """
        Heuristic: most planner steps are action steps and must produce a real tool call.
        Allow "final" answers only for explicit think/summarize/reflection steps.
        """
        d = (desc or "").strip().lower()
        if not d:
            return True
        if any(k in d for k in ("summarize", "总结", "explain", "解释", "reflect", "反思", "plan", "规划", "design", "设计")):
            return False
        return any(
            k in d
            for k in (
                "create",
                "write",
                "run",
                "execute",
                "verify",
                "check",
                "list",
                "read",
                "update",
                "delete",
                "mkdir",
                "touch",
                "生成",
                "创建",
                "写入",
                "执行",
                "验证",
                "检查",
                "读取",
                "更新",
                "删除",
            )
        )

    def _infer_fast_tool_call_from_description(self, desc: str) -> Optional[Dict[str, Any]]:
        """
        Deterministic step compiler for low-risk, high-frequency steps.

        Avoids brittle "LLM -> tool_call" translation failures on small local models.
        """
        d = (desc or "").strip()
        dl = d.lower()

        def _extract_path() -> Optional[str]:
            for pat in (r"'([^']+)'", r"`([^`]+)`", r"\"([^\"]+)\""):
                m = re.search(pat, d)
                if m:
                    candidate = (m.group(1) or "").strip()
                    if candidate and "/" in candidate and " " not in candidate:
                        return candidate
            m = re.search(r"(?P<p>(?:extensions|mutable|generated|quentin|meta_agent)/[a-zA-Z0-9_./-]+)", d)
            if m:
                return (m.group("p") or "").strip()
            return None

        # Health-check commands
        if "gemini --help" in dl:
            return {"tool_name": "shell.run_command", "args": {"command": "gemini --help"}}

        path = _extract_path()

        # File read steps (read-only)
        if path and any(k in dl for k in ("read ", "read the", "读取", "读取文件", "fs.read_file")):
            return {"tool_name": "fs.read_file", "args": {"path": path}}

        # Exact file write steps for deterministic report/materialization tasks.
        if path and "fs.write_file" in dl and any(k in dl for k in ("write", "create", "写入", "创建")):
            content_match = re.search(r"json content\s+(?P<json>\".*\")", d, flags=re.IGNORECASE | re.DOTALL)
            if content_match:
                try:
                    content = json.loads(content_match.group("json"))
                    return {"tool_name": "fs.write_file", "args": {"path": path, "content": str(content)}}
                except Exception:
                    pass

        # Existence checks (read-only)
        if path and any(k in dl for k in ("exists", "exist", "是否存在", "检查是否", "check if")):
            return {"tool_name": "ls", "args": {"path": path}}

        # Directory creation (mutating; restrict to allowed roots)
        if path and any(k in dl for k in ("create the directory", "创建目录", "mkdir", "make directory", "create directory")):
            try:
                from quentin.kernel.path_guard import PathGuard

                PathGuard(self.repo_root).ensure_allowed_path(path)
            except Exception:
                return None
            return {"tool_name": "mkdir", "args": {"path": path}}

        return None

    @staticmethod
    def _should_end_step_after_tool_call(*, desc: str, tool_call: Dict[str, Any], tool_res: Any) -> bool:
        """
        End the current step after a successful observation tool call.

        This prevents local-model dead-loops where the model keeps re-reading the same file
        instead of moving to the next plan step.
        """
        ok = bool(getattr(tool_res, "success", False))
        if not ok:
            return False
        tool_name = str(tool_call.get("tool_name") or "").strip().lower()
        read_only = {"fs.read_file", "fs.exists", "fs.get_write_policy", "ls", "cat", "grep", "pwd"}
        one_shot_mutating = {"fs.write_file", "fs.search_replace", "mkdir", "rm", "mv", "cp"}
        
        if tool_name in read_only or tool_name in one_shot_mutating:
            return True
        # If the step itself is explicitly a "read/check/list", treat a successful tool call as completion.
        dl = (desc or "").lower()
        if any(k in dl for k in ("read", "check", "list", "inspect", "读取", "检查", "列出")):
            return True
        return False

    @staticmethod
    def _build_native_tool_specs() -> List[Dict[str, Any]]:
        """
        Baseline tool definitions for native LLM function calling.
        """
        return [
            {
                "type": "function",
                "function": {
                    "name": "fs.read_file",
                    "description": "Read text file content from the workspace.",
                    "parameters": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]},
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "fs.exists",
                    "description": "Check if a repo-relative file or directory exists.",
                    "parameters": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]},
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "fs.search_replace",
                    "description": "Replace one text snippet in a file safely.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "path": {"type": "string"},
                            "search": {"type": "string"},
                            "replace": {"type": "string"},
                        },
                        "required": ["path", "search", "replace"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "fs.write_file",
                    "description": "Write full content to a file in allowed paths.",
                    "parameters": {
                        "type": "object",
                        "properties": {"path": {"type": "string"}, "content": {"type": "string"}},
                        "required": ["path", "content"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "fs.get_write_policy",
                    "description": "Get writable roots enforced by path policy.",
                    "parameters": {"type": "object", "properties": {}},
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "shell.run_command",
                    "description": "Run a non-interactive shell command.",
                    "parameters": {
                        "type": "object",
                        "properties": {"command": {"type": "string"}},
                        "required": ["command"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "ls",
                    "description": "List directory contents (alias of shell).",
                    "parameters": {"type": "object", "properties": {"path": {"type": "string"}}, "required": []},
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "mkdir",
                    "description": "Create directory (mkdir -p).",
                    "parameters": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]},
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "cat",
                    "description": "Read file contents to stdout (alias of shell).",
                    "parameters": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]},
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "grep",
                    "description": "Search for a pattern in a path (alias of shell).",
                    "parameters": {
                        "type": "object",
                        "properties": {"pattern": {"type": "string"}, "path": {"type": "string"}},
                        "required": ["pattern"],
                    },
                },
            },
        ]

    async def _get_relevant_tool_specs(self, task_description: str) -> List[Dict[str, Any]]:
        """
        P5: Cognitive Filtering (User Suggestion).
        Prevents context bloat by selecting 5 most relevant tools using a fast model.
        """
        if not self.tool_manager:
            return self._build_native_tool_specs()
            
        tool_menu = self.tool_manager.get_tool_menu()
        tool_count = len(self.tool_manager._handlers)
        
        # If toolset is small, just give everything to save a model call
        if tool_count <= 8:
            return self._build_native_tool_specs()

        # Step A: Fast Selection
        from quentin.llm.client import call_llm
        # P5: Use route instead of get_best_model
        fast_model = self.model_router.route(mode="speed", task_type="reasoning_heavy") 
        
        selection_prompt = (
            f"TASK: {task_description}\n"
            f"INVENTORY:\n{tool_menu}\n"
            "ACTION: Pick the 5 most relevant tool names from the inventory. "
            "Reply with ONLY a comma-separated list of names. Example: fs.read_file, shell.run_command"
        )
        
        print(f"\n[Executor]: Fast-filtering {tool_count} tools...", end="", flush=True)
        try:
            selected_raw = call_llm(fast_model, selection_prompt, system_prompt="You are a tool router.")
            print(f" Raw selection: {selected_raw}", flush=True)
            selected_names = [n.strip() for n in selected_raw.split(",") if n.strip()]
            print(f" selected: {selected_names}", flush=True)
        except Exception as e:
            print(f" Filtering failed: {e}. Using fallback.", flush=True)
            return self._build_native_tool_specs()

        return self._build_native_tool_specs() # P5: Simple fallback for now

    def _build_filtered_specs(self, names: List[str]) -> List[Dict[str, Any]]:
        # P5: Implementation of dynamic spec builder
        # In reality, this would pull from ToolManager._specs
        return self._build_native_tool_specs() # Fallback for this patch
        return [
            {
                "type": "function",
                "function": {
                    "name": "fs.read_file",
                    "description": "Read text file content from the workspace.",
                    "parameters": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]},
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "fs.search_replace",
                    "description": "Replace one text snippet in a file safely.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "path": {"type": "string"},
                            "search": {"type": "string"},
                            "replace": {"type": "string"},
                        },
                        "required": ["path", "search", "replace"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "fs.write_file",
                    "description": "Write full content to a file in allowed paths.",
                    "parameters": {
                        "type": "object",
                        "properties": {"path": {"type": "string"}, "content": {"type": "string"}},
                        "required": ["path", "content"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "shell.run_command",
                    "description": "Run a non-interactive shell command.",
                    "parameters": {
                        "type": "object",
                        "properties": {"command": {"type": "string"}},
                        "required": ["command"],
                    },
                },
            },
        ]

    @staticmethod
    def _normalize_native_reply(native_out: Dict[str, Any]) -> Dict[str, Any]:
        content = str(native_out.get("content") or "").strip()
        parsed: Dict[str, Any]
        if content:
            parsed = Executor._robust_json_parse(content)
            if not isinstance(parsed, dict):
                parsed = {"status": "ok", "result": content}
        else:
            parsed = {"status": "ok", "result": ""}
        parsed["tool_calls"] = native_out.get("tool_calls") or []
        parsed.setdefault("meta", {})
        if isinstance(parsed["meta"], dict):
            parsed["meta"]["tool_call_mode"] = "native"
        return parsed

    @staticmethod
    def _normalize_native_tool_call(raw_call: Any) -> Optional[Dict[str, Any]]:
        if not isinstance(raw_call, dict):
            return None
        function = raw_call.get("function") if isinstance(raw_call.get("function"), dict) else {}
        name = str(function.get("name") or raw_call.get("name") or "").strip()
        if not name:
            return None
        arguments = function.get("arguments", raw_call.get("arguments"))
        if isinstance(arguments, str):
            try:
                arguments = json.loads(arguments)
            except Exception:
                arguments = {}
        if not isinstance(arguments, dict):
            arguments = {}
        return {"tool_name": name, "args": arguments}

    @staticmethod
    def _normalize_json_tool_call(tool_call: Any) -> Optional[Dict[str, Any]]:
        if not isinstance(tool_call, dict):
            return None
        raw_name = (
            tool_call.get("tool_name")
            or tool_call.get("name")
            or tool_call.get("tool")
            or tool_call.get("tool_id")
            or tool_call.get("id")
        )
        name = str(raw_name or "").strip()
        alias_map = {
            "shell_run_command": "shell.run_command",
            "fs_write_file": "fs.write_file",
            "fs_read_file": "fs.read_file",
            "fs_search_replace": "fs.search_replace",
            "fs_list_dir": "fs.list_dir",
            "fs_mkdir": "fs.mkdir",
            "fs_exists": "fs.exists",
        }
        if name:
            name = alias_map.get(name.strip().lower(), name.strip())

        args = tool_call.get("args", tool_call.get("arguments"))
        if isinstance(args, str):
            try:
                args = json.loads(args)
            except Exception:
                args = {}
        if args is None:
            args = {}
        if not isinstance(args, dict):
            return None
        if name and not args:
            if name == "shell.run_command":
                command = tool_call.get("command")
                if command is not None:
                    args = {
                        "command": command,
                        **(
                            {"timeout_seconds": tool_call.get("timeout_seconds")}
                            if tool_call.get("timeout_seconds") is not None
                            else {}
                        ),
                        **(
                            {"yield_seconds": tool_call.get("yield_seconds")}
                            if tool_call.get("yield_seconds") is not None
                            else {}
                        ),
                    }
            elif name == "fs.write_file":
                path = tool_call.get("path", tool_call.get("file_path"))
                content = tool_call.get("content")
                if path is not None or content is not None:
                    args = {
                        **({"path": path} if path is not None else {}),
                        **({"content": content} if content is not None else {}),
                        **({"mode": tool_call.get("mode")} if tool_call.get("mode") is not None else {}),
                    }
            elif name in {"fs.read_file", "fs.exists", "fs.mkdir", "ls", "cat"}:
                path = tool_call.get("path", tool_call.get("file_path"))
                if path is not None:
                    args = {"path": path}
            elif name in {"grep", "fs.search_replace"}:
                path = tool_call.get("path", tool_call.get("file_path"))
                pattern = tool_call.get("pattern")
                replacement = tool_call.get("replacement")
                synthesized: Dict[str, Any] = {}
                if path is not None:
                    synthesized["path"] = path
                if pattern is not None:
                    synthesized["pattern"] = pattern
                if replacement is not None:
                    synthesized["replacement"] = replacement
                if synthesized:
                    args = synthesized
        if not name or not isinstance(args, dict):
            return None
        return {"tool_name": name, "args": args}

    @staticmethod
    def _extract_expected_tool_from_step_description(desc: str) -> str:
        d = str(desc or "").strip().lower()
        if not d:
            return ""
        explicit = (
            "fs.read_file",
            "fs.write_file",
            "fs.search_replace",
            "fs.list_dir",
            "fs.mkdir",
            "fs.exists",
            "shell.run_command",
            "ls",
            "mkdir",
            "cat",
            "grep",
        )
        for tool in explicit:
            if tool in d:
                return tool
        token_map = {
            "read_file": "fs.read_file",
            "write_file": "fs.write_file",
            "search_replace": "fs.search_replace",
            "list directory": "ls",
            "create directory": "mkdir",
        }
        for token, tool in token_map.items():
            if token in d:
                return tool
        return ""

    @staticmethod
    def _tool_family(tool_name: str) -> str:
        n = str(tool_name or "").strip().lower()
        if not n:
            return ""
        if n.startswith("fs.") or n in {"ls", "cat", "mkdir", "grep", "find"}:
            return "filesystem"
        if n.startswith("shell."):
            return "shell"
        if n.startswith("browser.") or n.startswith("web_search."):
            return "browser"
        return "generic"

    @classmethod
    def _are_tools_compatible_for_step(
        cls,
        *,
        expected: str,
        actual: str,
        allowed_fallback_families: Optional[List[str]] = None,
    ) -> bool:
        exp = str(expected or "").strip().lower()
        act = str(actual or "").strip().lower()
        if not exp:
            return True
        if exp == act:
            return True
        exp_fam = cls._tool_family(exp)
        act_fam = cls._tool_family(act)
        if exp == "shell.run_command" and act in {"ls", "cat", "mkdir", "grep"}:
            return True
        allow = [str(x).strip().lower() for x in (allowed_fallback_families or []) if str(x).strip()]
        if act_fam and act_fam in allow:
            return True
        return bool(exp_fam and exp_fam == act_fam)

    @staticmethod
    def _rewrite_shell_call_to_explicit_tool(*, expected_tool: str, tool_call: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        call = dict(tool_call or {})
        tool_name = str(call.get("tool_name") or "").strip().lower()
        args = call.get("args") if isinstance(call.get("args"), dict) else {}
        if tool_name != "shell.run_command":
            return None
        command = str(args.get("command") or "").strip()
        if not command:
            return None
        parts = command.split()
        if not parts:
            return None
        head = parts[0].strip().lower()

        if expected_tool == "fs.read_file" and head == "cat" and len(parts) >= 2:
            return {"tool_name": "fs.read_file", "args": {"path": parts[-1]}}
        if expected_tool in {"ls", "fs.list_dir"} and head == "ls":
            path = "."
            for p in reversed(parts[1:]):
                if not p.startswith("-"):
                    path = p
                    break
            return {"tool_name": "ls", "args": {"path": path}}
        if expected_tool in {"mkdir", "fs.mkdir"} and head == "mkdir":
            for p in reversed(parts[1:]):
                if not p.startswith("-"):
                    return {"tool_name": "mkdir", "args": {"path": p}}
        if expected_tool == "grep" and head == "grep" and len(parts) >= 2:
            pattern = parts[1]
            path = parts[2] if len(parts) >= 3 else "."
            return {"tool_name": "grep", "args": {"pattern": pattern, "path": path}}
        if expected_tool == "fs.exists" and head in {"ls", "stat"}:
            for p in reversed(parts[1:]):
                if not p.startswith("-"):
                    return {"tool_name": "fs.exists", "args": {"path": p}}
        if expected_tool == "fs.exists" and head in {"test", "["}:
            for p in reversed(parts[1:]):
                if p.startswith("-"):
                    continue
                if p in {"]"}:
                    continue
                return {"tool_name": "fs.exists", "args": {"path": p}}
        return None

    def _align_tool_call_with_step_intent(
        self,
        *,
        desc: str,
        tool_call: Dict[str, Any],
        iteration: int,
        expected_tool: str = "",
        allowed_fallback_families: Optional[List[str]] = None,
    ) -> tuple[Dict[str, Any], Optional[Dict[str, Any]]]:
        if not self._env_bool("QUENTIN_PLAN_TOOL_ALIGNMENT_ENABLED", True):
            return tool_call, None
        if not isinstance(tool_call, dict):
            return tool_call, None

        expected = str(expected_tool or "").strip().lower() or self._extract_expected_tool_from_step_description(desc)
        if not expected:
            return tool_call, None
        actual = str(tool_call.get("tool_name") or "").strip().lower()
        if not actual:
            return tool_call, None
        fallback_families = [str(x).strip().lower() for x in (allowed_fallback_families or []) if str(x).strip()]
        if self._are_tools_compatible_for_step(
            expected=expected,
            actual=actual,
            allowed_fallback_families=fallback_families,
        ):
            return tool_call, None

        if self._env_bool("QUENTIN_PLAN_TOOL_ALIGNMENT_AUTO_REWRITE", True):
            rewritten = self._rewrite_shell_call_to_explicit_tool(expected_tool=expected, tool_call=tool_call)
            if isinstance(rewritten, dict):
                return rewritten, {
                    "type": "tool_alignment_rewrite",
                    "reason": "plan_execution_misalignment",
                    "expected_tool": expected,
                    "actual_tool": actual,
                    "rewritten_tool": str(rewritten.get("tool_name") or ""),
                    "allowed_fallback_families": fallback_families,
                }

        hard_block = self._env_bool("QUENTIN_PLAN_TOOL_ALIGNMENT_HARD_BLOCK", True)
        allow_fallback = self._env_bool("QUENTIN_PLAN_TOOL_ALIGNMENT_ALLOW_FALLBACK", True)
        fallback_after = max(1, int(os.getenv("QUENTIN_PLAN_TOOL_ALIGNMENT_FALLBACK_AFTER_ITER", "2") or "2"))
        blocked = hard_block and not (allow_fallback and int(iteration) >= fallback_after)
        return tool_call, {
            "type": "tool_alignment_violation",
            "reason": "plan_execution_misalignment",
            "expected_tool": expected,
            "actual_tool": actual,
            "allowed_fallback_families": fallback_families,
            "blocked": blocked,
            "hint": (
                "Step/tool misalignment: use the explicit tool from step description first. "
                "Fallback to compatible tool family only after alignment retries."
            ),
        }

    @staticmethod
    def _dead_loop_diagnostic_probes() -> List[Dict[str, Any]]:
        return [
            {"tool_name": "pwd", "args": {}},
            {"tool_name": "shell.run_command", "args": {"command": "id"}},
            {"tool_name": "ls", "args": {"path": "."}},
            {"tool_name": "fs.get_write_policy", "args": {}},
        ]

    @staticmethod
    def _build_dead_loop_hint() -> str:
        tools = Executor._get_preferred_coding_tools()
        tool_hint = "/".join(tools[:3]) if tools else "configured coding tools"
        return (
            "EMERGENCY REFLECTION: repeated_tool_call_loop detected. Stop retrying identical calls. "
            f"Run diagnostic probes (pwd/id/ls/fs.get_write_policy), verify writable roots, then pivot strategy via {tool_hint}."
        )

    @staticmethod
    def _is_complex_coding_step(desc: str) -> bool:
        d = str(desc or "").lower()
        markers = (
            "code",
            "complex",
            "复杂",
            "html",
            "parser",
            "解析",
            "crawl",
            "爬取",
            "小红书",
            "logic.py",
            "refactor",
            "重构",
        )
        return any(m in d for m in markers)

    @staticmethod
    def _env_bool(name: str, default: bool) -> bool:
        raw = os.getenv(name, "1" if default else "0")
        return str(raw or "").strip().lower() in {"1", "true", "yes", "on"}

    @staticmethod
    def _get_preferred_coding_tools() -> List[str]:
        primary = str(os.getenv("QUENTIN_CODING_TOOL_PRIMARY", "gemini.code") or "").strip()
        fallback_raw = str(os.getenv("QUENTIN_CODING_TOOL_FALLBACKS", "coder.generate") or "")
        fallbacks = [x.strip() for x in fallback_raw.split(",") if x.strip()]
        out: List[str] = []
        for x in [primary, *fallbacks]:
            if x and x not in out:
                out.append(x)
        return out

    @classmethod
    def _build_coding_tool_guard_hint(cls) -> str:
        tools = cls._get_preferred_coding_tools()
        preferred = "/".join(tools[:3]) if tools else "configured coding tools"
        allow_direct = cls._env_bool("QUENTIN_CODING_TOOL_ALLOW_DIRECT_WRITE_FALLBACK", False)
        fallback_iter = int(os.getenv("QUENTIN_CODING_TOOL_FALLBACK_AFTER_ITER", "3") or "3")
        return (
            "Complex coding/editing task detected. Avoid direct fs.write_file. "
            f"Use {preferred} first. "
            f"Direct fs.write_file fallback is {'enabled' if allow_direct else 'disabled'} "
            f"(after iteration >= {max(1, fallback_iter)} when enabled)."
        )

    def _should_enforce_coding_tool(self, *, desc: str, tool_call: Dict[str, Any], iteration: int = 1) -> bool:
        if not self._env_bool("QUENTIN_CODING_TOOL_GUARD_ENABLED", True):
            return False
        if not self._is_complex_coding_step(desc):
            return False
        if not isinstance(tool_call, dict):
            return False
        tool_name = str(tool_call.get("tool_name") or "").strip().lower()
        if tool_name != "fs.write_file":
            return False
        if not self._env_bool("QUENTIN_CODING_TOOL_ALLOW_DIRECT_WRITE_FALLBACK", False):
            return True
        fallback_iter = max(1, int(os.getenv("QUENTIN_CODING_TOOL_FALLBACK_AFTER_ITER", "3") or "3"))
        return int(iteration) < fallback_iter

    def _repeat_limit_for_tool_call(self, tool_call: Dict[str, Any]) -> int:
        """
        Repeated-call guard:
        - keep strict limit for mutating calls
        - allow a slightly larger budget for read-only probing calls
        """
        from quentin.config.dynamic_manager import get_dynamic_config
        dynamic_cfg = get_dynamic_config(repo_root=self.repo_root)
        
        tool_name = str(tool_call.get("tool_name") or "").strip().lower()
        args = tool_call.get("args") if isinstance(tool_call.get("args"), dict) else {}
        read_only_names = {
            "fs.read_file",
            "ls",
            "cat",
            "grep",
            "rg",
            "find",
            "which",
        }
        
        # Base limits (can be boosted by network stability settings)
        limit_write = int(dynamic_cfg.get("repeat_limit_write", 3))
        limit_read = int(dynamic_cfg.get("repeat_limit_read", 5))

        if tool_name in read_only_names:
            return limit_read
        if tool_name in {"shell.run_command", "shell_run_command"}:
            command = str(args.get("command") or "").strip()
            base = command.split()[0].split("/")[-1].lower() if command else ""
            if base in read_only_names or base in {"pwd"}:
                return limit_read
        return limit_write

    def _repair_tool_call_for_paths(self, tool_call: Dict[str, Any]) -> tuple[Dict[str, Any], Optional[str]]:
        """
        Guard against common tool misuse from local models:
        reading a directory with `fs.read_file` / `cat`.
        """
        if not isinstance(tool_call, dict):
            return tool_call, None
        tool_name = str(tool_call.get("tool_name") or "").strip().lower()
        args = tool_call.get("args") if isinstance(tool_call.get("args"), dict) else {}
        path = args.get("path")
        if tool_name not in {"fs.read_file", "cat"} or not isinstance(path, str) or not path.strip():
            return tool_call, None

        rel_path = path.strip()
        is_dir_hint = rel_path.endswith("/")
        try:
            candidate = (self.repo_root / rel_path).resolve()
            if not is_dir_hint and candidate.exists() and candidate.is_dir():
                is_dir_hint = True
        except Exception:
            pass

        if is_dir_hint:
            fixed = rel_path.rstrip("/") or "."
            return {"tool_name": "ls", "args": {"path": fixed}}, "directory_read_rewritten_to_ls"
        return tool_call, None

    async def _execute_tool_call(self, *, tool_call: Dict[str, Any], context: Dict[str, Any]) -> Any:
        if self.tool_manager is None:
            return {"status": "error", "error": "tool_manager_unavailable"}

        # Repair common directory/file confusion before auditing/execution.
        tool_call, _ = self._repair_tool_call_for_paths(tool_call)
        
        # Phase 5.4: Mandatory Security Audit
        from quentin.infra.security.auditor import auditor
        is_safe, reason = auditor.audit_skill_call(
            tool_call.get("tool_name", ""), 
            tool_call.get("args", {})
        )
        if not is_safe:
            # P6: Optional HITL (default OFF). When OFF, fail closed (deny).
            import os

            approval_enabled = (os.getenv("QUENTIN_APPROVAL_GATE", "0") or "").strip().lower() in ("1", "true", "yes", "on")
            if not approval_enabled:
                return {"status": "error", "error": f"security_violation: {reason} (approval gate disabled)"}

            from quentin.infra.security.approval import approval_gate
            logger.warning(f"Executor: Security Warning! {reason}. Requesting human approval...")

            approved = await approval_gate.request_approval(
                tool_name=tool_call.get("tool_name", ""),
                args=tool_call.get("args", {}),
                reason=reason or "Sensitive Action",
            )

            if not approved:
                return {"status": "error", "error": f"security_violation: {reason} (User Denied)"}

            logger.info("Executor: Human approved sensitive action. Proceeding.")

        from quentin.tools.schemas import ToolCallRequest
        from quentin.tools.manager import ToolCallContext

        req = ToolCallRequest(
            tool_name=str(tool_call.get("tool_name") or ""),
            payload=dict(tool_call.get("args") or {}),
            trace_id=context.get("trace_id"),
        )
        try:
            result = await self.tool_manager.call_tool(
                req,
                ctx=ToolCallContext(
                    metadata=context,
                    trace_id=context.get("trace_id"),
                    cancel_token=context.get("cancel_token"),
                ),
            )
        except KeyError as e:
            return {"status": "error", "error": f"tool_not_found:{e}", "tool_name": req.tool_name}
        except PermissionError:
            # Preserve safety semantics: native tool-calling path must fall back to JSON mode
            # when the safety kernel denies a call (tests rely on this behavior).
            raise
        # v3.1+ Predictive First (v0): attach expected_state + prediction_error to tool_result.
        try:
            if bool(context.get("enable_expectation_engine")) and context.get("expectation_engine") is not None:
                engine = context.get("expectation_engine")
                situation_id = str(context.get("situation_id") or "unknown")
                tool_name = str(tool_call.get("tool_name") or "")
                step = {"description": str(context.get("current_step_description") or ""), "tool_call": tool_call}
                expected = engine.build_expected(situation_id=situation_id, tool_name=tool_name, step=step, ctx=context)  # type: ignore[attr-defined]
                observed = result.to_dict() if hasattr(result, "to_dict") else (result.model_dump() if hasattr(result, "model_dump") else (result.dict() if hasattr(result, "dict") else result))
                pred_err = engine.compute_error(expected=expected, observed=observed if isinstance(observed, dict) else {"result": observed}, ctx=context)  # type: ignore[attr-defined]
                if hasattr(result, "meta") and isinstance(getattr(result, "meta", None), dict):
                    result.meta.setdefault("expected_state", expected.to_dict() if hasattr(expected, "to_dict") else expected)  # type: ignore[union-attr]
                    result.meta.setdefault("prediction_error", pred_err.to_dict() if pred_err and hasattr(pred_err, "to_dict") else (pred_err if pred_err else None))  # type: ignore[union-attr]
        except Exception:
            pass
        return result

    @staticmethod
    def _goal_to_dict(goal: Any) -> Dict[str, Any]:
        if goal is None:
            return {}
        if isinstance(goal, dict):
            return goal
        if hasattr(goal, "to_dict"):
            try:
                return goal.to_dict()
            except Exception:
                return {"repr": repr(goal)}
        if hasattr(goal, "__dict__"):
            try:
                return dict(goal.__dict__)
            except Exception:
                return {"repr": repr(goal)}
        return {"repr": repr(goal)}

    @staticmethod
    def _resolve_narration_mode(*, step: Dict[str, Any], context: Dict[str, Any]) -> str:
        """
        OpenClaw-style guidance:
        - minimal: routine/low-risk tool calls (default)
        - explain: complex, multi-step, or risky operations
        """
        risk_level = str(context.get("risk_level") or "").strip().lower()
        if risk_level in {"high", "critical"}:
            return "explain"

        step_text = Executor._safe_json_dump(step).lower()
        risk_markers = (
            "rm -rf",
            "chmod",
            "delete",
            "drop ",
            "shutdown",
            "reboot",
            "mkfs",
            "dd ",
            "destructive",
        )
        if any(marker in step_text for marker in risk_markers):
            return "explain"

        if bool(context.get("progressive_pressure")):
            return "explain"

        return "minimal"

    def _build_tool_summaries(self) -> Dict[str, str]:
        if self.tool_manager is not None and hasattr(self.tool_manager, "get_tool_summaries"):
            try:
                return self.tool_manager.get_tool_summaries(max_words=10)
            except Exception:
                pass
        return {
            "fs.write_file": "Write content to a file path.",
            "fs.read_file": "Read text content from a file.",
            "shell.run_command": "Run non-interactive shell commands safely.",
        }

    def _build_tool_summary_block(self) -> str:
        if self.tool_manager is not None and hasattr(self.tool_manager, "get_tool_summaries"):
            try:
                summaries = self.tool_manager.get_tool_summaries(max_words=10)
                block = format_tool_summary_block(summaries)
                if block.strip():
                    return block
            except Exception:
                pass
        fallback = build_tool_summary_map(
            tool_descriptions={
                "fs.write_file": "Write content to a file path.",
                "fs.read_file": "Read text content from a file.",
                "shell.run_command": "Run non-interactive shell commands safely.",
            },
            max_words=10,
        )
        return format_tool_summary_block(fallback)

    @staticmethod
    def _truncate_prompt_text(value: Any, *, max_len: int = 120) -> str:
        text = str(value or "").strip().replace("\n", " ")
        if len(text) <= max_len:
            return text
        return text[: max_len - 3] + "..."

    def _build_tool_knowledge_block(self) -> str:
        if not self._tool_knowledge_prompt_enabled:
            return ""
        now = time.time()
        if (
            self._tool_knowledge_block_cache is not None
            and (now - float(self._tool_knowledge_block_cache_at or 0.0)) < self._tool_knowledge_block_cache_ttl_s
        ):
            return self._tool_knowledge_block_cache

        try:
            from quentin.memory.fabric import MemoryFabric
            from quentin.memory.kinds import KIND_TOOL_KNOWLEDGE
            from quentin.memory.models import MemoryQuery, MemoryTier

            memory_fabric = MemoryFabric(repo_root=self.repo_root)
            records = memory_fabric.store.search(
                MemoryQuery(
                    text="",
                    mode="text_only",
                    top_k=int(self._tool_knowledge_prompt_top_k),
                    tier=MemoryTier.LTS,
                    kind=KIND_TOOL_KNOWLEDGE,
                )
            )
            if not records:
                self._tool_knowledge_block_cache = ""
                self._tool_knowledge_block_cache_at = now
                return ""

            known_tools = None
            if self.tool_manager is not None and hasattr(self.tool_manager, "list_tool_names"):
                try:
                    known_tools = set(self.tool_manager.list_tool_names())
                except Exception:
                    known_tools = None

            lines: List[str] = ["TOOL KNOWLEDGE (learned usage):"]
            for rec in records:
                md = dict(getattr(rec, "metadata", None) or {})
                tool_name = str(md.get("tool_name") or md.get("tool_id") or "").strip()
                if not tool_name:
                    continue
                if isinstance(known_tools, set) and known_tools and tool_name not in known_tools:
                    continue
                stats = md.get("stats") if isinstance(md.get("stats"), dict) else {}
                call_count = int(stats.get("call_count") or 0)
                success_rate = float(stats.get("success_rate") or 0.0)
                last_used_at = str(stats.get("last_used_at") or "")

                examples = md.get("examples") if isinstance(md.get("examples"), list) else []
                example_text = ""
                if examples:
                    ex = examples[-1]
                    if isinstance(ex, dict):
                        inp = self._truncate_prompt_text(ex.get("input"), max_len=90)
                        out = self._truncate_prompt_text(ex.get("output") or ex.get("result"), max_len=90)
                        err = self._truncate_prompt_text(ex.get("error"), max_len=90)
                        if err:
                            example_text = f"last_example_error={err}"
                        elif inp or out:
                            example_text = f"last_example_input={inp}; output={out}"
                    else:
                        example_text = self._truncate_prompt_text(ex, max_len=120)

                line = (
                    f"- {tool_name}: call_count={call_count}, success_rate={success_rate:.2f}"
                    + (f", last_used_at={last_used_at}" if last_used_at else "")
                )
                lines.append(line)
                if example_text:
                    lines.append(f"  {example_text}")

                if len(lines) >= (1 + int(self._tool_knowledge_prompt_top_k) * 2):
                    break

            block = "\n".join(lines).strip()
            if block == "TOOL KNOWLEDGE (learned usage):":
                block = ""
            self._tool_knowledge_block_cache = block
            self._tool_knowledge_block_cache_at = now
            return block
        except Exception:
            self._tool_knowledge_block_cache = ""
            self._tool_knowledge_block_cache_at = now
            return ""

    @staticmethod
    def _has_visible_progress(parsed: Any) -> bool:
        if not isinstance(parsed, dict):
            return False
        if "tool_result" in parsed:
            return True
        text = str(parsed.get("result") or "").strip()
        if text:
            return True
        return False
