import pytest
from unittest.mock import MagicMock
from quentin.llm.ollama_client import OllamaLLMClient

def test_format_resilience_salvage():
    # Test that messy outputs still produce valid JSON
    messy = """
Here is your plan:
{
  "steps": [
    {"id": "s1", "description": "test"}
  ]
}
Note: ignore the text above.
"""
    parsed = OllamaLLMClient.extract_json(messy)
    assert parsed["steps"][0]["id"] == "s1"

def test_format_resilience_code_block():
    messy = """
```json
{"status": "ok"}
```
"""
    parsed = OllamaLLMClient.extract_json(messy)
    assert parsed["status"] == "ok"
