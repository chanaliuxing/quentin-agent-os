import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from quentin.llm.client import call_llm
from quentin.infra.llm.base import ModelResponse, UsageMetadata

def run():
    print("Testing LLM Bridge...")
    mr = ModelResponse(text="OK", usage=UsageMetadata())
    with patch("quentin.infra.llm.factory.ModelClientFactory.create_client") as f:
        mc = MagicMock()
        async def slow(*a, **k):
            import asyncio
            await asyncio.sleep(1)
            return mr
        mc.generate = slow
        f.return_value = mc
        # Test call_llm
        res = call_llm("m1", "hi", max_retries=1)
        if res == "OK":
            print("call_llm: PASSED")
        else:
            raise ValueError("Result mismatch")

if __name__ == "__main__":
    try:
        run()
        print("LLM_VITALS_OK")
    except Exception as e:
        print("FAILED: " + str(e))
        sys.exit(1)
