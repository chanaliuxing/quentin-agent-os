# scripts/smoke_test_gemini_coder.py
import os
import json
from quentin.blueprint.auto_patcher import BlueprintGapAutoPatcher
from meta_agent.tools.coder.router import coder_router
from unittest.mock import patch, MagicMock

def test_routing():
    print("=== Coder Routing Smoke Test (Gemini 2.5 Flash) ===")
    
    # Setup environment
    os.environ["CODER_BACKEND"] = "llm_client"
    os.environ["CODER_LLM_PROVIDER"] = "gemini"
    os.environ["CODER_LLM_MODEL"] = "gemini-2.5-flash"
    os.environ["LLM_STUB"] = "1" # Use stub to avoid needing real API keys
    
    # Mock call_llm to see what it receives
    with patch("meta_agent.tools.coder.llm_client_backend.call_llm") as mock_call:
        # Simulate a successful JSON response from stub
        mock_call.return_value = json.dumps({
            "implementation_code": "def gemini_test(): pass",
            "verification_test_code": "def test_gemini(): pass"
        })
        
        from meta_agent.tools.coder.base import CodeGenerationRequest
        req = CodeGenerationRequest(
            goal="Test Gemini Integration",
            context_files=[],
            instructions="Write a test function."
        )
        
        print(f"Calling coder_router.generate with backend: {os.environ['CODER_BACKEND']}")
        result = coder_router.generate(req, backend_name="llm_client")
        
        print(f"Result success: {result.success}")
        print(f"Reasoning: {result.reasoning}")
        
        # Verify arguments passed to call_llm
        args, kwargs = mock_call.call_args
        print(f"Provider passed to call_llm: {kwargs.get('provider')}")
        print(f"Model passed to call_llm: {kwargs.get('config')}")
        
        assert kwargs.get("provider") == "gemini"
        assert kwargs.get("config") == "gemini-2.5-flash"
        assert result.success is True
        
    print("\n✅ Routing test passed!")

if __name__ == "__main__":
    test_routing()