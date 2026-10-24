import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

async def run():
    from quentin.tools.manager import ToolManager, ToolCallContext
    from quentin.tools.schemas import ToolCallRequest
    print("Testing Fuzzy...")
    tm = ToolManager()
    tm.register("fs.read_file", lambda p, c=None: "ok")
    req = ToolCallRequest(tool_name="read", payload={})
    res = await tm.call_tool(req, ToolCallContext())
    print("Resolved: read -> " + res.tool_name)

    from quentin.execution.skill_executor import Executor
    print("Testing Guidance...")
    exe = Executor(repo_root=".", tool_manager=tm)
    bad_call = {"tool_name": "unknown_tool", "args": {}}
    # execute_tool_call returns a ToolCallResult object
    tr = await exe._execute_tool_call(tool_call=bad_call, context={})
    err_s = str(tr.error)
    if "HINT:" in err_s:
        print("Guidance: OK")
    else:
        print("Error was: " + err_s)
        raise ValueError("Hint missing")

if __name__ == "__main__":
    try:
        asyncio.run(run())
        print("PREVENTIVE_OK")
    except Exception as e:
        print("FAILED: " + str(e))
        sys.exit(1)
