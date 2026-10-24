import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

async def run_dry():
    from quentin.tools.manager import ToolManager
    from quentin.execution.skill_executor import Executor
    tm = ToolManager()
    tm.register("ls", lambda p, c=None: {"files": []})
    exe = Executor(repo_root=".", tool_manager=tm)
    # Testing the REAL method CognitiveLoop calls
    print("Testing execute_plan...")
    res = await exe.execute_plan(
        steps=[{"step_id": "s1", "description": "test"}],
        context={},
        goal=None
    )
    print("Execute Plan Status: OK")

if __name__ == "__main__":
    asyncio.run(run_dry())
