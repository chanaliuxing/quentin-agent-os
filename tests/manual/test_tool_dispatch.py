from quentin.tools.manager import ToolManager, ToolCallContext
from quentin.tools.schemas import ToolCallRequest, ToolCallResult
import asyncio

def mock_tool(params, ctx=None):
    # This is what failed before: params was a ToolCallRequest object
    path = params.get("path")
    return f"Success reading {path}"

async def test_dispatch():
    print("--- Testing ToolManager Dispatch Logic ---")
    tm = ToolManager()
    tm.register_tool(type('Spec', (), {'name': 'test.tool'})(), mock_tool)
    
    req = ToolCallRequest(tool_name="test.tool", payload={"path": "/tmp/test.txt"})
    ctx = ToolCallContext()
    
    try:
        res = await tm.call_tool(req, ctx)
        print(f"Result: {res.output}")
        assert "Success reading /tmp/test.txt" in str(res.output)
        print("✅ Dispatch Test PASSED.")
    except AttributeError as e:
        print(f"❌ Dispatch Test FAILED (AttributeError): {e}")
    except Exception as e:
        print(f"❌ Dispatch Test FAILED (General): {e}")

if __name__ == "__main__":
    asyncio.run(test_dispatch())
