import asyncio
import sys
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

async def run():
    from quentin.infra.llm.ollama_client import OllamaClient
    print("Checking num_ctx 8k...")
    c = OllamaClient(base_url="h", name="m")
    with patch.object(c, "_call_api") as m:
        m.return_value = MagicMock(status_code=200, json=lambda:{"response":"ok"})
        await c.generate([{"role":"user","content":"hi"}])
        p = m.call_args[0][3]
        if p.get("options",{}).get("num_ctx") == 8192:
            print("num_ctx: OK")
        else:
            raise ValueError("num_ctx fail: " + str(p))

    from quentin.execution.skill_executor import Executor
    from quentin.tools.manager import ToolManager
    print("Checking Payload log...")
    tm = ToolManager()
    tm.register("ls", lambda p, c=None: "ok")
    exe = Executor(repo_root=".", tool_manager=tm)
    mock_r = {"status":"ok","result":"r","tool_calls":[]}
    with patch("quentin.llm.client.call_llm_with_tools") as ml:
        ml.return_value = {"content":json.dumps(mock_r), "tool_calls":[]}
        import io
        from contextlib import redirect_stdout
        f = io.StringIO()
        with redirect_stdout(f):
            await exe._execute_step(step={"step_id":"s1","description":"t"}, context={}, goal=None)
        if "[Brain Payload]" in f.getvalue():
            print("Payload Log: OK")
        else:
            raise ValueError("Log missing")

if __name__ == "__main__":
    try:
        asyncio.run(run())
        print("TEST_OK")
    except Exception as e:
        print("FAILED: " + str(e))
        sys.exit(1)
