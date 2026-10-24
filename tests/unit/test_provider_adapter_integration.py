import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from quentin.llm.provider_adapters.router import adapter_router

def test_adapter():
    g = adapter_router.get_adapter("gemini")
    assert g is not None
    
    msgs = [{"role": "user", "content": "hi"}]
    t = g.transform_messages(msgs)
    
    assert t[0]["parts"][0]["text"] == "hi"
    print("ProviderAdapter: OK")

if __name__ == "__main__":
    test_adapter()
