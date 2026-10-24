# scripts/run_meta_agent_executor.py
import os
import uuid
import logging
from pathlib import Path
from unittest.mock import patch # Import patch for mocking

from meta_agent.goals.goal_manager import GoalManager # Corrected import
from meta_agent.runtime.task_executor import TaskExecutor
from meta_agent.tools.registry import ToolRegistry, ToolLifecycle, ToolRegistration, ToolGovernance
from meta_agent.self_programming.mcp_integration.invoker import MCPToolInvoker, ToolInvocationResult
from meta_agent.self_programming.mcp_integration.types import ServerDescriptor
from quentin.l3.research.smoke_evaluator import SmokeEvaluator

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def main():
    # 1. Create a persistent GoalManager
    goal_manager_path = Path("data/meta_agent_goals.json")
    goal_manager = GoalManager(storage_path=goal_manager_path)
    logger.info(f"Initialized GoalManager with storage path: {goal_manager_path}")

    # 2. Instantiate a TaskExecutor with enable_smoke_tests=True
    dummy_registry = ToolRegistry()
    dummy_tool = ToolRegistration(
        tool_id="dummy/example_tool",
        description="A dummy tool for demonstration.",
        signature='{"input_arg": "string"}',
        governance=ToolGovernance(lifecycle=ToolLifecycle.TRUSTED),
        server="dummy_server",
        transport="stdio",
        uri="dummy_uri",
    )
    dummy_registry.register(dummy_tool)
    
    # Patch _MCP_AVAILABLE to True for the duration of this script's execution
    with patch("meta_agent.self_programming.mcp_integration.invoker._MCP_AVAILABLE", True):
        dummy_invoker = MCPToolInvoker() # This will now proceed past the _MCP_AVAILABLE check
        
        # Mock the internal logic of MCPToolInvoker to simulate a tool response
        # This is needed because the MCPToolInvoker will be called by TaskExecutor.execute_plan
        # and we don't have a real MCP server running.
        def mock_invoke_implementation(server, tool_name, arguments):
            logger.info(f"Mock invoking tool: {tool_name} with args: {arguments}")
            if tool_name == "example_tool":
                return ToolInvocationResult(
                    success=True,
                    output={"message": f"Hello from {tool_name}!"},
                    error=None,
                    latency_ms=50
                )
            return ToolInvocationResult(success=False, output=None, error="Unknown dummy tool", latency_ms=0)
        
        dummy_invoker.invoke = mock_invoke_implementation # Assign the mock implementation

        # SmokeEvaluator setup (default points to tests/unit)
        smoke_evaluator = SmokeEvaluator()

        task_executor = TaskExecutor(
            tool_registry=dummy_registry,
            tool_invoker=dummy_invoker,
            goal_manager=goal_manager,
            enable_smoke_tests=True,
            smoke_evaluator=smoke_evaluator,
            sync_tool_knowledge=True # Enable knowledge sync for demonstration
        )
        logger.info("Initialized TaskExecutor with enable_smoke_tests=True")

        # 3. Construct example task and plan objects
        task_id = f"test_task_{uuid.uuid4().hex[:8]}"
        example_task = {
            "id": task_id,
            "type": "feature_implementation",
            "description": "Implement a new feature to greet users.",
            "code_change": True,
            "requires_smoke_tests": True,
            "smoke_tests": ["tests/unit/test_goal_manager.py"], # Point to an existing test file
        }

        example_plan = {
            "steps": [
                {
                    "type": "call_tool",
                    "tool_id": "dummy/example_tool",
                    "args": {"input_arg": "world"},
                    "id": "step-greet",
                },
                {
                    "type": "llm_call",
                    "prompt": "Based on the tool output, generate a greeting message.",
                    "id": "step-llm-greet",
                }
            ]
        }
        logger.info(f"Constructed example task: {example_task['id']}")

        # 4. Execute the plan and print the result
        logger.info("Executing plan with TaskExecutor...")
        result = task_executor.execute_plan(example_task, example_plan)
        logger.info(f"Plan execution completed. Result: {result}")

        # Optional: Verify goal state (for demonstration)
        goal_state = goal_manager.get_goal(task_id) # Corrected method name
        if goal_state:
            logger.info(f"Goal '{task_id}' state: {goal_state.status}")
        else:
            logger.warning(f"Goal '{task_id}' not found in GoalManager.")

if __name__ == "__main__":
    main()
