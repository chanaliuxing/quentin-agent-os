import asyncio
import os
import sys
from quentin.bootstrap.container import Container
from quentin.tools.manager import ToolCallRequest, ToolCallContext

async def test_gemini_tool():
    print("🚀 Initializing Gemini Tool Integration Test...")
    
    # Ensure tool packs are enabled
    os.environ["QUENTIN_TOOL_PACKS_ENABLED"] = "1"
    
    container = Container()
    tm = container.tool_manager
    
    # 1. Test gemini.code shortcut
    print("\n--- [TEST 1] gemini.code shortcut ---")
    req = ToolCallRequest(
        tool_name="gemini.code",
        payload={
            "prompt": "Write a simple python function called 'get_system_info' that returns 'Project Taylor' and the current date.",
            "context_files": []
        }
    )
    ctx = ToolCallContext(metadata={"session_id": "test_gemini_direct"})
    
    try:
        result = await tm.call_tool(req, ctx)
        print(f"Status: {result.success}")
        if result.success:
            code = result.output.get('code', '')
            print(f"Generated Code Preview:\n{code[:200]}...")
            if "get_system_info" in code:
                print("✅ [TEST 1] SUCCESS: Code generated correctly.")
            else:
                print("❌ [TEST 1] FAILED: Target function name not found in output.")
        else:
            print(f"❌ [TEST 1] FAILED: {result.error}")
    except Exception as e:
        print(f"❌ [TEST 1] EXCEPTION: {e}")

    # 2. Test coder.generate with gemini_cli backend
    print("\n--- [TEST 2] coder.generate (gemini_cli backend) ---")
    req_gen = ToolCallRequest(
        tool_name="coder.generate",
        payload={
            "goal": "Refactor a math utility",
            "instructions": "Create a class MathWizard with a method 'multiply' that takes two numbers.",
            "backend": "gemini_cli",
            "language": "python"
        }
    )
    
    try:
        result_gen = await tm.call_tool(req_gen, ctx)
        print(f"Status: {result_gen.success}")
        if result_gen.success:
            code_gen = result_gen.output.get('code', '')
            print(f"Generated Code Preview:\n{code_gen[:200]}...")
            if "MathWizard" in code_gen:
                print("✅ [TEST 2] SUCCESS: Complex generation via router worked.")
            else:
                print("❌ [TEST 2] FAILED: Target class name not found in output.")
        else:
            print(f"❌ [TEST 2] FAILED: {result_gen.error}")
    except Exception as e:
        print(f"❌ [TEST 2] EXCEPTION: {e}")

if __name__ == "__main__":
    asyncio.run(test_gemini_tool())
