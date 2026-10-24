# tests/unit/test_council_timeout_policy.py
import os
from quentin.llm.client import _resolve_timeout_seconds

def test_council_timeout_policy():
    # 1. Ollama + localhost => Local timeout
    # Default local is 240, but plan says floor should be 420 (handled in env usually)
    os.environ["QUENTIN_LLM_TIMEOUT_LOCAL_S"] = "420"
    os.environ["QUENTIN_LLM_TIMEOUT_REMOTE_S"] = "60"
    
    t1 = _resolve_timeout_seconds(provider="ollama", explicit_timeout=None, base_url="http://localhost:11434")
    assert t1 == 420.0

    # 2. OpenAI + remote => Remote timeout
    t2 = _resolve_timeout_seconds(provider="openai", explicit_timeout=None, base_url="https://api.openai.com/v1")
    assert t2 == 60.0

    # 3. Explicit timeout wins
    t3 = _resolve_timeout_seconds(provider="ollama", explicit_timeout=999, base_url="http://localhost:11434")
    assert t3 == 999.0

    # 4. Local IP check
    t4 = _resolve_timeout_seconds(provider="openai", explicit_timeout=None, base_url="http://192.168.1.5:8080")
    assert t4 == 420.0
