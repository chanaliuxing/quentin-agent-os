from __future__ import annotations

import logging
import time
from typing import Optional, TYPE_CHECKING

from meta_agent.self_programming.strategy import SimpleEvolutionStrategyManager

if TYPE_CHECKING:
    from meta_agent.self_programming.engine import SelfProgrammingEngine

logger = logging.getLogger(__name__)


def run_once(
    strategy_manager: SimpleEvolutionStrategyManager,
    engine: SelfProgrammingEngine,
) -> int:
    """
    Execute one evolution iteration: generate retry tasks and run them.
    Returns number of tasks attempted.
    """
    tasks = strategy_manager.generate_tasks()
    if not tasks:
        return 0

    attempted = 0
    for task in tasks:
        attempted += 1
        try:
            engine.run_task(task)
        except Exception:
            logger.exception("run_once: failed to execute task %s", task.task_id)
    return attempted


def run_loop(
    strategy_manager: SimpleEvolutionStrategyManager,
    engine: SelfProgrammingEngine,
    *,
    sleep_seconds: int = 30,
    max_iterations: Optional[int] = None,
) -> None:
    """
    Continuous loop for retrying failed tasks.
    """
    iteration = 0
    while max_iterations is None or iteration < max_iterations:
        iteration += 1
        processed = run_once(strategy_manager, engine)
        if processed == 0:
            time.sleep(sleep_seconds)
