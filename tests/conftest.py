import pytest
from typing import Dict, Any, List, Optional
import asyncio
import sys
from pathlib import Path
import json # Added for MockCoderRouter
import re # Added for MockCoderRouter
from unittest.mock import MagicMock, AsyncMock

from quentin.infra.storage.kv_store import KVStore # Added import for KVStore
from quentin.llm.multi_council import MultiAICouncil # for spec
from quentin.llm.ollama_client import OllamaClient # for spec

# Add project root to sys.path for module discovery
sys.path.insert(0, str(Path(__file__).parent.parent))

@pytest.fixture
def mock_kv_store() -> MagicMock: # Now returns a MagicMock directly
    mock = MagicMock(spec=KVStore) # Spec against the actual KVStore interface
    
    # Internal data structure for the mock's side effects
    mock._data: Dict[str, Any] = {}

    # Configure mock methods as AsyncMocks with side_effects
    async def mock_save(key: str, value: Any) -> None:
        mock._data[key] = value
        await asyncio.sleep(0.01) # Simulate async operation
    
    async def mock_get(key: str) -> Optional[Any]:
        await asyncio.sleep(0.01) # Simulate async operation
        return mock._data.get(key)

    mock.save.side_effect = mock_save
    mock.get.side_effect = mock_get
    # Add a custom append_list for those who use it, storing into the same _data,
    # but not used by SkillLibrary for skill:all
    mock.append_list = AsyncMock(side_effect=lambda lk, i: (lambda x: x.append(i))(mock._data.setdefault(lk, []))) # Store as list in _data
    mock.get_list = AsyncMock(side_effect=lambda lk: mock._data.get(lk, []))

    yield mock

# Mock CoderRouter for End-to-End Demo
from meta_agent.tools.coder.base import CodeGenerationResult, CodeGenerationRequest
from quentin.llm.ollama_client import OllamaClientConfig # Added import for OllamaClientConfig

class MockCoderRouter:
    def __init__(self):
        self._responses = {}

    def add_response(self, gap_id: str, implementation_code: str, verification_test_code: str, success: bool = True, reasoning: str = "Mocked success"):
        json_output = {
            "implementation_code": implementation_code,
            "verification_test_code": verification_test_code
        }
        self._responses[gap_id] = CodeGenerationResult(
            success=success,
            code=json.dumps(json_output), # The engine expects a JSON string
            reasoning=reasoning
        )

    def generate(self, request: CodeGenerationRequest, backend_name: str) -> CodeGenerationResult:
        # Assuming the gap_id is part of the request.goal
        gap_id_match = re.search(r"gap: (gap_demo_001)", request.goal)
        gap_id = gap_id_match.group(1) if gap_id_match else None
        
        if gap_id in self._responses:
            return self._responses[gap_id]
        
        # Default failure for unmocked gaps
        return CodeGenerationResult(
            success=False,
            code="{}",
            reasoning=f"No mock response for gap_id: {gap_id}"
        )

@pytest.fixture
def mock_coder_router() -> MockCoderRouter:
    mock = MockCoderRouter()
    # Pre-configure a response for our demo gap
    mock.add_response(
        gap_id="gap_demo_001",
        implementation_code="""
# quentin/mutable/math_utils.py
def calculate_fibonacci(n: int) -> int:
    if n <= 0:
        return 0
    elif n == 1:
        return 1
    else:
        a, b = 0, 1
        for _ in range(2, n + 1):
            a, b = b, a + b
        return b
""",
        verification_test_code="""
# tests/temp_test.py
import pytest
from quentin.mutable.math_utils import calculate_fibonacci

def test_calculate_fibonacci_zero():
    assert calculate_fibonacci(0) == 0

def test_calculate_fibonacci_one():
    assert calculate_fibonacci(1) == 1

def test_calculate_fibonacci_positive():
    assert calculate_fibonacci(2) == 1
    assert calculate_fibonacci(3) == 2
    assert calculate_fibonacci(4) == 3
    assert calculate_fibonacci(5) == 5
    assert calculate_fibonacci(10) == 55
"""
    )
    return mock


@pytest.fixture
def mock_council() -> MagicMock:
    mock_council_manager = MagicMock(spec=MultiAICouncil)
    mock_council_manager.ask_text = AsyncMock(return_value="Summarized memory content.")
    mock_council_manager.deliberate = AsyncMock(return_value=MagicMock(final_answer="Summarized memory content."))
    
    # Also mock it as if it's an OllamaClient for the fallback path
    mock_ollama_client = MagicMock(spec=OllamaClient)
    mock_ollama_client.complete = AsyncMock(return_value="Summarized memory content.")
    
    # To satisfy the "if hasattr(self.council, "ask_text")" or "deliberate", 
    # and also "isinstance(self.council, OllamaLLMClient)"
    # We can create a mock that tries to satisfy both, or just return a simple object.
    
    # For simplicity, let's create a mock object that supports both interfaces, favoring ask_text/deliberate
    # And it also needs to have a config attribute if OllamaClient.complete is called.
    
    class MixedMockCouncil(MagicMock):
        # Default behavior:
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.ask_text = AsyncMock(return_value="Summarized memory content from ask_text.")
            self.deliberate = AsyncMock(return_value=MagicMock(final_answer="Summarized memory content from deliberate."))
            self.complete = AsyncMock(return_value="Summarized memory content from complete.")
            
            # For OllamaClient type checking
            self.config = MagicMock(spec=OllamaClientConfig) # Needs to be defined if OllamaClient is instantiated
            self.config.name = "mock-ollama-model"
            self.config.base_url = "http://mock-ollama"
        
    mock = MixedMockCouncil(spec=MultiAICouncil) # Start as a MultiAICouncil
    return mock