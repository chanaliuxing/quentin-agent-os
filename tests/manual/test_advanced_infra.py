import asyncio
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

async def run():
    print("Checking Ollama num_ctx...")
    from quentin.infra.llm.ollama_client import OllamaClient
    c = OllamaClient(base_url="h", name="m")
    with patch.object(c, "_call_api") as m:
        m.return_value = MagicMock(status_code=200, json=lambda:{"response":"ok"})
        await c.generate([{"role":"user","content":"hi"}])
        p = m.call_args[0][3]
        if p.get("options",{}).get("num_ctx") == 32768:
            print("num_ctx: OK")
        else:
            raise ValueError("num_ctx fail: " + str(p))

    print("Checking Session Lock...")
    from quentin.tools.manager import ToolManager
    tm = ToolManager()
    l = tm._get_session_lock("s1")
    with l:
        print("Lock: OK")

if __name__ == "__main__":
    try:
        asyncio.run(run())
        print("ADVANCED_INFRA_OK")
    except Exception as e:
        print("FAILED: " + str(e))
        sys.exit(1)
