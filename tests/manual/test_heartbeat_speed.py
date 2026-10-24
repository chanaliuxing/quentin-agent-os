import sys
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from quentin.llm.client import call_llm
from quentin.infra.llm.base import ModelResponse, UsageMetadata

def test_speed():
    print("Testing Heartbeat (5s interval)...")
    mr = ModelResponse(text="OK", usage=UsageMetadata())
    
    with patch("quentin.infra.llm.factory.ModelClientFactory.create_client") as factory:
        mc = MagicMock()
        async def slow_gen(*a, **k):
            import asyncio
            # Wait 12 seconds: should produce 2 dots (at 5s, 10s)
            await asyncio.sleep(12)
            return mr
        mc.generate = slow_gen
        factory.return_value = mc
        
        start = time.time()
        res = call_llm("test", "hi", max_retries=1)
        elapsed = time.time() - start
        
        print(f"Elapsed: {elapsed:.1f}s")
        if res == "OK" and elapsed >= 12:
            print("Heartbeat Speed: PASSED")
        else:
            raise ValueError("Test failed or too fast")

if __name__ == "__main__":
    try:
        test_speed()
        print("SPEED_CHECK_OK")
    except Exception as e:
        print("FAILED: " + str(e))
        sys.exit(1)
