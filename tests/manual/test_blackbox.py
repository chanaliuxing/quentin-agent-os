import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from quentin.llm.client import call_llm
from quentin.infra.llm.base import ModelResponse, UsageMetadata

def test_blackbox():
    print("Testing Global LLM Blackbox...")
    log_path = Path("data/llm_raw_history.jsonl")
    if log_path.exists(): log_path.unlink()
    
    mr = ModelResponse(text="Raw Story Data", usage=UsageMetadata())
    with patch("quentin.infra.llm.factory.ModelClientFactory.create_client") as f:
        mc = MagicMock()
        async def slow(*a, **k): return mr
        mc.generate = slow
        f.return_value = mc
        
        call_llm("m1", "hi", actor="test_actor", max_retries=1)
        
    if log_path.exists():
        content = log_path.read_text()
        print(f"Log captured: {content.strip()}")
        if "Raw Story Data" in content and "test_actor" in content:
            print("✅ Blackbox: OK")
        else:
            raise ValueError("Log content mismatch")
    else:
        raise ValueError("Blackbox failed to create log file")

if __name__ == "__main__":
    test_blackbox()
