from typing import List
from quentin.kernel.schemas import TrainingPair
from quentin.infra.storage.kv_store import KVStore


class TrainingDataStore:
    """
    管理训练/对齐数据：
    - 来自 SleepLoop / ImmuneLoop / 人工导入
    - 将来可以导出为 JSONL / Parquet 给外部训练脚本使用
    """

    def __init__(self, kv_store: KVStore, prefix: str = "train_pair:"):
        self.kv = kv_store
        self.prefix = prefix

    async def save_pair(self, pair: TrainingPair):
        await self.kv.save(f"{self.prefix}{pair.pair_id}", pair.model_dump())
        await self.kv.append_list(f"{self.prefix}all", pair.model_dump())

    async def list_all(self) -> List[TrainingPair]:
        data = await self.kv.get(f"{self.prefix}all") or []
        return [TrainingPair(**d) for d in data]
