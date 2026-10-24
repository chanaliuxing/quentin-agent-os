from datetime import datetime, UTC
from typing import Optional
from quentin.infra.storage.kv_store import KVStore
from quentin.infra.logging import Tracer
from quentin.kernel.schemas import EnvName # Add this import


class BudgetController:
    """
    控制自改/实验的频率：
    - 目前只控制「每天最多多少次实验」
    - 将来可以增加 token / 费用预算
    """

    def __init__(
        self,
        tracer: Tracer,
        kv_store: KVStore,
        max_experiments_per_day: int = 5,
    ):
        self.tracer = tracer
        self.kv = kv_store
        self.max_per_day = max_experiments_per_day

    def _today_key(self) -> str:
        today = datetime.now(UTC).strftime("%Y-%m-%d")
        return f"budget:exp_count:{today}"

    async def can_run_experiment(self) -> bool:
        data = await self.kv.get(self._today_key())
        count = int(data or 0)
        allowed = count < self.max_per_day
        self.tracer.span(
            "L3",
            "budget_check",
            module="budget_controller",
            input={"used": count, "max": self.max_per_day},
            output={"allowed": allowed},
        )
        return allowed

    async def record_run(self) -> None:
        key = self._today_key()
        data = await self.kv.get(key)
        count = int(data or 0) + 1
        await self.kv.save(key, count)
        self.tracer.span(
            "L3",
            "budget_record",
            module="budget_controller",
            output={"used": count, "max": self.max_per_day},
        )
