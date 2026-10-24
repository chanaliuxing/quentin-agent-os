import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from quentin.memory.query_intent import IntentRouter

def test_intent():
    router = IntentRouter()
    
    assert router.route('"exact"') == "keyword_exact"
    assert router.route("this is a long semantic query about artificial intelligence") == "semantic_explore"
    assert router.route("short") == "mixed"
    
    print("IntentRouter: OK")

if __name__ == "__main__":
    test_intent()
