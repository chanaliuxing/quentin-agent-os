# tests/unit/test_model_router_base_url_normalization.py
from quentin.routing.model_router import _normalize_ollama_base_url

def test_model_router_base_url_normalization():
    # 1. No suffix
    assert _normalize_ollama_base_url("http://localhost:11434") == "http://localhost:11434"
    
    # 2. /api/generate suffix
    assert _normalize_ollama_base_url("http://localhost:11434/api/generate") == "http://localhost:11434"
    
    # 3. /api/chat suffix
    assert _normalize_ollama_base_url("http://localhost:11434/api/chat") == "http://localhost:11434"
    
    # 4. Trailing slash
    assert _normalize_ollama_base_url("http://localhost:11434/") == "http://localhost:11434"

    # 5. Empty
    assert _normalize_ollama_base_url("") == "http://localhost:11434"
    assert _normalize_ollama_base_url(None) == "http://localhost:11434"
