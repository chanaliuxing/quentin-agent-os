from __future__ import annotations

import json
import uuid
import hashlib
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

from quentin.planning import Plan, PlanStep
from quentin.tools.manager import ToolManager, ToolCallContext
from quentin.tools.schemas import ToolCallRequest
from quentin.llm.ollama_client import OllamaLLMClient
from quentin.traces.core import TraceRecorder, new_trace_event, TraceEventType
from quentin.infra.concurrency.cancellation import CancellationToken, CancelledError
from quentin.execution.idempotency import IdempotencyGate
from quentin.execution.contract import StepContractGuard


class Executor:
    """
    v1 Plan Executor:

    - 接收一个 Plan
    - 迭代执行 Plan 中的每个 step
    - 根据 step.kind 调用不同组件（ToolManager, LLM, etc.）
    - 简单地将上一步的输出作为下一步的输入
    """

    def __init__(
        self,
        tool_manager: ToolManager,
        llm: OllamaLLMClient,
        trace_recorder: TraceRecorder,
        repo_root: str = ".",
    ):
        self.tool_manager = tool_manager
        self.llm = llm
        self.trace_recorder = trace_recorder
        self.idempotency_gate = IdempotencyGate(repo_root=repo_root)
        self.step_contract_guard = StepContractGuard()

    async def execute_plan(self, plan: Plan | Dict[str, Any], context: Dict[str, Any], goal: Any = None) -> Dict[str, Any]:
        """
        执行一个完整的计划。
        """
        # P4-A: Reset contract guard for new plan
        self.step_contract_guard.reset()
        
        # Start a new trace span for the plan execution
        plan_id = getattr(plan, "plan_id", str(uuid.uuid4()))
        trace_id = f"exec_plan_{plan_id}"
        self.trace_recorder.record_event(
            new_trace_event(
                trace_id=trace_id,
                event_type=TraceEventType.EXECUTION,
                payload={"phase": "plan_start", "plan": plan.to_dict() if hasattr(plan, "to_dict") else plan, "context": context},
            )
        )

        step_outputs = {}
        final_output = None

        cancel_token = context.get("cancel_token")
        if isinstance(cancel_token, CancellationToken):
            cancel_token.raise_if_cancelled()

        steps = plan.steps if hasattr(plan, "steps") else plan.get("steps", [])
        try:
            for step in steps:
                if not isinstance(step, PlanStep) and isinstance(step, dict):
                    # Convert dict to PlanStep for _execute_step
                    step = PlanStep(
                        step_id=step.get("step_id", "s"),
                        description=step.get("description", ""),
                        kind=step.get("kind", "tool"),
                        name=step.get("name", ""),
                        args=step.get("args", {}),
                        fingerprint=step.get("fingerprint"),
                        target_file=step.get("target_file")
                    )

                # Simple data flow: make previous step outputs available to the next step
                current_context = {**context, **step_outputs}

                step_output = await self._execute_step(step, current_context, trace_id)

                step_outputs[f"{step.step_id}_output"] = step_output
                final_output = step_output  # The output of the last step is the final output
        except CancelledError as e:
            self.trace_recorder.record_event(
                new_trace_event(
                    trace_id=trace_id,
                    event_type=TraceEventType.ERROR,
                    payload={"phase": "aborted", "reason": str(e)},
                )
            )
            raise

        self.trace_recorder.record_event(
            new_trace_event(
                trace_id=trace_id,
                event_type=TraceEventType.EXECUTION,
                payload={"phase": "plan_end", "final_output": final_output},
            )
        )
        return {"raw_output": final_output}

    def _generate_auto_fingerprint(self, step: PlanStep) -> Optional[str]:
        """
        P0.2: Generate a deterministic fingerprint for mutating operations.
        """
        if step.kind != "tool":
            return None
        
        # We only fingerprint high-impact mutating operations
        mutating_tools = {"fs.write_file", "fs.search_replace", "mkdir"}
        if step.name not in mutating_tools:
            return None
            
        try:
            # Deterministic hash of tool name + relevant arguments
            parts = [step.name]
            args = step.args or {}
            
            if step.name == "fs.write_file":
                path = args.get("path") or args.get("file")
                content = args.get("content", "")
                if path:
                    parts.append(str(path))
                    # Hash content to keep fingerprint string length manageable
                    content_hash = hashlib.sha256(str(content).encode("utf-8")).hexdigest()
                    parts.append(content_hash)
            
            elif step.name == "fs.search_replace":
                path = args.get("path") or args.get("file")
                old_s = args.get("old_string", "")
                new_s = args.get("new_string", "")
                if path:
                    parts.append(str(path))
                    parts.append(old_s)
                    parts.append(new_s)
                    
            elif step.name == "mkdir":
                path = args.get("path") or args.get("dir")
                if path:
                    parts.append(str(path))
            
            if len(parts) > 1:
                raw = "|".join(parts)
                return hashlib.sha256(raw.encode("utf-8")).hexdigest()
        except Exception as e:
            logger.warning(f"Executor: failed to generate auto-fingerprint: {e}")
            
        return None

    async def _execute_step(
        self,
        step: PlanStep,
        context: Dict[str, Any],
        trace_id: str
    ) -> Any:
        """
        执行单个计划步骤。
        """
        # P0.2: Content-aware fingerprints when planner omitted/unstable
        if not step.fingerprint:
            step.fingerprint = self._generate_auto_fingerprint(step)

        # P4-A: Idempotency check
        target_file = step.args.get("path") or step.args.get("file") or step.args.get("target_path")
        if step.fingerprint and self.idempotency_gate.check(step.fingerprint, target_file):
            self.trace_recorder.record_event(
                new_trace_event(
                    trace_id=trace_id,
                    event_type=TraceEventType.EXECUTION,
                    payload={"phase": "step_skip", "step_id": step.step_id, "reason": "idempotent_hit", "fingerprint": step.fingerprint},
                )
            )
            return {"status": "skipped", "idempotent_hit": True}

        # P4-A: Step Contract check
        if not self.step_contract_guard.verify_step(step):
             raise RuntimeError(f"Step {step.step_id} ('{step.name}') violated step contract: mutation without prior observation.")

        self.trace_recorder.record_event(
            new_trace_event(
                trace_id=trace_id,
                event_type=TraceEventType.EXECUTION,
                payload={"phase": "step_start", "step": step.to_dict(), "context": context},
            )
        )
        
        cancel_token = context.get("cancel_token")
        if isinstance(cancel_token, CancellationToken):
            cancel_token.raise_if_cancelled()

        # Validation for empty name
        if step.kind in ("tool", "skill") and not str(step.name or "").strip():
            raise ValueError(f"Step {step.step_id} of kind {step.kind} has empty name. Full step: {step}")

        output = None
        error: Optional[str] = None
        re_raise: Optional[BaseException] = None
        format_salvaged = False

        try:
            if step.kind == "tool":
                # P4-B: Complexity layering (fast path)
                fast_path_tools = {"ls", "pwd", "sys.info", "fs.exists"}
                if step.name in fast_path_tools:
                    self.trace_recorder.record_event(
                        new_trace_event(
                            trace_id=trace_id,
                            event_type=TraceEventType.EXECUTION,
                            payload={"phase": "fast_path", "tool": step.name},
                        )
                    )
                    # For v1, we still call tool_manager but mark it as fast_path in trace.
                    # Future: call lightweight handler directly.
                
                if hasattr(self.tool_manager, "call_tool"):
                    ctx = ToolCallContext(metadata={
                        "domain": context.get("domain", "core"),
                        "environment": context.get("environment", "sandbox"),
                        "risk_level": context.get("risk_level", "medium"),
                        "trace_id": trace_id,
                        "trace_recorder": self.trace_recorder,
                    }, cancel_token=cancel_token if isinstance(cancel_token, CancellationToken) else None, trace_id=trace_id)
                    result = await self.tool_manager.call_tool(
                        ToolCallRequest(tool_name=step.name, payload=step.args, trace_id=trace_id),
                        ctx=ctx,
                    )
                    output = result.output if hasattr(result, "output") else result
                    if hasattr(result, "success") and not result.success:
                        error = result.error or "action failed"
                else:
                    output = self.tool_manager.run_tool(step.name, step.args)
                    if isinstance(output, dict) and output.get("status") == "error":
                        error = output.get("error") or "action failed"
            elif step.kind == "skill":
                # Assuming a skill manager exists and has a similar interface
                # For now, we'll treat it like a tool
                if hasattr(self.tool_manager, "call_tool"):
                    ctx = ToolCallContext(metadata={
                        "domain": context.get("domain", "core"),
                        "environment": context.get("environment", "sandbox"),
                        "risk_level": context.get("risk_level", "medium"),
                        "trace_id": trace_id,
                        "trace_recorder": self.trace_recorder,
                    }, cancel_token=cancel_token if isinstance(cancel_token, CancellationToken) else None, trace_id=trace_id)
                    result = await self.tool_manager.call_tool(
                        ToolCallRequest(tool_name=step.name, payload=step.args, trace_id=trace_id),
                        ctx=ctx,
                    )
                    output = result.output if hasattr(result, "output") else result
                    if hasattr(result, "success") and not result.success:
                        error = result.error or "action failed"
                else:
                    output = self.tool_manager.run_tool(step.name, step.args)
                    if isinstance(output, dict) and output.get("status") == "error":
                        error = output.get("error") or "action failed"
            elif step.kind == "llm_call":
                if isinstance(cancel_token, CancellationToken):
                    cancel_token.raise_if_cancelled()
                prompt = f"Executing task: {step.description}\nArgs: {json.dumps(step.args)}"
                res = self.llm.complete(prompt)
                if hasattr(res, "__await__"):
                    res = await res  # type: ignore[assignment]
                
                # P4-A: JSON salvage and format_soft_fail
                try:
                    output = self.llm.extract_json(res)
                    # Simple check if salvage was needed
                    if res.strip() != json.dumps(output):
                        format_salvaged = True
                except Exception as e:
                    logger.warning("LLM output format failed: %s", e)
                    output = {"raw_text": res, "error": str(e), "format_fail": True}
            elif step.kind == "sub_plan" and step.sub_steps:
                 sub_plan = Plan(plan_id=f"{step.step_id}_sub_plan", goal=step.description, steps=step.sub_steps)
                 output = await self.execute_plan(sub_plan, context)
            else:
                raise ValueError(f"Unknown step kind: {step.kind}")
            
            # P4-A: Mark success for idempotency
            if step.fingerprint:
                self.idempotency_gate.mark_success(step.fingerprint, target_file)

            if isinstance(cancel_token, CancellationToken):
                cancel_token.raise_if_cancelled()
        except Exception as e:  # noqa: BLE001
            if isinstance(e, CancelledError):
                error = f"cancelled:{e}"
                re_raise = e
            else:
                error = str(e)
                re_raise = e
        
        self.trace_recorder.record_event(
            new_trace_event(
                trace_id=trace_id,
                event_type=TraceEventType.EXECUTION,
                payload={"phase": "step_end", "output": output, "error": error, "format_salvaged": format_salvaged},
            )
        )

        if re_raise is not None:
            raise re_raise
        if error:
            raise RuntimeError(f"Step {step.step_id} failed: {error}")
            
        return output
