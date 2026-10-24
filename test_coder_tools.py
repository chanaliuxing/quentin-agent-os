import asyncio
import os
from quentin.bootstrap.container import Container

async def test_tools():
    print("Testing Tool Registration...")
    container = Container()
    tm = container.tool_manager
    
    tools = tm.list_tool_names()
    print(f"Available tools: {tools}")
    
    coder_tools = [t for t in tools if "coder" in t or "gemini.code" in t or "claude.code" in t]
    print(f"Detected Coder Tools: {coder_tools}")
    
    assert "coder.generate" in tools
    assert "gemini.code" in tools
    assert "claude.code" in tools
    print("\n✅ TOOL REGISTRATION VERIFIED")

if __name__ == "__main__":
    asyncio.run(test_tools())
