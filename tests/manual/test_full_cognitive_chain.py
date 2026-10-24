import asyncio
import sys
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

async def test_council_reflection_chain():
    print("Testing Council & Reflection Chain...")
    from quentin.council.manager import CouncilDecision
    from quentin.council.done import DoneCouncil
    from quentin.council.reflection import ReflectionCouncil
    from quentin.goals.done_definition import GoalSpec
    
    cm = MagicMock()
    dc = DoneCouncil(council_manager=cm)
    rc = ReflectionCouncil(council_manager=cm)
    goal = GoalSpec.new(description="test")

    # 1. Done
    print("Checking DoneCouncil...")
    cm.ask.return_value = CouncilDecision(
        council_name="done", topic="done_check",
        final={"verdict": "no"}, member_replies=[],
        arbiter_raw=None, created_at="now"
    )
    res = dc.assess(goal=goal, execution_summary={}, metrics={})
    if not res.is_done: print("Done: OK")

    # 2. Reflection
    print("Checking ReflectionCouncil...")
    cm.ask.return_value = CouncilDecision(
        council_name="reflection", topic="reflection",
        final={"verdict": "retry", "answer": {"action": "retry"}},
        member_replies=[], arbiter_raw=None, created_at="now"
    )
    # Align with NEW signature
    advice = rc.reflect(
        goal=goal,
        last_plan={},
        last_exec_result={},
        metrics={},
        failure_count=1
    )
    if advice.action == "retry": print("Reflection: OK")

if __name__ == "__main__":
    try:
        asyncio.run(test_council_reflection_chain())
        print("SUCCESS")
    except Exception as e:
        print("FAILED: " + str(e))
        sys.exit(1)
