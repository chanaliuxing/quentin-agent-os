import asyncio
from quentin.mutable.toy_planner import plan_toy_task


def test_toy_planner_basic():
    """正常 goal 应该能返回非空 steps。"""
    task = {"goal": "Say hello to a friend", "domain": "toy"}
    plan = asyncio.run(plan_toy_task(task))
    assert "steps" in plan
    assert isinstance(plan["steps"], list)
    assert len(plan["steps"]) >= 3


def test_toy_planner_crash_bug():
    """
    当前版本中，包含 'CRASH' 的 goal 会抛异常。
    这个测试一开始是「期望失败」的：

    - 前期：这个测试会失败，暴露 bug
    - 后期：如果自编程修复了 bug，你可以把这里改成不期待异常
    """
    task = {"goal": "This should CRASH by design", "domain": "toy"}

    try:
        asyncio.run(plan_toy_task(task))
    except RuntimeError as e:
        assert "CRASH" in str(e).upper()
    else:
        # 如果将来 bug 被修了，你可以改掉这个分支的逻辑
        # 例如 assert no exception
        assert False, "Expected RuntimeError for 'CRASH' goal, but got none."
