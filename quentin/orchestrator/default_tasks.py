from __future__ import annotations

from quentin.orchestrator.models import ScheduledTask
from quentin.runtime.sleep_loop import SleepLoop
from quentin.skills.evolution import SkillEvolutionLoop
from quentin.self_programming.skill_impl_runner import run_skill_impl_cycle
from quentin.cli.blueprint_runner import run_blueprint_self_iteration
from quentin.runtime.system import RuntimeFacade
from scripts.blueprint_self_iterate import create_runtime_for_blueprint_self_iteration


def build_default_tasks(runtime: RuntimeFacade) -> list[ScheduledTask]:
    tasks: list[ScheduledTask] = []

    # 1) SleepLoop：每天跑一次（间隔 24h，窗口 24h，最多 1 次）
    if runtime.sleep_loop:
        tasks.append(
            ScheduledTask(
                name="sleep_loop_daily",
                fn=lambda: runtime.sleep_loop.run_once(),
                interval_seconds=24 * 3600,
                max_runs_per_window=1,
                window_seconds=24 * 3600,
            )
        )

    # 2) SkillEvolutionLoop：每天各 domain 跑一次，限制每次最多挖 1 个新技能
    if runtime.skill_evolution_loop:
        for domain in ["desktop", "legal", "trading", "generic"]:
            tasks.append(
                ScheduledTask(
                    name=f"skill_evolution_{domain}",
                    fn=lambda d=domain: runtime.skill_evolution_loop.run_once(domain=d),
                    interval_seconds=24 * 3600,
                    max_runs_per_window=1,
                    window_seconds=24 * 3600,
                )
            )

    # 3) SkillImplCycle：每天各 domain 跑一次，最多尝试实现 1 个技能
    # This is more complex as it requires many components.
    # We will skip this for now as it's not a simple loop call.

    # 4) Blueprint 改进循环：每天跑一次
    # This is also complex and is already orchestrated by blueprint_self_iterate.py
    # We will skip this for now.

    return tasks
