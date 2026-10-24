import asyncio
import os
from pathlib import Path
from quentin.tools.manager import ToolManager, ToolCallRequest
from quentin.tools.plugin_loader import register_tool_plugins

async def test_tool_isolation_async():
    print("Testing Tool Plugin Isolation...")
    tm = ToolManager()
    repo_root = Path(".").resolve()
    
    # 1. Disable isolation
    os.environ["QUENTIN_PLUGIN_RUNTIME_ISOLATION"] = "0"
    register_tool_plugins(tool_manager=tm, repo_root=repo_root)
    
    if "test_isolated_tool" not in tm._specs:
        print(f"Test tool not registered. Found: {list(tm._specs.keys())}")
        return

    req = ToolCallRequest(tool_name="test_isolated_tool", payload={})
    res = await tm.call_tool(req)
    print(f"Isolation OFF result: {res.output}")
    assert res.success == True
    
    # 2. Enable isolation
    print("\nEnabling isolation...")
    os.environ["QUENTIN_PLUGIN_RUNTIME_ISOLATION"] = "1"
    
    res = await tm.call_tool(req)
    print(f"Isolation ON result: {res.output}")
    assert res.success == False
    assert "missing_required_env" in str(res.error)
    print("Tool isolation check PASSED.")

if __name__ == "__main__":
    try:
        asyncio.run(test_tool_isolation_async())
    except Exception as e:
        print(f"FAILED: {e}")
        import traceback
        traceback.print_exc()
        exit(1)
