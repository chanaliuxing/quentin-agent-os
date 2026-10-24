# quentin/demo/self_improvement_pipeline.py

from __future__ import annotations

from typing import Optional

import uuid

from quentin.runtime.agent_runtime import AgentRuntime
# from quentin.cognitive.loop import Task # Using DomainTask from domains.base
from quentin.domains.base import DomainTask


async def run_demo_self_improvement(
    runtime: AgentRuntime,
    episodes_before: int = 5,
    episodes_after: int = 5,
    auto_apply: bool = True,
) -> None:
    """
    完整 Demo 流水线：

    1. 先跑几轮 demo 任务（使用 buggy 的 add_numbers）
    2. 从 ImmuneLoop 拿到 demo 域的 ImmuneCase hotspot
    3. 用 SelfImprovementManager 为该 case 创建补丁（修复 add_numbers）
    4. 调用 SelfProgrammingEngine 跑测试并应用补丁
    5. 再跑几轮 demo 任务，观察是否恢复正常
    """

    tracer = runtime.tracer

    # -------- Step 1: 跑 Buggy 版本 --------
    tracer.span(
        "L1",
        "demo_self_improvement_before",
        module="demo",
        input={"episodes_before": episodes_before},
    )

    from quentin.demo.toy_workflow import run_demo
    print("=== [Demo] Before patch ===")
    await run_demo(runtime, episodes=episodes_before)

    # -------- Step 2: 找 demo 域的 ImmuneCase --------
    immune = runtime.immune_loop
    cases = await immune.list_cases(limit=50)
    demo_cases = [c for c in cases if c.domain == "demo"]

    if not demo_cases:
        print("[Demo] No demo ImmuneCase found after running demo. Nothing to improve.")
        return

    case = demo_cases[-1]
    print(f"[Demo] Using ImmuneCase: {case.case_id} ({case.title})")

    # -------- Step 3: 为 ImmuneCase 创建对应 patch --------
    # 目标：修复 mutable/skills/example_skill.py 中的 add_numbers 实现。
    #
    # 现有实现：
    #     return a - b
    #
    # 期望实现：
    #     return a + b
    #
    # 我们使用最简单的 text_replace 方式：
    target_file = "mutable/skills/example_skill.py"
    description = "Fix demo add_numbers: use addition instead of subtraction."
    search = "return a - b"
    replace = "return a + b"

    self_improve = runtime.self_improvement
    patch = await self_improve.open_patch_for_case(
        case_id=case.case_id,
        target_file=target_file,
        description=description,
        search=search,
        replace=replace,
        allow_auto_apply=auto_apply,
    )

    print(f"[Demo] Patch proposed: {patch.patch_id} -> {patch.target_file}")

    # -------- Step 4: 自编程引擎跑测试 + 应用补丁 --------
    self_prog = runtime.self_programming

    patch = await self_prog.run_tests(patch.patch_id)
    if not patch.test_summary.passed:
        print("[Demo] Patch tests FAILED; will NOT apply this patch.")
        print("       Logs:")
        print(patch.test_summary.logs)
        return

    print("[Demo] Patch tests PASSED.")

    if auto_apply:
        patch = await self_prog.apply_patch(patch.patch_id, auto=True)
        print(f"[Demo] Patch applied. Backup file: {patch.meta.get('backup_file')}")
    else:
        print("[Demo] auto_apply=False, patch NOT applied automatically.")
        return

    # -------- Step 5: 再跑几轮 demo 任务，观察修复效果 --------
    tracer.span(
        "L1",
        "demo_self_improvement_after",
        module="demo",
        input={"episodes_after": episodes_after},
    )

    print("=== [Demo] After patch ===")
    await run_demo(runtime, episodes=episodes_after)

    print("[Demo] Self-improvement pipeline completed.")
