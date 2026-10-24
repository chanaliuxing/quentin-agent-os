# quentin/demo/toy_workflow.py

from __future__ import annotations

import random
import uuid
from typing import Optional

from quentin.runtime.agent_runtime import AgentRuntime
from quentin.domains.base import DomainTask

async def run_demo(runtime: AgentRuntime, episodes: int = 5) -> None:
    tracer = runtime.tracer

    for i in range(episodes):
        a = random.randint(0, 10)
        b = random.randint(0, 10)
        expected = a + b

        task = DomainTask(
            domain="demo",
            goal=f"add {a} + {b}",
            input={"a": a, "b": b},
        )

        summary = await runtime.cognitive_loop.run_task(task)
        
        ok = False
        output = None
        error = summary.error
        
        if summary.success and summary.steps:
            last_step = summary.steps[-1]
            if last_step.success and last_step.output:
                output = last_step.output.get("result")
                if output is not None:
                    ok = (output == expected)
        
        tracer.span(
            "L1",
            "demo_eval",
            module="demo",
            input={
                "task_id": summary.task_id,
                "a": a,
                "b": b,
                "output": output,
                "expected": expected,
            },
            output={"ok": ok},
        )

        status = "OK" if ok else "BUG"
        print(f"[EP {i}] {a} + {b} -> {output} (expected {expected}) :: {status}")

        if not ok:
            await runtime.immune_loop.record_demo_task_result(
                task_id=summary.task_id,
                success=summary.success,
                expected_ok=ok,
                error=f"Output {output} != Expected {expected}" if not error else error,
            )
