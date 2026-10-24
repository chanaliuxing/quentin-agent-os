import pytest
import json
from quentin.llm.ollama_client import OllamaLLMClient

def test_extract_json_direct():
    text = '{"key": "value"}'
    assert OllamaLLMClient.extract_json(text) == {"key": "value"}

def test_extract_json_markdown():
    text = """
Here is the json:
```json
{"key": "value"}
```
Hope this helps.
"""
    assert OllamaLLMClient.extract_json(text) == {"key": "value"}

def test_extract_json_fenced_no_type():
    text = """
```
{"key": "value"}
```
"""
    assert OllamaLLMClient.extract_json(text) == {"key": "value"}

def test_extract_json_fallback_braces():
    text = 'The result is { "success": true }.'
    assert OllamaLLMClient.extract_json(text) == {"success": True}

def test_extract_json_multiple_blocks():
    text = """
```json
{"first": 1}
```
And then:
```json
{"last": 2}
```
"""
    # Should take the last one
    assert OllamaLLMClient.extract_json(text) == {"last": 2}

def test_extract_json_invalid():
    text = "No json here."
    with pytest.raises(ValueError, match="No valid JSON found"):
        OllamaLLMClient.extract_json(text)
