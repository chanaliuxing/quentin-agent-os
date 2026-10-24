# meta_agent/runtime/task_executor.py
from __future__ import annotations
from typing import Dict, Any, Optional
import uuid
import os

from meta_agent.goals import GoalManager
from quentin.l3.research.smoke_evaluator import SmokeEvaluator
from meta_agent.skills.executor import SkillExecutor
from meta_agent.tools.bootstrap import bootstrap_registry
from meta_agent.tools.registry import ToolRegistry, ToolLifecycle
from meta_agent.tools.registry_loader import resolve_registry_index
from meta_agent.tools.knowledge_sync import sync_registry_to_memory, record_tool_usage
from meta_agent.self_programming.mcp_integration import MCPToolInvoker, ServerDescriptor
from quentin.traces.core import JsonlTraceRecorder, new_trace_event, TraceEventType

trace = JsonlTraceRecorder(repo_root=".")


class TaskExecutor:
    def __init__(
        self,
        skill_executor: Optional[SkillExecutor] = None,
        tool_registry: Optional[ToolRegistry] = None,
        registry_index: Optional[list[dict]] = None,
        registry_index_path: Optional[str] = None,
        memory_search=None,
        memory_fabric=None,
        sync_tool_knowledge: bool = False,
        tool_invoker: Optional[MCPToolInvoker] = None,
        goal_manager: Optional[GoalManager] = None,
        smoke_evaluator: Optional[SmokeEvaluator] = None,
        enable_smoke_tests: bool = False,
    ) -> None:
        self.skill_executor = skill_executor or SkillExecutor()
        self.memory_fabric = memory_fabric
        self.sync_tool_knowledge = sync_tool_knowledge
        self.tool_registry = tool_registry or bootstrap_registry(
            registry_index=resolve_registry_index(registry_index, registry_index_path),
            memory_search=memory_search,
        )
        self.tool_invoker = tool_invoker or MCPToolInvoker()
        self.goal_manager = goal_manager or GoalManager()
        self.smoke_evaluator = smoke_evaluator or SmokeEvaluator()
        self.enable_smoke_tests = enable_smoke_tests
        # 这里还可以有其他工具 / LLM 客户端等

    def _select_tool(self, tool_id: str):
        """
        Prefer trusted variant if available; allow experimental as fallback.
        """
        if not self.tool_registry:
            return None
        reg = self.tool_registry.get(tool_id)
        if reg and reg.governance.lifecycle == ToolLifecycle.TRUSTED:
            return reg
        # If requested tool is experimental, still allow it; otherwise try to find a trusted sibling.
        if reg:
            return reg
        trusted = [t for t in self.tool_registry.list(ToolLifecycle.TRUSTED) if t.tool_id.endswith(tool_id)]
        if trusted:
            return trusted[0]
        experimental = [t for t in self.tool_registry.list(ToolLifecycle.EXPERIMENTAL) if t.tool_id.endswith(tool_id)]
        return experimental[0] if experimental else None

    def execute_plan(self, task: Dict[str, Any], plan: Dict[str, Any]) -> Dict[str, Any]:
        results = {}
        success = True
        goal_id = task.get("id") or f"goal-{uuid.uuid4().hex[:8]}"
        goal_description = task.get("description") or task.get("type")

        if self.goal_manager:
            self.goal_manager.activate_goal(goal_id, description=goal_description, metadata={"task": task})

        steps = plan.get("steps", [])
        for step in steps:
            stype = step.get("type")
            sid = step.get("id") or f"step-{uuid.uuid4().hex[:4]}"
            try:
                if stype == "use_skill":
                    skill_id = step.get("skill_id")
                    inputs = step.get("inputs") or {}
                    res = self.skill_executor.execute(skill_id, inputs, task_context=task)
                elif stype == "call_tool":
                    tool_id = step.get("tool_id")
                    if not tool_id:
                        raise ValueError("call_tool step missing tool_id")
                    reg = self._select_tool(tool_id)
                    if not reg:
                        res = {"error": f"tool_not_found: {tool_id}"}
                    else:
                        tool_name = tool_id.split("/", 1)[1] if "/" in tool_id else tool_id
                        arguments = step.get("args") or step.get("inputs") or {}
                        server = ServerDescriptor(
                            server_id=reg.server,
                            transport=reg.transport,
                            uri=reg.uri,
                            auth_token=reg.auth_token, # Pass auth_token from ToolRegistration
                        )
                        result = self.tool_invoker.invoke(
                            server=server, tool_name=tool_name, arguments=arguments
                        )
                        if not result.success: # If tool invocation failed
                            success = False    # Mark overall plan as failed
                        self.tool_registry.record_invocation(
                            tool_id,
                            success=result.success,
                            latency_ms=int(result.latency_ms),
                            error=result.error,
                        )
                        if self.memory_fabric and self.sync_tool_knowledge:
                            record_tool_usage(
                                self.tool_registry,
                                self.memory_fabric,
                                tool_id,
                                arguments=arguments,
                                output=result.output,
                                error=result.error,
                                success=result.success,
                            )
                            sync_registry_to_memory(self.tool_registry, self.memory_fabric)
                        res = {
                            "tool_id": tool_id,
                            "server": reg.server,
                            "success": result.success,
                            "output": result.output,
                            "error": result.error,
                            "latency_ms": result.latency_ms,
                        }
                elif stype == "llm_call":
                    from quentin.llm.client import call_llm

                    inputs = step.get("inputs") or {}
                    user_prompt = (
                        step.get("prompt")
                        or inputs.get("prompt")
                        or inputs.get("user_prompt")
                        or step.get("user_prompt")
                        or ""
                    )
                    system_prompt = (
                        step.get("system_prompt")
                        or inputs.get("system_prompt")
                        or step.get("system")
                        or inputs.get("system")
                        or ""
                    )
                    provider = step.get("provider") or inputs.get("provider")
                    model_name = step.get("model") or inputs.get("model") or os.getenv("LLM_MODEL")
                    auth_profile_id = step.get("auth_profile_id") or inputs.get("auth_profile_id")
                    auth_store_path = step.get("auth_store_path") or inputs.get("auth_store_path")
                    reserve_tokens = int(step.get("reserve_tokens") or inputs.get("reserve_tokens") or 0)

                    out = call_llm(
                        model_name or os.getenv("LLM_MODEL"),
                        user_prompt=str(user_prompt),
                        system_prompt=str(system_prompt),
                        provider=provider,
                        model_name=model_name,
                        auth_profile_id=auth_profile_id,
                        auth_store_path=auth_store_path,
                        reserve_tokens=reserve_tokens,
                        action_metadata={"topic": "task_executor_llm_call", "task_id": task.get("id"), "step_id": sid},
                    )
                    res = {"output": out}
                else:
                    res = {"info": "no-op or decision step"}

                results[sid] = res
            except Exception as e:
                success = False
                results[sid] = {"error": repr(e)}
                trace.record_event(
                    new_trace_event(
                        trace_id=task.get("id", "unknown_trace"),
                        event_type=TraceEventType.ERROR,
                        payload={"task_id": task.get("id"), "step_id": sid, "error": repr(e)},
                    )
                )

        smoke_result = None
        overall_success = success
        if self.enable_smoke_tests and self.smoke_evaluator and self._should_run_smoke_tests(task, plan):
            smoke_result = self.smoke_evaluator.run_smoke_tests(
                test_paths=plan.get("smoke_tests") or task.get("smoke_tests")
            )
            overall_success = success and smoke_result.success

        if self.goal_manager:
            attempt_metadata = {
                "plan_success": success,
                "smoke_result": smoke_result.to_dict() if smoke_result else None,
            }
            self.goal_manager.record_attempt(goal_id, overall_success, metadata=attempt_metadata)
            self.goal_manager.complete_goal(goal_id, success=overall_success)

        trace.record_event(
            new_trace_event(
                trace_id=goal_id,
                event_type=TraceEventType.EXECUTION,
                payload={
                    "task_type": task.get("type") or "unknown",
                    "task_id": task.get("id"),
                    "success": overall_success,
                    "plan": plan,
                    "results_preview": str(results)[:800],
                    "smoke_result": smoke_result.to_dict() if smoke_result else None,
                },
            )
        )
        return {
            "success": overall_success,
            "results": results,
            "smoke_result": smoke_result.to_dict() if smoke_result else None,
        }

    def _should_run_smoke_tests(self, task: Dict[str, Any], plan: Dict[str, Any]) -> bool:
        return bool(
            task.get("requires_smoke_tests")
            or plan.get("requires_smoke_tests")
            or task.get("code_change")
            or plan.get("code_change")
        )
