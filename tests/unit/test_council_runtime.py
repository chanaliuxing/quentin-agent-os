import pytest
from unittest.mock import MagicMock, AsyncMock
import json

from meta_agent.runtime.council_runtime import CouncilRuntime, CouncilTask, CouncilResult
from quentin.llm.ollama_client import OllamaClient, OllamaClientConfig # Corrected import path
from meta_agent.llm.client import LLMRequest # Used in _run_planner etc.
from meta_agent.runtime.council_config import DEFAULT_COUNCIL_CONFIG # For CouncilRuntime __init__

@pytest.fixture
def mock_ollama_client():
    mock_config = MagicMock(spec=OllamaClientConfig)
    mock_config.name = "mock_model"
    mock_config.base_url = "http://mock-llm:11434"
    mock_client = MagicMock(spec=OllamaClient)
    mock_client.config = mock_config
    mock_client.generate = AsyncMock() # This is the method that _run_planner etc. call
    return mock_client

@pytest.fixture
def council_runtime(mock_ollama_client):
    runtime = CouncilRuntime(ollama_client=mock_ollama_client)
    # Ensure config is loaded as expected for tests
    runtime.cfg = DEFAULT_COUNCIL_CONFIG
    return runtime

@pytest.mark.asyncio
async def test_extract_json_normal_wrapped(council_runtime, mock_ollama_client):
    test_json = {"a": 1, "b": "test"}
    mock_ollama_client.generate.return_value = f"Some text before ```json\n{json.dumps(test_json)}\n``` and after."

    task = CouncilTask(
        role="test_role", 
        question="test_question", 
        context={}, 
        json_schema_hint="{}"
    )
    result = await council_runtime.ask_json(task.role, task.question, task.context, task.json_schema_hint)
    
    # We should assert that the generate method was called
    mock_ollama_client.generate.assert_awaited()
    assert result == test_json

@pytest.mark.asyncio
async def test_extract_json_multiple_blocks(council_runtime, mock_ollama_client):
    test_json_first = {"first": 1}
    test_json_second = {"second": 2}
    mock_ollama_client.generate.return_value = f"First block: {json.dumps(test_json_first)} More text. Then second block: {json.dumps(test_json_second)} End."

    task = CouncilTask(
        role="test_role", 
        question="test_question", 
        context={}, 
        json_schema_hint="{}"
    )
    result = await council_runtime.ask_json(task.role, task.question, task.context, task.json_schema_hint)
    
    # _extract_json takes the last block if there are multiple.
    assert result == test_json_second

@pytest.mark.asyncio
async def test_extract_json_invalid_output(council_runtime, mock_ollama_client):
    mock_ollama_client.generate.return_value = "This is not a JSON output."

    task = CouncilTask(
        role="test_role", 
        question="test_question", 
        context={}, 
        json_schema_hint="{}"
    )
    result = await council_runtime.ask_json(task.role, task.question, task.context, task.json_schema_hint)
    
    assert result["status"] == "parse_error"
    assert "no_json_block" in result["reason"]

@pytest.mark.asyncio
async def test_extract_json_empty_output(council_runtime, mock_ollama_client):
    mock_ollama_client.generate.return_value = ""

    task = CouncilTask(
        role="test_role", 
        question="test_question", 
        context={}, 
        json_schema_hint="{}"
    )
    result = await council_runtime.ask_json(task.role, task.question, task.context, task.json_schema_hint)
    
    assert result["status"] == "parse_error"
    assert "no_json_block" in result["reason"]

@pytest.mark.asyncio
async def test_ask_json_planner_critic_judge_flow(council_runtime, mock_ollama_client):
    planner_json = {"plan": ["step1", "step2"]}
    critic_text = "Critique: good plan"
    judge_json = {"final_decision": "approve", "reason": "all good"}

    # Mock responses for planner, critic, and judge calls
    # Planner output (JSON wrapped)
    mock_ollama_client.generate.side_effect = [
        f"Planner output: ```json\n{json.dumps(planner_json)}\n```",
        f"Critic output: {critic_text}",
        f"Judge output: ```json\n{json.dumps(judge_json)}\n```",
    ]

    task = CouncilTask(
        role="test_flow", 
        question="plan this", 
        context={"data": 1}, 
        json_schema_hint="{}"
    )
    result = await council_runtime.ask_json(task.role, task.question, task.context, task.json_schema_hint)
    
    # Final result should be from the judge
    assert result == judge_json
    # Check that generate was called 3 times
    assert mock_ollama_client.generate.call_count == 3


def test_build_planner_prompt_uses_prompt_factory_when_flag_enabled(
    council_runtime,
    monkeypatch,
):
    monkeypatch.setenv("QUENTIN_FF_PROMPT_MIGRATION_M1_SYSTEM_FACTORY", "1")
    task = CouncilTask(
        role="planner_test",
        question="what to do?",
        context={
            "is_subagent": True,
            "agent_id": "agent-test",
            "workspace": "/repo",
            "os": "darwin",
            "enabled_tools": {"fs.read_file": "read file"},
        },
        json_schema_hint='{"answer":"string"}',
    )
    prompt = council_runtime._build_planner_prompt(task)
    assert "[SYSTEM]" in prompt
    assert "[USER]" in prompt
    assert "You are Planner in Quentin council runtime." in prompt
    assert "Runtime: agent=agent-test" in prompt
    # minimal mode path should suppress full tool section in system prompt
    assert "Tools (short summaries):" not in prompt
