from typing import List
from quentin.kernel.schemas import ExecutionSummary
from quentin.infra.storage.kv_store import KVStore


class ExecutionStore:
    """
    统一管理 ExecutionSummary：
    - 写入每次任务的 summary
    - 提供最近 N 条 summary 给免疫 / 睡眠 / skill evolution 用
    """

    def __init__(self, kv_store: KVStore, prefix: str = "exec:"):
        self.kv = kv_store
        self.prefix = prefix

    async def save_summary(self, summary: ExecutionSummary):
        key = f"{self.prefix}{summary.task_id}"
        await self.kv.save(key, summary.model_dump())

        # 更新最近列表
        await self.kv.append_list(f"{self.prefix}recent", summary.model_dump())

    async def list_recent(self, limit: int = 100) -> List[ExecutionSummary]:
        data = await self.kv.get(f"{self.prefix}recent") or []
        items = data[-limit:]
        return [ExecutionSummary(**d) for d in items]
